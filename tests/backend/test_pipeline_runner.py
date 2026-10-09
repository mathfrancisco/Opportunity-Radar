from __future__ import annotations

import os
from contextlib import nullcontext

import pytest

from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.pipeline import (
    ClaimBusyError,
    ConfigurationError,
    ExitCode,
    PostgresWindowClaim,
    StageCounts,
    StageSpec,
    StopSignal,
    describe_pipeline,
    run_pipeline,
)


def _stages(events: list[str]) -> list[StageSpec]:
    def stage(name: str) -> StageSpec:
        def run(_context):
            events.append(name)
            return StageCounts(input=1, completed=1)

        return StageSpec(name, run)

    return [
        stage("collect_enabled_sources"),
        stage("normalize_opportunities"),
        stage("evaluate_pending"),
    ]


def test_owner_is_refused_before_claim_or_clock() -> None:
    claimed = False

    def claim():
        nonlocal claimed
        claimed = True
        return nullcontext()

    with pytest.raises(ConfigurationError):
        run_pipeline(_stages([]), owner_sub=" ", deadline_seconds=1, claim_factory=claim)
    assert not claimed


def test_runs_fixed_order_once() -> None:
    events: list[str] = []
    report = run_pipeline(
        _stages(events), owner_sub="owner", deadline_seconds=30, claim_factory=nullcontext
    )
    assert events == ["collect_enabled_sources", "normalize_opportunities", "evaluate_pending"]
    assert report.exit_code == ExitCode.SUCCESS
    assert report.correlation_id
    assert report.duration_ms >= 0
    assert report.stages[0].counts.completed == 1
    assert report.stages[0].duration_ms >= 0


def test_dry_run_has_no_claim_or_clock() -> None:
    plan = describe_pipeline(owner_sub="owner", deadline_seconds=30)
    assert plan["dry_run"] is True
    assert plan["touches"] == "none"
    assert [stage["name"] for stage in plan["stages"][:3]] == [spec.name for spec in _stages([])]


def test_busy_claim_does_no_work() -> None:
    events: list[str] = []

    def busy():
        raise ClaimBusyError()

    report = run_pipeline(
        _stages(events), owner_sub="owner", deadline_seconds=30, claim_factory=busy
    )
    assert report.exit_code == ExitCode.CLAIM_BUSY
    assert events == []


def test_failed_stage_is_sanitized_and_is_not_retried() -> None:
    calls = 0

    def collect(_context):
        nonlocal calls
        calls += 1
        raise RuntimeError("password=must-not-appear")

    stages = [
        StageSpec("collect_enabled_sources", collect),
        StageSpec("normalize_opportunities", lambda _context: pytest.fail("must not run")),
        StageSpec("evaluate_pending", lambda _context: pytest.fail("must not run")),
    ]
    report = run_pipeline(stages, owner_sub="owner", deadline_seconds=30, claim_factory=nullcontext)
    assert report.exit_code == ExitCode.STAGE_FAILED
    assert report.stages[0].error == "RuntimeError"
    assert calls == 1


def test_deadline_stops_between_units_and_retry_runs_pending() -> None:
    clock = iter((0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, *(2.0 for _ in range(12))))
    pending = ["first", "second"]

    def collect(context):
        completed = 0
        while pending and not context.should_stop():
            pending.pop(0)
            completed += 1
        return StageCounts(input=2, completed=completed, stopped=len(pending))

    stages = [
        StageSpec("collect_enabled_sources", collect),
        StageSpec("normalize_opportunities", lambda _context: StageCounts()),
        StageSpec("evaluate_pending", lambda _context: StageCounts()),
    ]
    report = run_pipeline(
        stages,
        owner_sub="owner",
        deadline_seconds=1,
        claim_factory=nullcontext,
        clock=lambda: next(clock),
    )
    assert report.exit_code == ExitCode.DEADLINE_REACHED
    assert pending == ["second"]
    retry_events: list[str] = []
    retry = run_pipeline(
        _stages(retry_events), owner_sub="owner", deadline_seconds=30, claim_factory=nullcontext
    )
    assert retry.exit_code == ExitCode.SUCCESS
    assert retry_events == [
        "collect_enabled_sources",
        "normalize_opportunities",
        "evaluate_pending",
    ]


def test_interrupt_is_reported_and_does_not_start_next_stage() -> None:
    stop = StopSignal()

    def collect(_context):
        stop.set("interrupted")
        return StageCounts(input=1, completed=1, stopped=1)

    stages = [
        StageSpec("collect_enabled_sources", collect),
        StageSpec("normalize_opportunities", lambda _context: pytest.fail("must not run")),
        StageSpec("evaluate_pending", lambda _context: pytest.fail("must not run")),
    ]
    report = run_pipeline(
        stages, owner_sub="owner", deadline_seconds=30, claim_factory=nullcontext, stop=stop
    )
    assert report.exit_code == ExitCode.INTERRUPTED
    assert [stage.status for stage in report.stages] == ["stopped", "skipped", "skipped"]


def test_stopped_stage_ends_the_global_pipeline() -> None:
    events: list[str] = []

    def collect(_context):
        events.append("collect")
        return StageCounts(input=1, completed=1, stopped=1)

    report = run_pipeline(
        [
            StageSpec("collect_enabled_sources", collect),
            StageSpec("normalize_opportunities", lambda _context: events.append("normalize")),
            StageSpec("evaluate_pending", lambda _context: events.append("evaluate")),
        ],
        owner_sub="owner",
        deadline_seconds=30,
        claim_factory=nullcontext,
    )

    assert report.exit_code == ExitCode.SUCCESS
    assert events == ["collect"]
    assert [stage.status for stage in report.stages] == ["stopped", "skipped", "skipped"]


@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="requires explicitly isolated PostgreSQL integration database",
)
def test_postgres_claim_allows_only_one_window_on_isolated_database() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    first = PostgresWindowClaim(engine, name="pipeline-runner-test-claim")
    second = PostgresWindowClaim(engine, name="pipeline-runner-test-claim")

    with first:
        with pytest.raises(ClaimBusyError):
            with second:
                pass


def test_no_analysis_or_retention_is_planned() -> None:
    stages = describe_pipeline(owner_sub="owner", deadline_seconds=30)["stages"]
    assert stages[-2]["status"] == "blocked"
    assert stages[-1]["status"] == "blocked"
