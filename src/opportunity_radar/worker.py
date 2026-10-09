from __future__ import annotations

import hashlib
import signal
from asyncio import run as run_async
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock
from time import monotonic
from uuid import UUID
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
from opportunity_radar.acquisition.models import (
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.scheduling import (
    CollectionGate,
    evaluate_gate,
    next_due_at,
)
from opportunity_radar.acquisition.service import (
    AcquisitionService,
    SourceClaimedElsewhereError,
    active_profile_target_role_families,
    budget_host_for_source,
)
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyExtractionSettings
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import (
    AnalysisStatus,
    SemanticAnalysisPort,
)
from opportunity_radar.matching.service import (
    DEFAULT_ANALYSIS_VERDICTS,
    AnalysisInProgressError,
    MatchingService,
    is_reused_analysis,
)
from opportunity_radar.operations.assessment_retention import prune_superseded_assessments
from opportunity_radar.operations.retention import PayloadRetentionService
from opportunity_radar.operations.service import annotate_pass, observe_job
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.opportunities.suggestions import (
    candidates_needing_suggestion,
    load_classification_prompt,
    suggest_fields,
)
from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.config import AIState, ai_status
from opportunity_radar.platform.ai.providers.routed import build_provider
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.ai.telemetry import purge_older_than
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.logging import (
    configure_logging,
    get_logger,
)
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.keywords import (
    KeywordRotationState,
    derive_keywords,
    rotate,
)
from opportunity_radar.profile.service import ProfileService

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
    "suggest_fields_pending": "suggest-fields-pending",
}

logger = get_logger("opportunity_radar.worker")


def heartbeat() -> None:
    """Expose a lightweight scheduler liveness job."""
    logger.debug("worker heartbeat")


def normalize_opportunities(
    engine: Engine, *, stop_requested: Callable[[], bool] | None = None
) -> dict[str, int]:
    """Each pass gets its own correlation id, so one batch is greppable end to end."""
    if stop_requested is not None and stop_requested():
        return {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 1}
    with observe_job(
        engine, job_name="normalize_opportunities", interval=timedelta(seconds=60)
    ):
        with Session(engine) as session:
            try:
                service = OpportunityService(session)
                totals = {"processed": 0, "succeeded": 0, "review_required": 0, "failed": 0}
                remaining = 100
                while remaining and (stop_requested is None or not stop_requested()):
                    batch = service.normalize_pending(
                        limit=1 if stop_requested is not None else remaining
                    )
                    totals["processed"] += batch.processed
                    totals["succeeded"] += batch.succeeded
                    totals["review_required"] += batch.review_required
                    totals["failed"] += batch.failed
                    remaining -= batch.processed
                    if not batch.processed:
                        break
            except Exception:
                logger.exception("normalization batch failed", extra={"job": "normalize"})
                raise
        if totals["processed"]:
            logger.info(
                "normalization batch finished",
                extra={
                    "job": "normalize",
                    **totals,
                },
            )
        return {
            "input": totals["processed"],
            "completed": totals["succeeded"],
            "failed": totals["failed"],
            "skipped": totals["review_required"],
            "stopped": int(stop_requested is not None and stop_requested()),
        }


def _operational_owner(owner_sub: str | None, *, job: str) -> str | None:
    owner = ProfileService.operational_owner(owner_sub)
    if owner is None:
        logger.warning(
            "worker job skipped: no operational owner configured",
            extra={"job": job, "reason": "missing_worker_owner"},
        )
    return owner


