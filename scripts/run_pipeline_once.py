"""Run one finite collection/normalization/evaluation/analysis(/daily retention) window and exit."""

from __future__ import annotations

import argparse
import json
from time import monotonic

from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.operations.data_reduction import (
    DataReductionReport,
    check_database_size,
    run_data_reduction,
)
from opportunity_radar.operations.opportunity_retention import (
    DRY_RUN_JOB_NAME,
    JOB_NAME,
    record_retention_attempt,
    retention_due,
    run_opportunity_retention,
)
from opportunity_radar.platform.ai.config import AIState, ai_status
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.logging import get_logger
from opportunity_radar.platform.pipeline import (
    ANALYZE_STAGE,
    ConfigurationError,
    ExitCode,
    PostgresWindowClaim,
    StageContext,
    StageCounts,
    StageSpec,
    StopSignal,
    describe_pipeline,
    run_pipeline,
    signal_stop,
    validate_owner,
)
from opportunity_radar.worker import (
    analyze_pending,
    collect_enabled_sources,
    evaluate_pending,
    normalize_opportunities,
)

#: Daily job name of the size watch that runs while the opportunity retention is off.
SIZE_JOB_NAME = "database_size_check"

logger = get_logger("opportunity_radar.scripts.run_pipeline_once")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def analyze_window_cap(settings: Settings) -> int:
    """Assessments one window may analyse: the day's request ceiling spread over its windows.

    The ceiling is the soft day limit minus the interactive reserve (the free Groq quota is
    1,000 requests a day on the 120b model), so 24 hourly windows cannot spend more than
    the worker's share between them (R55-C1). At least 1, so a tiny ceiling still moves.
    """
    ceiling = settings.ai_daily_requests_soft_limit - settings.ai_interactive_reserve_requests
    return max(1, ceiling // settings.pipeline_analyze_windows_per_day)


def _stages(engine, settings, measurements: dict[str, object] | None = None) -> list[StageSpec]:
    measurements = measurements if measurements is not None else {}

    def counts(result: dict[str, int]) -> StageCounts:
        return StageCounts(
            input=result["input"],
            completed=result["completed"],
            failed=result["failed"],
            skipped=result["skipped"],
            stopped=result["stopped"],
            metrics={
                key: result[key] for key in ("eligible", "executed") if key in result
            },
        )

    def collect(context: StageContext) -> StageCounts:
        return counts(
            collect_enabled_sources(
                engine,
                timezone=settings.collection_timezone,
                backoff_base_seconds=settings.collection_backoff_base_seconds,
                backoff_ceiling_seconds=settings.collection_backoff_ceiling_seconds,
                source_deadline_seconds=settings.collection_source_deadline_seconds,
                pass_deadline_seconds=min(
                    settings.collection_pass_deadline_seconds or context.deadline.remaining(),
                    context.deadline.remaining(),
                ),
                host_concurrency=settings.collection_host_concurrency,
                owner_sub=context.owner_sub,
                stop_requested=context.should_stop,
                manual_min_interval_hours=settings.manual_source_min_interval_hours,
            )
        )

    def normalize(context: StageContext) -> StageCounts:
        if context.should_stop():
            return StageCounts(stopped=1)
        return counts(normalize_opportunities(engine, stop_requested=context.should_stop))

    def evaluate(context: StageContext) -> StageCounts:
        if context.should_stop():
            return StageCounts(stopped=1)
        return counts(
            evaluate_pending(
                engine,
                batch_size=settings.worker_evaluate_batch_size,
                owner_sub=context.owner_sub,
                stop_requested=context.should_stop,
            )
        )

    def analyze(context: StageContext) -> StageCounts:
        # R55-C1: gated by the kill switch and AI_ENABLED (with its key) before anything is
        # built; a window with no quota left or no eligible verdict is a clean no-op.
        if context.should_stop():
            return StageCounts(stopped=1)
        if not settings.worker_analyze_enabled or ai_status(settings) is not AIState.ENABLED:
            return StageCounts(skipped=1, metrics={"ai_disabled": 1})
        cap = analyze_window_cap(settings)
        return counts(
            analyze_pending(
                engine,
                build_analysis_adapter(settings, engine),
                batch_size=cap,
                eligible_verdicts=settings.analysis_eligible_verdicts,
                cooldown_seconds=settings.analysis_retry_cooldown_seconds,
                attempt_window_seconds=settings.analysis_retry_attempt_window_seconds,
                max_attempts=settings.analysis_retry_max_attempts,
                lease_seconds=settings.analysis_claim_lease_seconds,
                aging_sample_ratio=settings.worker_analyze_aging_sample_ratio,
                daily_cap_fraction=settings.worker_analyze_daily_cap_fraction,
                worker_requests_ceiling=(
                    settings.ai_daily_requests_soft_limit
                    - settings.ai_interactive_reserve_requests
                ),
                owner_sub=context.owner_sub,
                stop_requested=context.should_stop,
            )
        )

    def retention(context: StageContext) -> StageCounts:
        # Nothing in the retention slot may block collection: any exception, from the due
        # check to the bookkeeping, becomes a failed count, and either kind of failure is
        # surfaced as `retention_failed` plus a nonzero exit once every stage has run.
        try:
            counts = retention_body(context)
        except Exception as error:
            logger.error("retention stage failed", extra={"error": type(error).__name__})
            counts = StageCounts(input=1, failed=1)
        if counts.failed:
            measurements["retention_failed"] = True
        return counts

    def retention_body(context: StageContext) -> StageCounts:
        # R55-E2/E6: at most one run per UTC day, and FIRST in the window so that the short
        # hourly window always reaches it; it has its own budget (RETENTION_STAGE_BUDGET_
        # SECONDS) so collection still runs, and a failure here never blocks collection.
        # 0 days is the off switch for deletions, never for the 1 GB size watch.
        # Deleting needs the owner's explicit OPPORTUNITY_RETENTION_APPLY=true; until then
        # the stage only counts, and that dry run is tracked apart from applied runs.
        budget_ends_at = monotonic() + settings.retention_stage_budget_seconds

        def budget_spent() -> bool:
            return monotonic() >= budget_ends_at

        def should_stop() -> bool:
            return context.should_stop() or budget_spent()

        if settings.opportunity_retention_days <= 0:
            return size_only(context)
        apply = bool(settings.opportunity_retention_apply)
        job_name = JOB_NAME if apply else DRY_RUN_JOB_NAME
        if not retention_due(engine, job_name=job_name):
            return StageCounts(skipped=1)
        if context.should_stop():
            return StageCounts(stopped=1)
        try:
            report = run_opportunity_retention(
                engine,
                retention_days=settings.opportunity_retention_days,
                batch_size=settings.opportunity_retention_batch_size,
                ai_call_record_retention_days=settings.ai_call_record_retention_days,
                dry_run=not apply,
                should_stop=should_stop,
            )
            # R55-E6: payload expiry, superseded-assessment pruning and the size check share
            # this daily slot and the same apply gate (dry run only counts). Skipped when the
            # retention above already stopped or failed, so the day stays open for a retry.
            if not report.stopped and not report.errors:
                reduction = run_data_reduction(
                    engine,
                    apply=apply,
                    payload_retention_days=settings.payload_retention_days,
                    payload_batch_size=settings.payload_retention_batch_size,
                    assessment_retention_days=settings.assessment_retention_days,
                    assessment_batch_size=settings.assessment_retention_batch_size,
                    size_limit_bytes=settings.database_size_limit_bytes,
                    size_alert_ratio=settings.database_size_alert_ratio,
                    should_stop=should_stop,
                )
                _note_size(reduction)
                report.stopped = report.stopped or reduction.stopped
                report.errors.update({f"reduction_{k}": v for k, v in reduction.errors.items()})
                report.complete = report.complete and reduction.complete
        except Exception as error:
            try:
                record_retention_attempt(
                    engine, success=False, error=type(error).__name__, job_name=job_name
                )
            except Exception:  # never mask the original error
                pass
            ensure_size()
            # Logged and counted, not raised: a raising first stage would skip collection.
            logger.error("retention stage failed", extra={"error": type(error).__name__})
            return StageCounts(input=1, failed=1)
        # The 70% warning must fire during a backlog too, so measure whatever happened above.
        ensure_size()
        if not apply:
            # Per-table counts only, for the owner to read before enabling the apply flag.
            logger.info(
                "opportunity retention dry run",
                extra={"job": JOB_NAME, "rows": dict(sorted(report.rows.items()))},
            )
        if report.stopped:
            # The day stays open for the next window. Only the stage's own budget running
            # out is not a pipeline stop: collection must still run.
            if context.should_stop():
                return StageCounts(input=1, stopped=1)
            return StageCounts(input=1, skipped=1)
        if report.errors:
            record_retention_attempt(
                engine,
                success=False,
                error=",".join(sorted(report.errors)),
                job_name=job_name,
            )
            return StageCounts(input=1, failed=1)
        record_retention_attempt(engine, success=report.complete, job_name=job_name)
        return StageCounts(input=1, completed=int(report.complete))

    def ensure_size() -> None:
        if "database_size_bytes" in measurements:
            return
        try:
            _note_size(
                check_database_size(
                    engine,
                    size_limit_bytes=settings.database_size_limit_bytes,
                    size_alert_ratio=settings.database_size_alert_ratio,
                )
            )
        except Exception as error:  # a watch failure never fails the stage
            logger.warning("size check failed", extra={"error": type(error).__name__})

    def size_only(context: StageContext) -> StageCounts:
        # Retention is off, but the size watch runs once per UTC day on its own job name.
        if not retention_due(engine, job_name=SIZE_JOB_NAME):
            return StageCounts(skipped=1)
        if context.should_stop():
            return StageCounts(stopped=1)
        reduction = check_database_size(
            engine,
            size_limit_bytes=settings.database_size_limit_bytes,
            size_alert_ratio=settings.database_size_alert_ratio,
        )
        _note_size(reduction)
        ok = not reduction.errors
        record_retention_attempt(
            engine,
            success=ok,
            error=None if ok else ",".join(sorted(reduction.errors)),
            job_name=SIZE_JOB_NAME,
        )
        return StageCounts(input=1, completed=int(ok), failed=int(not ok))

    def _note_size(reduction: DataReductionReport) -> None:
        if reduction.database_size_bytes is not None:
            measurements["database_size_bytes"] = reduction.database_size_bytes
            measurements["database_size_alert"] = reduction.size_alert

    return [
        StageSpec("retention", retention),
        StageSpec("collect_enabled_sources", collect),
        StageSpec("normalize_opportunities", normalize),
        StageSpec("evaluate_pending", evaluate),
        StageSpec(ANALYZE_STAGE, analyze),
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = get_settings()
    try:
        owner = validate_owner(settings.worker_owner_sub)
        if args.dry_run:
            print(
                json.dumps(
                    describe_pipeline(owner_sub=owner, deadline_seconds=args.deadline_seconds),
                    sort_keys=True,
                )
            )
            return 0
        engine = create_database_engine(settings.database_url)
        stop = StopSignal()
        with signal_stop(stop):
            measurements: dict[str, object] = {}
            report = run_pipeline(
                _stages(engine, settings, measurements),
                owner_sub=owner,
                deadline_seconds=args.deadline_seconds,
                claim_factory=lambda: PostgresWindowClaim(engine),
                stop=stop,
            )
        # database_size_* appear only in the window that measured them (once per UTC day).
        print(json.dumps({**report.to_dict(), **measurements}, sort_keys=True))
        if measurements.get("retention_failed") and report.exit_code == ExitCode.SUCCESS:
            # Collection ran, but the journal and the unit must show that retention did not.
            return int(ExitCode.STAGE_FAILED)
        return int(report.exit_code)
    except ConfigurationError as error:
        print(
            json.dumps(
                {"outcome": "configuration_error", "error": type(error).__name__}, sort_keys=True
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
