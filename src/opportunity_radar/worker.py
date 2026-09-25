from __future__ import annotations

import signal
from asyncio import run as run_async
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.alerts import (
    SourceAlertService,
    build_source_alert_notifier,
)
from opportunity_radar.acquisition.domain import (
    CollectionMode,
    CollectionRequest,
    ExecutionTrigger,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.scheduling import CollectionGate, evaluate_gate
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import (
    AnalysisMetrics,
    AnalysisStatus,
    SemanticAnalysisPort,
)
from opportunity_radar.matching.service import (
    DEFAULT_ANALYSIS_VERDICTS,
    AnalysisInProgressError,
    MatchingService,
    is_reused_analysis,
)
from opportunity_radar.operations.retention import PayloadRetentionService
from opportunity_radar.operations.service import observe_job
from opportunity_radar.opportunities.embeddings import (
    EmbeddingPort,
    build_embedding_adapter,
    count_pending_embeddings,
    embed_pending,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.logging import (
    configure_logging,
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
    "expire_raw_payloads": "expire-raw-payloads",
    "embed_opportunities": "embed-opportunities",
}

#: How long an embedding pass waits for the GPU before giving the turn up. A warm analysis
#: takes seconds (SPEC 36, section 3.2); a pass that would wait longer is skipped and the
#: next one, an interval later, tries again, instead of holding a scheduler thread.
EMBED_ADMISSION_TIMEOUT_SECONDS = 30.0

logger = get_logger("opportunity_radar.worker")


class GpuAdmission:
    """One model call on the GPU at a time, served in arrival order.

    Analysis and embedding share 8 GB of VRAM on the reference machine (SPEC 36, section
    3.1), and whether both models fit resident with their contexts is still to be
    measured. Admission is per model call — one analysis, one embedding batch — so neither
    job holds the GPU for a whole pass. The turn is handed straight to the oldest waiter on
    release: with a plain lock, the analysis loop, which re-acquires at once, could keep
    the embedding job out for its whole batch.

    Process-wide by design: the API's query embeddings are not counted here.
    """

    def __init__(self) -> None:
        self._mutex = Lock()
        self._busy = False
        self._waiting: deque[Event] = deque()

    def acquire(self, timeout: float | None = None) -> bool:
        """Wait for the turn; `False` when `timeout` passed first. `None` waits forever."""
        with self._mutex:
            if not self._busy:
                self._busy = True
                return True
            turn = Event()
            self._waiting.append(turn)
        if turn.wait(timeout):
            return True
        with self._mutex:
            if turn.is_set():  # handed over between the timeout and this line
                return True
            self._waiting.remove(turn)
            return False

    def release(self) -> None:
        with self._mutex:
            if self._waiting:
                self._waiting.popleft().set()
            else:
                self._busy = False

    @contextmanager
    def hold(self) -> Iterator[None]:
        self.acquire()
        try:
            yield
        finally:
            self.release()


GPU_ADMISSION = GpuAdmission()


def heartbeat() -> None:
    """Expose a lightweight scheduler liveness job."""
    logger.debug("worker heartbeat")


def normalize_opportunities(engine: Engine) -> None:
    """Each pass gets its own correlation id, so one batch is greppable end to end."""
    with observe_job(
        engine, job_name="normalize_opportunities", interval=timedelta(seconds=60)
    ):
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
    with observe_job(
        engine, job_name="evaluate_pending", interval=timedelta(seconds=60)
    ):
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


def warm_up_models(
    adapter: SemanticAnalysisPort, *, admission: GpuAdmission = GPU_ADMISSION
) -> None:
    """Load the model once at startup, so the first analysis does not pay for it."""
    with admission.hold():
        metrics = run_async(adapter.warm_up())
    _log_warm_up(metrics, reason="startup")


def _log_warm_up(metrics: AnalysisMetrics | None, *, reason: str) -> None:
    if metrics is None:
        return
    logger.info(
        "analysis model warmed up",
        extra={"job": "warm-up", "reason": reason, "load_ms": metrics.load_ms},
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
    admission: GpuAdmission = GPU_ADMISSION,
) -> None:
    """Attach the semantic layer to current assessments, one claim at a time.

    The adapter classifies its own failures instead of raising, so an Ollama that is down
    degrades this job alone: evaluation keeps running and the failure is persisted as the
    history entry that the cooldown then reads. Each model call waits for its GPU turn,
    which the embedding job gets between two analyses.
    """
    with observe_job(
        engine, job_name="analyze_pending", interval=timedelta(seconds=120)
    ) as correlation_id:
        with Session(engine) as session:
            service = MatchingService(session)
            pending = service.pending_analysis_ids(
                limit=batch_size,
                eligible_verdicts=eligible_verdicts or DEFAULT_ANALYSIS_VERDICTS,
                cooldown=timedelta(seconds=cooldown_seconds),
                attempt_window=timedelta(seconds=attempt_window_seconds),
                max_attempts=max_attempts,
            )
            if pending:
                # After an idle stretch longer than `keep_alive` the server has unloaded
                # the model; loading it here keeps that cost out of the first analysis.
                with admission.hold():
                    metrics = run_async(adapter.warm_up(only_if_idle=True))
                _log_warm_up(metrics, reason="idle")
            completed = reused = degraded = claimed_elsewhere = failed = 0
            for assessment_id in pending:
                try:
                    with admission.hold():
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
                    reused += is_reused_analysis(analysis)
                else:
                    degraded += 1
            if pending:
                logger.info(
                    "analysis batch finished",
                    extra={
                        "job": "analyze",
                        "processed": len(pending),
                        "succeeded": completed,
                        "reused": reused,
                        "degraded": degraded,
                        "claimed_elsewhere": claimed_elsewhere,
                        "failed": failed,
                    },
                )


def embed_opportunities(
    engine: Engine,
    adapter: EmbeddingPort | None,
    *,
    batch_size: int = 32,
    interval_seconds: int = 120,
    admission: GpuAdmission = GPU_ADMISSION,
    admission_timeout_seconds: float = EMBED_ADMISSION_TIMEOUT_SECONDS,
) -> None:
    """Keep one current vector per eligible opportunity, one bounded batch per pass.

    `None` is embedding switched off, and an unreachable model is the same for this pass:
    both are logged as degraded and charge no posting for it. A posting whose own vector
    came back wrong is recorded and cooled down without holding the others back. A pass
    never outlasts its interval, and it gives its turn up rather than queue for the GPU
    behind a long analysis.
    """
    with observe_job(
        engine,
        job_name="embed_opportunities",
        interval=timedelta(seconds=interval_seconds),
    ):
        if adapter is None:
            logger.warning(
                "embedding batch degraded",
                extra={"job": "embed", "reason": "embedding_disabled"},
            )
            return
        if not admission.acquire(timeout=admission_timeout_seconds):
            logger.warning(
                "embedding pass skipped",
                extra={
                    "job": "embed",
                    "reason": "gpu_busy",
                    "waited_seconds": admission_timeout_seconds,
                },
            )
            return
        try:
            with Session(engine) as session:
                batch = embed_pending(
                    session,
                    adapter,
                    batch_size=batch_size,
                    time_budget_seconds=interval_seconds,
                )
        finally:
            admission.release()
        if not batch.selected:
            return
        with Session(engine) as session:
            backlog = count_pending_embeddings(session, model=adapter.model)
        summary = {
            "job": "embed",
            "model": adapter.model,
            "selected": batch.selected,
            "embedded": batch.embedded,
            "reused": batch.reused,
            "failed": batch.failed,
            "skipped": batch.skipped,
            "backlog": backlog,
            "failures": batch.failures,
        }
        if batch.degraded is not None:
            logger.warning(
                "embedding batch degraded",
                extra={**summary, "reason": batch.degraded.value},
            )
        else:
            logger.info("embedding batch finished", extra=summary)


def expire_raw_payloads(
    engine: Engine,
    *,
    retention_days: int = 365,
    batch_size: int = 500,
    interval_seconds: int = 21600,
    now: datetime | None = None,
) -> None:
    """Drop raw bodies the policy has released, and account for every one of them."""
    with observe_job(
        engine,
        job_name="expire_raw_payloads",
        interval=timedelta(seconds=interval_seconds),
    ):
        with Session(engine) as session:
            outcome = PayloadRetentionService(
                session, retention_days=retention_days, batch_size=batch_size
            ).expire_due_payloads(now=now)
        if outcome.expired:
            logger.info(
                "retention batch finished",
                extra={
                    "job": "retention",
                    "examined": outcome.examined,
                    "expired": outcome.expired,
                    "policy_version": outcome.policy_version,
                    "retention_days": outcome.retention_days,
                },
            )


def collect_enabled_sources(
    engine: Engine,
    *,
    timezone: str = "UTC",
    now: datetime | None = None,
    backoff_base_seconds: float = 300.0,
    backoff_ceiling_seconds: float = 86400.0,
    service_factory: Callable[[Session], AcquisitionService] = AcquisitionService,
) -> None:
    """Run every eligible source whose schedule is due, and account for the ones that are not.

    Each eligible source ends the pass in exactly one bucket. Silence about a source that
    did not run is what makes partial coverage look like full coverage, so a skip and a
    block are reported as deliberately as a failure.
    """
    moment = now or datetime.now(ZoneInfo(timezone))
    backoff_base = timedelta(seconds=backoff_base_seconds)
    backoff_ceiling = timedelta(seconds=backoff_ceiling_seconds)
    with observe_job(
        engine, job_name="collect_enabled_sources", interval=timedelta(seconds=60)
    ) as correlation_id:
        with Session(engine) as session:
            service = service_factory(session)
            sources, _ = service.list_sources(offset=0, limit=100)
            summary = {"completed": 0, "failed": 0, "skipped": 0, "blocked": 0}
            for source in sources:
                # A disabled source is not eligible, and a manual one has no clock.
                if not source.enabled or source.source_type == "manual":
                    continue
                try:
                    gate = evaluate_gate(
                        service.scheduling_state(source, timezone=timezone),
                        now=moment,
                        backoff_base=backoff_base,
                        backoff_ceiling=backoff_ceiling,
                    )
                except Exception:
                    session.rollback()
                    summary["failed"] += 1
                    logger.exception(
                        "source scheduling could not be evaluated",
                        extra={"job": "collect", "source_id": str(source.id)},
                    )
                    continue
                if gate is not CollectionGate.DUE:
                    summary[gate.outcome] += 1
                    logger.info(
                        "scheduled collection did not run",
                        extra={
                            "job": "collect",
                            "source_id": str(source.id),
                            "outcome": gate.outcome,
                            "gate": gate.value,
                        },
                    )
                    continue
                try:
                    run = run_async(
                        service.execute(
                            source.id,
                            _scheduled_request(service, source, correlation_id),
                        )
                    )
                except Exception:
                    # One unreachable source must not cost the others their pass.
                    session.rollback()
                    summary["failed"] += 1
                    logger.exception(
                        "scheduled collection failed",
                        extra={"job": "collect", "source_id": str(source.id)},
                    )
                    continue
                if run.complete:
                    # Closure compares this run's occurrences against the previous complete
                    # run, so its items must be normalized first: an occurrence that has
                    # not been touched yet would read as absent and close by mistake.
                    try:
                        opportunity_service = OpportunityService(session)
                        opportunity_service.normalize_run(run.id)
                        opportunity_service.reconcile_run_closures(run.id)
                    except Exception:
                        session.rollback()
                        logger.exception(
                            "run closure reconciliation failed",
                            extra={"job": "collect", "source_id": str(source.id)},
                        )
                outcome = "failed" if run.status == "FAILED" else "completed"
                summary[outcome] += 1
                logger.info(
                    "scheduled collection finished",
                    extra={
                        "job": "collect",
                        "source_id": str(source.id),
                        "outcome": outcome,
                        "run_status": run.status,
                        "items_persisted": run.items_persisted,
                    },
                )
            if any(summary.values()):
                logger.info(
                    "collection batch finished", extra={"job": "collect", **summary}
                )


def collection_service_factory(settings: Settings) -> Callable[[Session], AcquisitionService]:
    """Build the collectors once per worker, with the endpoints this deployment points at."""
    registry = build_collector_registry(
        greenhouse_base_url=settings.greenhouse_base_url,
        tavily_api_key=settings.tavily_api_key,
        tavily_base_url=settings.tavily_base_url,
        tavily_search_depth=settings.tavily_search_depth,
    )
    notifier = build_source_alert_notifier(
        settings.source_alert_webhook_url,
        timeout_seconds=settings.source_alert_timeout_seconds,
    )

    def build(session: Session) -> AcquisitionService:
        return AcquisitionService(
            session,
            registry=registry,
            alerts=SourceAlertService(
                session,
                notifier=notifier,
                threshold=settings.source_alert_failure_threshold,
            ),
        )

    return build


def _scheduled_request(
    service: AcquisitionService,
    source: SourceDefinitionModel,
    correlation_id: str,
) -> CollectionRequest:
    """Build the request from what this collector can actually accept.

    Sending keywords to a board that has no keyword search is rejected as an invalid
    configuration, which would report the source as broken when it is merely narrower than
    Remotive — so the capability decides, not the stored configuration.
    """
    collector = service.registry.resolve(source.source_type)
    configured = source.configuration.get("keywords", ())
    keywords = (
        tuple(configured)
        if isinstance(configured, list) and all(isinstance(item, str) for item in configured)
        else ()
    )
    return CollectionRequest(
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


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.collection_timezone)
    engine = create_database_engine(settings.database_url)
    # An interval trigger fires one interval after startup, which leaves every functional
    # job with no observable state for its first minute — indistinguishable, to the doctor
    # and to an operator, from a job that was never registered. Each job therefore takes a
    # first pass immediately; they are idempotent, coalesced and capped to one instance.
    first_run = datetime.now(ZoneInfo(settings.collection_timezone))
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
            next_run_time=first_run,
        )
    if settings.worker_collect_enabled:
        scheduler.add_job(
            collect_enabled_sources,
            "interval",
            seconds=60,
            args=(engine,),
            kwargs={
                "timezone": settings.collection_timezone,
                "backoff_base_seconds": settings.collection_backoff_base_seconds,
                "backoff_ceiling_seconds": settings.collection_backoff_ceiling_seconds,
                "service_factory": collection_service_factory(settings),
            },
            id="collect-enabled-sources",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=first_run,
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
            next_run_time=first_run,
        )
    if settings.worker_analyze_enabled:
        # One adapter for both jobs: it remembers when it last reached the model.
        adapter = build_analysis_adapter(settings)
        if settings.ollama_analysis_enabled:
            # One-off, so it stays out of FUNCTIONAL_JOB_IDS.
            scheduler.add_job(
                warm_up_models,
                "date",
                run_date=first_run,
                args=(adapter,),
                id="warm-up-models",
                replace_existing=True,
                # A one-off that misses its instant is dropped, not deferred, by default.
                misfire_grace_time=None,
            )
        scheduler.add_job(
            analyze_pending,
            "interval",
            seconds=120,
            args=(engine, adapter),
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
            next_run_time=first_run,
        )
    if settings.worker_retention_enabled:
        scheduler.add_job(
            expire_raw_payloads,
            "interval",
            seconds=settings.payload_retention_interval_seconds,
            args=(engine,),
            kwargs={
                "retention_days": settings.payload_retention_days,
                "batch_size": settings.payload_retention_batch_size,
                "interval_seconds": settings.payload_retention_interval_seconds,
            },
            id="expire-raw-payloads",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            # Six hours is the cadence, not the wait before the first pass: a job whose
            # state only appears after six hours reads to the doctor as a job that is
            # missing, which is the one thing operational state exists to rule out.
            next_run_time=first_run,
        )
    if settings.worker_embed_enabled:
        # Registered even with embedding switched off (`None` adapter): the pass then says
        # so in the log, which a job that is simply absent never would.
        scheduler.add_job(
            embed_opportunities,
            "interval",
            seconds=settings.worker_embed_interval_seconds,
            args=(engine, build_embedding_adapter(settings)),
            kwargs={
                "batch_size": settings.worker_embed_batch_size,
                "interval_seconds": settings.worker_embed_interval_seconds,
            },
            id="embed-opportunities",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=first_run,
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