def evaluate_pending(
    engine: Engine,
    *,
    batch_size: int = 50,
    owner_sub: str | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Evaluate each eligible opportunity independently for the current identity."""
    owner = _operational_owner(owner_sub, job="evaluate")
    if owner is None:
        return {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0}
    if stop_requested is not None and stop_requested():
        return {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 1}
    with observe_job(
        engine, job_name="evaluate_pending", interval=timedelta(seconds=60)
    ):
        with Session(engine) as session:
            service = MatchingService(session, owner)
            try:
                pending_ids = service.pending_evaluation_ids(limit=batch_size)
            except ProfileNotFoundError:
                # A missing active profile is an expected degraded operating state.
                logger.warning(
                    "matching batch degraded",
                    extra={"job": "evaluate", "reason": "no_active_profile"},
                )
                return {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0}
            completed = failed = 0
            stopped = 0
            for opportunity_id in pending_ids:
                if stop_requested is not None and stop_requested():
                    stopped = 1
                    break
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
            return {
                "input": len(pending_ids),
                "completed": completed,
                "failed": failed,
                "skipped": max(0, len(pending_ids) - completed - failed),
                "stopped": stopped,
            }


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
    aging_sample_ratio: float = 0.0,
    worker_requests_ceiling: int | None = None,
    daily_cap_fraction: float | None = None,
    owner_sub: str | None = None,
) -> None:
    """Attach the semantic layer to current assessments, one claim at a time.

    The adapter classifies its own failures instead of raising, so a provider that is
    down degrades this job alone: evaluation keeps running and the failure is persisted
    as the history entry that the cooldown then reads.

    `worker_requests_ceiling`, when given, is a day-request budget lower than the
    adapter's own `QuotaGuard` limit (`settings.ai_daily_requests_soft_limit -
    ai_interactive_reserve_requests`, card F20-24): before each call, a probe
    reservation of the primary model's per-call token estimate (F48-02) checks the day
    counter against it and is released immediately either way,
    so the check never itself consumes quota. An assessment that fails the probe is
    skipped with no attempt recorded — the retry budget never counts a budget defer, and
    the opportunity is back in the next pass, not lost. The same ceiling also travels with
    the call (SPEC 51), where the router enforces it atomically on the real reservation;
    the probe stays because a denial there is recorded as a failed attempt.

    `daily_cap_fraction`, when given, stops the job for the day once the primary model's
    day-window token usage plus one probe estimate would pass that share of the daily
    token limit, leaving the rest as slack for interactive analysis (card F51-12). It is
    a read (`QuotaGuard.has_day_balance`), checked before the queue is read and before each
    item; reaching it writes nothing, so assessments stay pending in queue order for the
    next day window. An explicit analysis never goes through this job, so it is not capped.
    """
    owner = _operational_owner(owner_sub, job="analyze")
    if owner is None:
        return
    with observe_job(
        engine, job_name="analyze_pending", interval=timedelta(seconds=120)
    ) as correlation_id:
        quota_guard = getattr(adapter, "quota_guard", None)
        # The probe reserves what one call of the primary model can cost (0 for an
        # adapter that does not say): a zero-token probe passes with 100 tokens left
        # and the real call then fails as QUOTA_EXHAUSTED, one wasted attempt each.
        probe_tokens = int(getattr(adapter, "probe_tokens", 0) or 0)

        def under_daily_cap() -> bool:
            return (
                daily_cap_fraction is None
                or quota_guard is None
                or quota_guard.has_day_balance(
                    adapter.model,
                    estimated_tokens=probe_tokens,
                    token_fraction=daily_cap_fraction,
                )
            )

        if not under_daily_cap():
            logger.info(
                "analysis daily cap reached; assessments stay pending",
                extra={"job": "analyze", "reason": "daily_cap", "cap_fraction": daily_cap_fraction},
            )
            return
        with Session(engine) as session:
            service = MatchingService(session, owner)
            pending = service.pending_analysis_ids(
                limit=batch_size,
                eligible_verdicts=eligible_verdicts or DEFAULT_ANALYSIS_VERDICTS,
                cooldown=timedelta(seconds=cooldown_seconds),
                attempt_window=timedelta(seconds=attempt_window_seconds),
                max_attempts=max_attempts,
                aging_sample_ratio=aging_sample_ratio,
            )
            if pending:
                # After an idle stretch the provider connection may need re-warming
                # (a no-op for the cloud adapter); this keeps that cost out of the
                # first analysis of the batch.
                metrics = run_async(adapter.warm_up(only_if_idle=True))
                if metrics is not None:
                    logger.info(
                        "analysis model warmed up",
                        extra={"job": "warm-up", "reason": "idle", "load_ms": metrics.load_ms},
                    )
            completed = reused = degraded = claimed_elsewhere = failed = skipped_budget = 0
            skipped_daily_cap = 0
            for position, assessment_id in enumerate(pending):
                if not under_daily_cap():
                    skipped_daily_cap = len(pending) - position
                    logger.info(
                        "analysis daily cap reached; assessments stay pending",
                        extra={
                            "job": "analyze",
                            "reason": "daily_cap",
                            "cap_fraction": daily_cap_fraction,
                            "skipped_daily_cap": skipped_daily_cap,
                        },
                    )
                    break
                if worker_requests_ceiling is not None and quota_guard is not None:
                    probe = quota_guard.reserve(
                        adapter.model, probe_tokens, ceiling_requests=worker_requests_ceiling
                    )
                    if probe is None:
                        skipped_budget += 1
                        continue
                    quota_guard.release(probe)
                try:
                    analysis = run_async(
                        service.analyze(
                            assessment_id,
                            adapter,
                            owner=correlation_id,
                            lease=timedelta(seconds=lease_seconds),
                            quota_ceiling_requests=worker_requests_ceiling,
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
                        "skipped_budget": skipped_budget,
                        "skipped_daily_cap": skipped_daily_cap,
                        "failed": failed,
                    },
                )


def build_classification_router(settings: Settings, engine: Engine) -> AIRouter | None:
    """`AIRouter` wired for the `job_classification` task (card F20-23), or `None` when
    AI is disabled or missing its key (SPEC 43's `ai_status`, same gate the analysis
    adapter uses in `matching.adapters.build_analysis_adapter`). Built independently of
    that adapter — a router alone is enough here, there is no cache or evidence-checked
    parse to share with the semantic-analysis port.
    """
    state = ai_status(settings)
    if state is not AIState.ENABLED:
        return None
    provider = build_provider(settings)

    quota_guard = QuotaGuard(
        engine,
        QuotaLimits(
            minute_requests=settings.ai_minute_requests_soft_limit,
            minute_tokens=settings.ai_minute_tokens_soft_limit,
            day_requests=settings.ai_daily_requests_soft_limit,
            day_tokens=settings.ai_daily_tokens_soft_limit,
        ),
    )
    breaker = CircuitBreaker(
        failures=settings.ai_breaker_failures,
        cooldown_seconds=settings.ai_breaker_cooldown_seconds,
    )
    return AIRouter(
        provider,
        default_routes(settings),
        fallback_enabled=settings.ai_fallback_enabled,
        max_retries=settings.ai_max_retries,
        breaker=breaker,
        quota_guard=quota_guard,
    )


def suggest_fields_pending(
    engine: Engine,
    router: AIRouter | None,
    *,
    batch_size: int = 20,
    worker_requests_ceiling: int | None = None,
    owner_sub: str | None = None,
) -> None:
    """Suggest `role_family`/`seniority`/`work_mode` for opportunities the deterministic
    rules left `UNKNOWN` (card F20-23). Off by default (`worker_suggest_enabled`): the
    card requires measuring precision on a labelled sample before this job ever writes a
    suggestion outside a controlled run. Never touches the canonical column itself — an
    operator accepts or rejects each suggestion through the HTTP endpoints. Only postings
    with a top verdict under the active profile are taken (`candidates_needing_suggestion`).
    """
    owner = _operational_owner(owner_sub, job="suggest-fields")
    if owner is None:
        return
    if router is None:
        return
    with observe_job(
        engine, job_name="suggest_fields_pending", interval=timedelta(seconds=300)
    ):
        with Session(engine) as session:
            prompt = load_classification_prompt()
            route = router.route(AITask.JOB_CLASSIFICATION)
            route_hash = hashlib.sha256("\0".join(route.chain).encode()).hexdigest()
            # One read of the day windows decides the pass: with no balance on any model of
            # the chain every candidate would only leave an operation row and a defer.
            guard = router.quota_guard
            if guard is not None:
                estimated = route.budget.max_input_tokens + route.budget.max_output_tokens
                if not any(
                    guard.has_day_balance(
                        model,
                        estimated_tokens=estimated,
                        ceiling_requests=worker_requests_ceiling,
                    )
                    for model in route.chain
                ):
                    logger.info(
                        "suggest fields skipped: no day quota on any route model",
                        extra={"job": "suggest-fields", "reason": "no_quota"},
                    )
                    return
            candidates = candidates_needing_suggestion(
                session,
                limit=batch_size,
                owner_sub=owner,
                prompt_version=prompt.version,
                route_hash=route_hash,
                prompt=prompt,
                route=route,
            )
            created = discarded = skipped_budget = failed = attempted = 0
            failure_classes = Counter[str]()
            stopped_by: str | None = None
            for opportunity in candidates:
                attempted += 1
                try:
                    outcome = run_async(
                        suggest_fields(
                            session,
                            router,
                            opportunity,
                            prompt=prompt,
                            quota_ceiling_requests=worker_requests_ceiling,
                        )
                    )
                except Exception:
                    session.rollback()
                    failed += 1
                    failure_classes["internal_error"] += 1
                    logger.exception(
                        "field suggestion failed",
                        extra={"job": "suggest-fields", "opportunity_id": str(opportunity.id)},
                    )
                    continue
                created += len(outcome.created)
                discarded += len(outcome.discarded_fields)
                if outcome.state == "deferred":
                    failure_classes["quota_defer"] += 1
                elif outcome.state in ("provider_error", "parse_error"):
                    failure_classes[outcome.state] += 1
                if outcome.quota_exhausted:
                    # Every remaining candidate would only leave an operation row and a defer.
                    stopped_by = "quota"
                    break
            if candidates:
                logger.info(
                    "suggest fields batch finished",
                    extra={
                        "job": "suggest-fields",
                        "processed": len(candidates),
                        "suggestions_created": created,
                        "discarded": discarded,
                        "skipped_budget": skipped_budget,
                        "failed": failed,
                        "failure_classes": dict(failure_classes),
                        "not_attempted": len(candidates) - attempted,
                        "stopped_by": stopped_by,
                    },
                )


def expire_raw_payloads(
    engine: Engine,
    *,
    retention_days: int = 365,
    batch_size: int = 500,
    interval_seconds: int = 21600,
    ai_call_record_retention_days: int | None = None,
    now: datetime | None = None,
) -> None:
    """Drop raw bodies the policy has released, and account for every one of them.

    `ai_call_record_retention_days` piggybacks on this same daily pass (card F20-19):
    the telemetry table carries no PII, so it only needs its own short retention, not a
    dedicated job.
    """
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
        if ai_call_record_retention_days is not None:
            purged = purge_older_than(engine, ai_call_record_retention_days, now=now)
            if purged:
                logger.info(
                    "ai call record retention batch finished",
                    extra={
                        "job": "retention",
                        "purged": purged,
                        "retention_days": ai_call_record_retention_days,
                    },
                )


def prune_match_assessments(
    engine: Engine,
    *,
    retention_days: int = 7,
    batch_size: int = 500,
    max_batches: int = 20,
    interval_seconds: int = 21600,
) -> None:
    """Delete superseded assessments, bounded per pass (card F50-08)."""
    with observe_job(
        engine,
        job_name="prune_match_assessments",
        interval=timedelta(seconds=interval_seconds),
    ):
        prune_superseded_assessments(
            engine,
            retention_days=retention_days,
            batch_size=batch_size,
            max_batches=max_batches,
            dry_run=False,
        )


@dataclass
class _PassSummary:
    """Per-bucket counts of one pass; the threads of a concurrent pass add to it safely."""

    counts: dict[str, int] = field(
        default_factory=lambda: {"completed": 0, "failed": 0, "skipped": 0, "blocked": 0}
    )
    _lock: Lock = field(default_factory=Lock, repr=False)

    def add(self, outcome: str, count: int = 1) -> None:
        with self._lock:
            self.counts[outcome] += count


@dataclass(frozen=True)
class _PassContext:
    """What one source needs to know about the pass it runs in."""

    correlation_id: str
    timezone: str
    now: datetime | None
    utc_clock: Callable[[], datetime] | None
    backoff_base: timedelta
    backoff_ceiling: timedelta
    source_deadline_seconds: float
    pass_deadline_seconds: float
    pass_started: float
    monotonic_clock: Callable[[], float]
    summary: _PassSummary
    stop_requested: Callable[[], bool] | None = None


def _collect_one_source(
    session: Session,
    service: AcquisitionService,
    source: SourceDefinitionModel,
    ctx: _PassContext,
) -> None:
    """Judge one source and, when due, run it. A source's own failure is counted, not raised."""
    timezone = ctx.timezone
    summary = ctx.summary
    now = ctx.now
    utc_clock = ctx.utc_clock
    backoff_base = ctx.backoff_base
    backoff_ceiling = ctx.backoff_ceiling
    pass_deadline_seconds = ctx.pass_deadline_seconds
    source_deadline_seconds = ctx.source_deadline_seconds
    pass_started = ctx.pass_started
    monotonic_clock = ctx.monotonic_clock
    correlation_id = ctx.correlation_id
    if ctx.stop_requested is not None and ctx.stop_requested():
        summary.add("skipped")
        return
    moment = now or (
        utc_clock() if utc_clock is not None else datetime.now(ZoneInfo(timezone))
    )
    pass_remaining = (
        pass_deadline_seconds - (monotonic_clock() - pass_started)
        if pass_deadline_seconds > 0
        else None
    )
    if pass_remaining is not None and pass_remaining <= 0:
        summary.add("skipped")
        logger.info(
            "scheduled collection skipped",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "outcome": "skipped",
                "reason": "pass_deadline",
            },
        )
        return
    try:
        # Read once per source, right before it is judged: the host's shared
        # budget (F20-38) is state committed by whichever earlier source in
        # this same pass already spent against it, so re-reading it here (not
        # once for the whole pass) is what keeps the running total correct
        # without one failing source blocking the others on its host.
        state = service.scheduling_state(source, timezone=timezone)
        gate = evaluate_gate(
            state,
            now=moment,
            backoff_base=backoff_base,
            backoff_ceiling=backoff_ceiling,
        )
    except Exception:
        session.rollback()
        summary.add("failed")
        logger.exception(
            "source scheduling could not be evaluated",
            extra={"job": "collect", "source_id": str(source.id)},
        )
        return
    if gate is not CollectionGate.DUE:
        summary.add(gate.outcome)
        _, reason = next_due_at(
            state,
            now=moment,
            backoff_base=backoff_base,
            backoff_ceiling=backoff_ceiling,
        )
        logger.info(
            "scheduled collection did not run",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "outcome": gate.outcome,
                "gate": gate.value,
                "reason": reason,
                "host": state.host,
            },
        )
        return
    request: CollectionRequest | None = None
    try:
        request, rotation_state, term_count = _scheduled_request_with_rotation(
            service, source, correlation_id
        )
        pass_remaining = (
            pass_deadline_seconds - (monotonic_clock() - pass_started)
            if pass_deadline_seconds > 0
            else None
        )
        if pass_remaining is not None and pass_remaining <= 0:
            summary.add("skipped")
            logger.info(
                "scheduled collection skipped",
                extra={
                    "job": "collect",
                    "source_id": str(source.id),
                    "outcome": "skipped",
                    "reason": "pass_deadline",
                },
            )
            return
        if ctx.stop_requested is not None and ctx.stop_requested():
            summary.add("skipped")
            return
        source_started = monotonic_clock()
        source_timeout = source_deadline_seconds or None
        if pass_remaining is not None:
            source_timeout = min(
                source_timeout
                if source_timeout is not None
                else pass_remaining,
                pass_remaining,
            )
        logger.info(
            "scheduled collection started",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "deadline_seconds": source_timeout,
            },
        )
        run = run_async(
            service.execute(
                source.id, request, deadline_seconds=source_timeout
            )
        )
        if rotation_state is not None:
            _advance_keyword_rotation_checkpoint(
                service, source, run, rotation_state, term_count=term_count
            )
    except SourceClaimedElsewhereError:
        # Another execution (CLI/API/previous pass) owns this source right now.
        # It made no request, so it is a skip, not a failure.
        session.rollback()
        summary.add("skipped")
        logger.info(
            "scheduled collection skipped",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "outcome": "skipped",
                "reason": "claimed_elsewhere",
            },
        )
        return
    except Exception:
        # One unreachable source must not cost the others their pass.
        session.rollback()
        summary.add("failed")
        logger.exception(
            "scheduled collection failed",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "terms_used": list(request.keywords) if request is not None else [],
            },
        )
        return
    if run.complete:
        # Closure compares this run's occurrences against the previous complete
        # run, so its items must be normalized first: an occurrence that has
        # not been touched yet would read as absent and close by mistake.
        try:
            opportunity_service = OpportunityService(session)
            opportunity_service.normalize_run(run.id)
            opportunity_service.reconcile_run_closures(
                run.id, may_close=service.run_may_close_absences
            )
        except Exception:
            session.rollback()
            logger.exception(
                "run closure reconciliation failed",
                extra={"job": "collect", "source_id": str(source.id)},
            )
    outcome = "failed" if run.status == "FAILED" else "completed"
    summary.add(outcome)
    logger.info(
        "scheduled collection finished",
        extra={
            "job": "collect",
            "source_id": str(source.id),
            "outcome": outcome,
            "run_status": run.status,
            "run_id": str(run.id),
            "terms_used": list(request.keywords) if request is not None else [],
            "items_persisted": run.items_persisted,
            "duration_ms": round(
                (monotonic_clock() - source_started) * 1000
            ),
            "last_activity_at": datetime.now(ZoneInfo(timezone)).isoformat(),
        },
    )


def _collect_host_group(
    engine: Engine,
    service_factory: Callable[[Session], AcquisitionService],
    source_ids: list[UUID],
    ctx: _PassContext,
) -> None:
    """Run the sources of one host, one after another, on this thread's own session.

    The session, the service and each run's HTTP client belong to this thread alone; the
    only state shared with the other threads is the database. A group that cannot even
    start counts its unreached sources as failed and leaves the other hosts alone.
    """
    reached = 0
    try:
        if ctx.stop_requested is not None and ctx.stop_requested():
            ctx.summary.add("skipped", len(source_ids))
            return
        with Session(engine) as session:
            service = service_factory(session)
            for source_id in source_ids:
                if ctx.stop_requested is not None and ctx.stop_requested():
                    ctx.summary.add("skipped", len(source_ids) - reached)
                    return
                reached += 1
                try:
                    source = service.get_source(source_id)
                except Exception:
                    session.rollback()
                    source = None
                if source is None:
                    ctx.summary.add("failed")
                    logger.error(
                        "source could not be loaded for collection",
                        extra={"job": "collect", "source_id": str(source_id)},
                    )
                    continue
                _collect_one_source(session, service, source, ctx)
    except Exception:
        logger.exception("collection host group failed", extra={"job": "collect"})
        for _ in source_ids[reached:]:
            ctx.summary.add("failed")


def collect_enabled_sources(
    engine: Engine,
    *,
    timezone: str = "UTC",
    now: datetime | None = None,
    backoff_base_seconds: float = 300.0,
    backoff_ceiling_seconds: float = 86400.0,
    source_deadline_seconds: float = 0.0,
    pass_deadline_seconds: float = 0.0,
    host_concurrency: int = 1,
    monotonic_clock: Callable[[], float] = monotonic,
    utc_clock: Callable[[], datetime] | None = None,
    service_factory: Callable[[Session], AcquisitionService] = AcquisitionService,
    owner_sub: str | None = None,
    stop_requested: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Run every eligible source whose schedule is due, and account for the ones that are not.

    Each eligible source ends the pass in exactly one bucket. Silence about a source that
    did not run is what makes partial coverage look like full coverage, so a skip and a
    block are reported as deliberately as a failure.

    With `host_concurrency` > 1 up to that many budget hosts are collected at once, each on
    its own thread and database session; the sources of one host always run one after the
    other, so a host never sees two runs at the same time. 1 is the original serial pass.
    """
    owner = _operational_owner(owner_sub, job="collect")
    if owner is None:
        return {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0}
    pass_started = monotonic_clock()
    with observe_job(
        engine, job_name="collect_enabled_sources", interval=timedelta(seconds=60)
    ) as correlation_id:
        summary = _PassSummary()
        ctx = _PassContext(
            correlation_id=correlation_id,
            timezone=timezone,
            now=now,
            utc_clock=utc_clock,
            backoff_base=timedelta(seconds=backoff_base_seconds),
            backoff_ceiling=timedelta(seconds=backoff_ceiling_seconds),
            source_deadline_seconds=source_deadline_seconds,
            pass_deadline_seconds=pass_deadline_seconds,
            pass_started=pass_started,
            monotonic_clock=monotonic_clock,
            summary=summary,
            stop_requested=stop_requested,
        )
        groups: dict[str, list[UUID]] = {}
        with Session(engine) as session:
            service = service_factory(session)
            # Not the paginated listing: a page cut dropped every eligible source past it (F48-01).
            sources = service.list_collectable_sources()
            if host_concurrency <= 1:
                for source in sources:
                    _collect_one_source(session, service, source, ctx)
            else:
                for source in sources:
                    host = budget_host_for_source(source.source_type, source.configuration)
                    groups.setdefault(host, []).append(source.id)
        if groups:
            _run_host_groups(
                engine, service_factory, list(groups.values()), ctx, host_concurrency
            )
        # F48-07: DUE sources = the ones that reached execution (or failed doing so).
        counts = summary.counts
        annotate_pass(
            engine,
            correlation_id,
            due_sources=counts["completed"] + counts["failed"],
            **counts,
        )
        if any(counts.values()):
            logger.info("collection batch finished", extra={"job": "collect", **counts})
        return {
            "input": sum(counts.values()),
            "completed": counts["completed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"] + counts["blocked"],
            "stopped": int(stop_requested is not None and stop_requested()),
        }


def _run_host_groups(
    engine: Engine,
    service_factory: Callable[[Session], AcquisitionService],
    groups: list[list[UUID]],
    ctx: _PassContext,
    host_concurrency: int,
) -> None:
    """Bounded pool over host groups: at most `host_concurrency` hosts in flight at once."""
    with ThreadPoolExecutor(
        max_workers=min(host_concurrency, len(groups)), thread_name_prefix="collect-host"
    ) as pool:
        for group in groups:
            pool.submit(_collect_host_group, engine, service_factory, group, ctx)


def collection_service_factory(settings: Settings) -> Callable[[Session], AcquisitionService]:
    """Build the collectors once per worker, with the endpoints this deployment points at."""
    owner = ProfileService.operational_owner(settings.worker_owner_sub)
    registry = build_collector_registry(
        greenhouse_base_url=settings.greenhouse_base_url,
        tavily_api_key=settings.tavily_api_key,
        tavily_base_url=settings.tavily_base_url,
        tavily_search_depth=settings.tavily_search_depth,
        tavily_credit_budget_per_run=settings.tavily_credit_budget_per_run,
    )
    notifier = build_source_alert_notifier(
        settings.source_alert_webhook_url,
        timeout_seconds=settings.source_alert_timeout_seconds,
    )
    # F20-45: fills in a missing description via Tavily `/extract` for any collector's
    # items, not only tavily_search's own. Disabled (None) the same way tavily_search
    # itself is when no API key is configured — a supported deployment, not an error.
    tavily_extraction = (
        TavilyExtractionSettings(
            client_factory=lambda: TavilyClient(
                api_key=settings.tavily_api_key,
                base_url=settings.tavily_base_url,
            ),
            cache_ttl_seconds=settings.tavily_extract_cache_ttl_seconds,
            credit_budget_per_run=settings.tavily_credit_budget_per_run,
            extract_depth=settings.tavily_extract_depth,
            format=settings.tavily_extract_format,
            skip_source_types=settings.extraction_skip_source_type_set,
            host_failure_threshold=settings.tavily_extract_host_failure_threshold,
        )
        if settings.tavily_api_key
        else None
    )

    def build(session: Session) -> AcquisitionService:
        if owner is None:
            raise ValueError("collection requires an explicit operational owner")
        target_roles = active_profile_target_role_families(session, owner)
        return AcquisitionService(
            session,
            registry=registry,
            alerts=SourceAlertService(
                session,
                notifier=notifier,
                threshold=settings.source_alert_failure_threshold,
            ),
            tavily_extraction=tavily_extraction,
            host_request_ceilings=settings.host_request_ceiling_map,
            target_role_families=target_roles,
            profile_owner_sub=owner,
            target_area_floor=settings.collection_target_area_floor,
            claims_enabled=settings.collection_claim_enabled,
            inventory_contract_enabled=settings.collection_inventory_contract_enabled,
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
    request, _, _ = _scheduled_request_with_rotation(service, source, correlation_id)
    return request


def _scheduled_request_with_rotation(
    service: AcquisitionService,
    source: SourceDefinitionModel,
    correlation_id: str,
) -> tuple[CollectionRequest, KeywordRotationState | None, int]:
    collector = service.registry.resolve(source.source_type)
    configured = source.configuration.get("keywords", ())
    configured_keywords = (
        tuple(configured)
        if isinstance(configured, list) and all(isinstance(item, str) for item in configured)
        else ()
    )
    rotation_state: KeywordRotationState | None = None
    term_count = 0
    if source.source_type == "remotive" and collector.capabilities.keyword_search:
        profile_keywords: tuple[str, ...] = ()
        owner = ProfileService.operational_owner(service.profile_owner_sub)
        if owner is not None:
            try:
                profile = ProfileService(service.session, owner).get_active()
            except ProfileNotFoundError:
                pass
            else:
                profile_keywords = derive_keywords(
                    profile.snapshot.preferences, profile.snapshot.skills
                )
        terms = _normalize_keywords((*profile_keywords, *configured_keywords))
        term_count = len(terms)
        checkpoint = source.checkpoint
        block_index = 0
        if (
            checkpoint is not None
            and checkpoint.checkpoint_type == "keyword_rotation"
            and checkpoint.cursor is not None
        ):
            try:
                block_index = max(0, int(checkpoint.cursor))
            except ValueError:
                block_index = 0
        keywords = rotate(terms, block_index=block_index)
        if keywords:
            rotation_state = KeywordRotationState(block_index, keywords)
    else:
        keywords = configured_keywords
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
    ), rotation_state, term_count


def _normalize_keywords(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(term.strip().casefold() for term in terms if term.strip()))


def _advance_keyword_rotation_checkpoint(
    service: AcquisitionService,
    source: SourceDefinitionModel,
    run: SourceRunModel,
    state: KeywordRotationState,
    *,
    term_count: int,
) -> bool:
    """Commit next block only after `execute` durably commits a successful run."""
    if run.status != "SUCCEEDED" or not state.terms_used or term_count == 0:
        return False
    checkpoint = service.session.get(SourceCheckpointModel, source.id)
    if checkpoint is None:
        checkpoint = SourceCheckpointModel(source_definition_id=source.id)
    block_count = (term_count + 9) // 10
    checkpoint.checkpoint_type = "keyword_rotation"
    checkpoint.cursor = str((state.block_index + 1) % block_count)
    checkpoint.promoted_by_run_id = run.id
    checkpoint.promoted_at = datetime.now(ZoneInfo("UTC"))
    service.session.add(checkpoint)
    service.session.commit()
    return True


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
                "source_deadline_seconds": settings.collection_source_deadline_seconds,
                "pass_deadline_seconds": settings.collection_pass_deadline_seconds,
                "host_concurrency": settings.collection_host_concurrency,
                "service_factory": collection_service_factory(settings),
                "owner_sub": settings.worker_owner_sub,
            },
            id="collect-enabled-sources",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=first_run,
        )
    if settings.worker_match_enabled:
        evaluate_kwargs: dict[str, object] = {"batch_size": settings.worker_evaluate_batch_size}
        if settings.worker_owner_sub:
            evaluate_kwargs["owner_sub"] = settings.worker_owner_sub
        scheduler.add_job(
            evaluate_pending,
            "interval",
            seconds=60,
            args=(engine,),
            kwargs=evaluate_kwargs,
            id="evaluate-pending",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=first_run,
        )
    if settings.worker_analyze_enabled:
        adapter = build_analysis_adapter(settings, engine)
        analyze_kwargs: dict[str, object] = {
            "batch_size": settings.worker_analyze_batch_size,
            "eligible_verdicts": settings.analysis_eligible_verdicts,
            "cooldown_seconds": settings.analysis_retry_cooldown_seconds,
            "attempt_window_seconds": settings.analysis_retry_attempt_window_seconds,
            "max_attempts": settings.analysis_retry_max_attempts,
            "lease_seconds": settings.analysis_claim_lease_seconds,
            "aging_sample_ratio": settings.worker_analyze_aging_sample_ratio,
            "daily_cap_fraction": settings.worker_analyze_daily_cap_fraction,
            "worker_requests_ceiling": (
                settings.ai_daily_requests_soft_limit
                - settings.ai_interactive_reserve_requests
            ),
        }
        if settings.worker_owner_sub:
            analyze_kwargs["owner_sub"] = settings.worker_owner_sub
        scheduler.add_job(
            analyze_pending,
            "interval",
            seconds=120,
            args=(engine, adapter),
            kwargs=analyze_kwargs,
            id="analyze-pending",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            next_run_time=first_run,
        )
    if settings.worker_suggest_enabled:
        classification_router = build_classification_router(settings, engine)
        suggest_kwargs: dict[str, object] = {
            "batch_size": settings.worker_suggest_batch_size,
            "worker_requests_ceiling": (
                settings.ai_daily_requests_soft_limit
                - settings.ai_interactive_reserve_requests
            ),
        }
        if settings.worker_owner_sub:
            suggest_kwargs["owner_sub"] = settings.worker_owner_sub
        scheduler.add_job(
            suggest_fields_pending,
            "interval",
            seconds=300,
            args=(engine, classification_router),
            kwargs=suggest_kwargs,
            id="suggest-fields-pending",
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
                "ai_call_record_retention_days": settings.ai_call_record_retention_days,
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
    # Not in FUNCTIONAL_JOB_IDS: it is off by default, and that map is what the doctor and
    # the soak gate expect to find running.
    if settings.worker_assessment_retention_enabled:
        scheduler.add_job(
            prune_match_assessments,
            "interval",
            seconds=settings.payload_retention_interval_seconds,
            args=(engine,),
            kwargs={
                "retention_days": settings.assessment_retention_days,
                "batch_size": settings.assessment_retention_batch_size,
                "interval_seconds": settings.payload_retention_interval_seconds,
            },
            id="prune-match-assessments",
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
