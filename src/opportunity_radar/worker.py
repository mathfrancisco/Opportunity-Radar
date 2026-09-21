from __future__ import annotations

import signal
from asyncio import run as run_async
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import (
    CollectionMode,
    CollectionRequest,
    ExecutionTrigger,
)
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import AnalysisStatus, SemanticAnalysisPort
from opportunity_radar.matching.service import (
    DEFAULT_ANALYSIS_VERDICTS,
    AnalysisInProgressError,
    MatchingService,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.logging import (
    configure_logging,
    correlation_scope,
    get_logger,
)
from opportunity_radar.profile.domain import ProfileNotFoundError

WORKER_READY_FILE = Path("/tmp/opportunity-radar-worker-ready")

# Every functional job the worker can schedule, mapped to its scheduler id. The startup log
# is derived from this map against the built scheduler, never from the settings: a job that
# is not registered must never be reported as active, whatever its kill switch says.
FUNCTIONAL_JOB_IDS = {
    "collect_enabled_sources": "collect-enabled-sources",
    "normalize_opportunities": "normalize-opportunities",
    "evaluate_pending": "evaluate-pending",
    "analyze_pending": "analyze-pending",
}

logger = get_logger("opportunity_radar.worker")


def heartbeat() -> None:
    """Expose a lightweight scheduler liveness job."""
    logger.debug("worker heartbeat")


def normalize_opportunities(engine: Engine) -> None:
    """Each pass gets its own correlation id, so one batch is greppable end to end."""
    with correlation_scope():
        with Session(engine) as session:
            try:
                batch = OpportunityService(session).normalize_pending()
            except Exception:
                logger.exception("normalization batch failed", extra={"job": "normalize"})
                raise
        if batch.processed:
            logger.info(
                "normalization batch finished",
                extra={
                    "job": "normalize",
                    "processed": batch.processed,
                    "succeeded": batch.succeeded,
                    "review_required": batch.review_required,
                    "failed": batch.failed,
                },
            )


def evaluate_pending(engine: Engine, *, batch_size: int = 50) -> None:
    """Evaluate each eligible opportunity independently for the current identity."""
    with correlation_scope():
        with Session(engine) as session:
            service = MatchingService(session)
            try:
                pending_ids = service.pending_evaluation_ids(limit=batch_size)
            except ProfileNotFoundError:
                # A missing active profile is an expected degraded operating state.
                logger.warning(
                    "matching batch degraded",
                    extra={"job": "evaluate", "reason": "no_active_profile"},
                )
                return
            completed = failed = 0
            for opportunity_id in pending_ids:
                try:
                    service.evaluate(opportunity_id)
                    completed += 1
                except Exception:
                    session.rollback()
                    failed += 1
                    logger.exception(
                        "opportunity evaluation failed",
                        extra={"job": "evaluate", "opportunity_id": str(opportunity_id)},
                    )
            if pending_ids:
                logger.info(
                    "matching batch finished",
                    extra={
                        "job": "evaluate",
                        "processed": len(pending_ids),
                        "succeeded": completed,
                        "failed": failed,
                    },
                )


def analyze_pending(
    engine: Engine,
    adapter: SemanticAnalysisPort,
    *,
    batch_size: int = 10,
    eligible_verdicts: tuple[str, ...] = (),
    cooldown_seconds: int = 3600,
    attempt_window_seconds: int = 86400,
    max_attempts: int = 3,
    lease_seconds: int = 900,
) -> None:
    """Attach the semantic layer to current assessments, one claim at a time.

    The adapter classifies its own failures instead of raising, so an Ollama that is down
    degrades this job alone: evaluation keeps running and the failure is persisted as the
    history entry that the cooldown then reads.
    """
    with correlation_scope() as correlation_id:
        with Session(engine) as session:
            service = MatchingService(session)
            pending = service.pending_analysis_ids(
                limit=batch_size,
                eligible_verdicts=eligible_verdicts or DEFAULT_ANALYSIS_VERDICTS,
                cooldown=timedelta(seconds=cooldown_seconds),
                attempt_window=timedelta(seconds=attempt_window_seconds),
                max_attempts=max_attempts,
            )
            completed = degraded = claimed_elsewhere = failed = 0
            for assessment_id in pending:
                try:
                    analysis = run_async(
                        service.analyze(
                            assessment_id,
                            adapter,
                            owner=correlation_id,
                            lease=timedelta(seconds=lease_seconds),
                        )
                    )
                except AnalysisInProgressError:
                    # The manual action or another worker holds it. Not an error.
                    claimed_elsewhere += 1
                    continue
                except Exception:
                    session.rollback()
                    failed += 1
                    logger.exception(
                        "assessment analysis failed",
                        extra={"job": "analyze", "assessment_id": str(assessment_id)},
                    )
                    continue
                if analysis.status == AnalysisStatus.AI_COMPLETED.value:
                    completed += 1
                else:
                    degraded += 1
            if pending:
                logger.info(
                    "analysis batch finished",
                    extra={
                        "job": "analyze",
                        "processed": len(pending),
                        "succeeded": completed,
                        "degraded": degraded,
                        "claimed_elsewhere": claimed_elsewhere,
                        "failed": failed,
                    },
                )


def collect_enabled_sources(engine: Engine, *, timezone: str = "UTC") -> None:
    """Run only enabled sources whose five-field cron expression is due."""
    with correlation_scope() as correlation_id:
        with Session(engine) as session:
            service = AcquisitionService(session)
            sources, _ = service.list_sources(offset=0, limit=100)
            now = datetime.now(ZoneInfo(timezone))
            for source in sources:
                if not source.enabled or not source.schedule or source.source_type == "manual":
                    continue
                try:
                    trigger = CronTrigger.from_crontab(source.schedule, timezone=timezone)
                    previous = max(
                        (item.started_at for item in source.runs if item.started_at),
                        default=None,
                    )
                    due_at = trigger.get_next_fire_time(previous, now)
                    if due_at is None or due_at > now:
                        continue
                    collector = service.registry.resolve(source.source_type)
                    configured_keywords = source.configuration.get("keywords", ())
                    keywords = (
                        tuple(configured_keywords)
                        if isinstance(configured_keywords, list)
                        and all(isinstance(item, str) for item in configured_keywords)
                        else ()
                    )
                    request = CollectionRequest(
                        source_definition_id=source.id,
                        mode=(
                            CollectionMode.INCREMENTAL
                            if collector.capabilities.incremental_cursor
                            else CollectionMode.DISCOVERY
                        ),
                        keywords=keywords if collector.capabilities.keyword_search else (),
                        correlation_id=correlation_id,
                        execution_trigger=ExecutionTrigger.SCHEDULED,
                    )
                    run_async(service.execute(source.id, request))
                except Exception:
                    session.rollback()
                    logger.exception(
                        "scheduled collection failed",
                        extra={"job": "collect", "source_id": str(source.id)},
                    )


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.collection_timezone)
    engine = create_database_engine(settings.database_url)
    scheduler.add_job(heartbeat, "interval", minutes=5, id="heartbeat", replace_existing=True)
    if settings.worker_normalize_enabled:
        scheduler.add_job(
            normalize_opportunities,
            "interval",
            seconds=60,
            args=(engine,),
            id="normalize-opportunities",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    if settings.worker_collect_enabled:
        scheduler.add_job(
            collect_enabled_sources,
            "interval",
            seconds=60,
            args=(engine,),
            kwargs={"timezone": settings.collection_timezone},
            id="collect-enabled-sources",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    if settings.worker_match_enabled:
        scheduler.add_job(
            evaluate_pending,
            "interval",
            seconds=60,
            args=(engine,),
            kwargs={"batch_size": settings.worker_evaluate_batch_size},
            id="evaluate-pending",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    if settings.worker_analyze_enabled:
        scheduler.add_job(
            analyze_pending,
            "interval",
            seconds=120,
            args=(engine, build_analysis_adapter(settings)),
            kwargs={
                "batch_size": settings.worker_analyze_batch_size,
                "eligible_verdicts": settings.analysis_eligible_verdicts,
                "cooldown_seconds": settings.analysis_retry_cooldown_seconds,
                "attempt_window_seconds": settings.analysis_retry_attempt_window_seconds,
                "max_attempts": settings.analysis_retry_max_attempts,
                "lease_seconds": settings.analysis_claim_lease_seconds,
            },
            id="analyze-pending",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    jobs = {
        name: scheduler.get_job(job_id) is not None
        for name, job_id in FUNCTIONAL_JOB_IDS.items()
    }
    logger.info("worker jobs configured", extra={"jobs": jobs})
    return scheduler


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    scheduler = build_scheduler(settings)
    stopped = Event()

    def stop(*_: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    scheduler.start()
    WORKER_READY_FILE.touch()
    logger.info("worker started", extra={"timezone": settings.collection_timezone})
    try:
        stopped.wait()
    finally:
        WORKER_READY_FILE.unlink(missing_ok=True)
        scheduler.shutdown(wait=False)
        logger.info("worker stopped")


if __name__ == "__main__":
    run()
