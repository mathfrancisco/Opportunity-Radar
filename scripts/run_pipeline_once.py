"""Run one finite collection/normalization/evaluation(/daily retention) window and exit."""

from __future__ import annotations

import argparse
import json

from opportunity_radar.operations.opportunity_retention import (
    record_retention_attempt,
    retention_due,
    run_opportunity_retention,
)
from opportunity_radar.platform.config import get_settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.pipeline import (
    ConfigurationError,
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
    collect_enabled_sources,
    evaluate_pending,
    normalize_opportunities,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _stages(engine, settings) -> list[StageSpec]:
    def counts(result: dict[str, int]) -> StageCounts:
        return StageCounts(
            input=result["input"],
            completed=result["completed"],
            failed=result["failed"],
            skipped=result["skipped"],
            stopped=result["stopped"],
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

    def retention(context: StageContext) -> StageCounts:
        # R55-E2: at most one complete run per UTC day; 0 days is the off switch.
        if settings.opportunity_retention_days <= 0 or not retention_due(engine):
            return StageCounts(skipped=1)
        if context.should_stop():
            return StageCounts(stopped=1)
        try:
            report = run_opportunity_retention(
                engine,
                retention_days=settings.opportunity_retention_days,
                batch_size=settings.opportunity_retention_batch_size,
                ai_call_record_retention_days=settings.ai_call_record_retention_days,
                dry_run=False,
                should_stop=context.should_stop,
            )
        except Exception as error:
            record_retention_attempt(engine, success=False, error=type(error).__name__)
            raise
        record_retention_attempt(engine, success=report.complete)
        return StageCounts(
            input=1, completed=int(report.complete), stopped=int(report.stopped)
        )

    return [
        StageSpec("collect_enabled_sources", collect),
        StageSpec("normalize_opportunities", normalize),
        StageSpec("evaluate_pending", evaluate),
        StageSpec("retention", retention),
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
            report = run_pipeline(
                _stages(engine, settings),
                owner_sub=owner,
                deadline_seconds=args.deadline_seconds,
                claim_factory=lambda: PostgresWindowClaim(engine),
                stop=stop,
            )
        print(json.dumps(report.to_dict(), sort_keys=True))
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
