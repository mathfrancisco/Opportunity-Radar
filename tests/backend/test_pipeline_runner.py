from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from opportunity_radar import worker
from opportunity_radar.acquisition.collectors import CollectorCapabilities
from opportunity_radar.acquisition.domain import CollectionRequest
from opportunity_radar.acquisition.scheduling import SourceSchedulingState
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.pipeline import (
    ClaimBusyError,
    ConfigurationError,
    Deadline,
    ExitCode,
    PostgresWindowClaim,
    StageContext,
    StageCounts,
    StageSpec,
    StopSignal,
    describe_pipeline,
    run_pipeline,
)
from scripts import run_pipeline_once


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


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_deadline_is_refused_by_pure_description(deadline: float) -> None:
    with pytest.raises(ConfigurationError):
        describe_pipeline(owner_sub="owner", deadline_seconds=deadline)


@pytest.mark.parametrize("deadline", ["nan", "inf", "-inf"])
def test_cli_dry_run_refuses_non_finite_deadline(monkeypatch, deadline: str) -> None:
    monkeypatch.setattr(
        run_pipeline_once, "get_settings", lambda: SimpleNamespace(worker_owner_sub="owner")
    )
    assert run_pipeline_once.main([f"--deadline-seconds={deadline}", "--dry-run"]) == 2


def test_normalize_stops_before_starting_the_next_item(monkeypatch) -> None:
    calls: list[int] = []

    class Service:
        def normalize_pending(self, limit: int) -> SimpleNamespace:
            calls.append(limit)
            return SimpleNamespace(processed=1, succeeded=1, review_required=0, failed=0)

    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(worker, "OpportunityService", lambda _session: Service())
    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext())

    result = worker.normalize_opportunities(object(), stop_requested=lambda: bool(calls))

    assert calls == [1]
    assert result == {"input": 1, "completed": 1, "failed": 0, "skipped": 0, "stopped": 1}


def test_parallel_collection_accounts_for_unstarted_host_group() -> None:
    summary = worker._PassSummary()
    context = worker._PassContext(
        correlation_id="test",
        timezone="UTC",
        now=None,
        utc_clock=None,
        backoff_base=timedelta(seconds=1),
        backoff_ceiling=timedelta(seconds=1),
        source_deadline_seconds=0,
        pass_deadline_seconds=0,
        pass_started=0,
        monotonic_clock=lambda: 0,
        summary=summary,
        stop_requested=lambda: True,
    )

    worker._collect_host_group(
        object(),
        lambda _session: pytest.fail("must not build service"),
        [uuid4(), uuid4()],
        context,
    )

    assert summary.counts == {"completed": 0, "failed": 0, "skipped": 2, "blocked": 0}


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


def test_analysis_stays_blocked_and_retention_is_planned_daily() -> None:
    stages = describe_pipeline(owner_sub="owner", deadline_seconds=30)["stages"]
    assert stages[-2] == {
        "name": "analyze_pending",
        "status": "blocked",
        "reason": "analysis is opt-in and disabled for finite pipeline windows",
    }
    assert stages[-1]["name"] == "retention"
    assert stages[-1]["status"] == "planned"


def test_retention_stage_is_optional_and_last() -> None:
    events: list[str] = []
    stages = _stages(events) + [
        StageSpec("retention", lambda _c: events.append("retention") or StageCounts(input=1))
    ]
    report = run_pipeline(stages, owner_sub="owner", deadline_seconds=30, claim_factory=nullcontext)
    assert events[-1] == "retention" and report.exit_code == ExitCode.SUCCESS
    with pytest.raises(ConfigurationError):
        run_pipeline(
            [stages[-1], *stages[:-1]],
            owner_sub="owner",
            deadline_seconds=30,
            claim_factory=nullcontext,
        )


# --- F53-10 AC03/AC05 -----------------------------------------------------------------
# Mid-source deadline not closing absences is covered by
# tests/backend/acquisition/test_source_run_claim_fencing.py::
# test_worker_timeout_preserves_positive_presence_only.
# The tests below add the missing runner-level and between-sources interruption angles.


def _run_pipeline_once_settings(**overrides: object) -> SimpleNamespace:
    defaults = {
        "opportunity_retention_days": 0,
        "opportunity_retention_apply": False,
        "opportunity_retention_batch_size": 500,
        "ai_call_record_retention_days": 7,
    }
    return SimpleNamespace(
        database_url="postgresql://unused",
        worker_owner_sub="owner",
        collection_timezone="UTC",
        collection_backoff_base_seconds=300.0,
        collection_backoff_ceiling_seconds=86400.0,
        collection_source_deadline_seconds=0.0,
        collection_pass_deadline_seconds=None,
        collection_host_concurrency=1,
        worker_evaluate_batch_size=10,
        **{**defaults, **overrides},
    )


def _patch_run_pipeline_once_for_non_success(
    monkeypatch: pytest.MonkeyPatch,
    collect_result: dict[str, int],
) -> None:
    monkeypatch.setattr(
        run_pipeline_once, "get_settings", lambda: _run_pipeline_once_settings()
    )
    monkeypatch.setattr(run_pipeline_once, "create_database_engine", lambda _url: object())
    monkeypatch.setattr(run_pipeline_once, "validate_owner", lambda sub: sub)
    monkeypatch.setattr(run_pipeline_once, "PostgresWindowClaim", lambda _engine: nullcontext())
    monkeypatch.setattr(
        run_pipeline_once, "collect_enabled_sources", lambda **kwargs: collect_result
    )
    monkeypatch.setattr(
        run_pipeline_once,
        "normalize_opportunities",
        lambda **kwargs: {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0},
    )
    monkeypatch.setattr(
        run_pipeline_once,
        "evaluate_pending",
        lambda **kwargs: {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0},
    )


def test_run_pipeline_once_deadline_reached_returns_non_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Runner-level deadline hit reports partial/deadline and returns non-success."""
    _patch_run_pipeline_once_for_non_success(
        monkeypatch,
        {"input": 1, "completed": 0, "failed": 0, "skipped": 0, "stopped": 1},
    )

    # `run_pipeline`'s default clock is the `time.monotonic` object imported at module
    # load, so patching the module attribute is not enough. Wrap the call to inject a
    # fake clock that expires the deadline before the collect stage finishes.
    real_run_pipeline = run_pipeline_once.run_pipeline
    clock_values = [0.0, 0.0, 100.0, 100.0, 100.0, 100.0]

    def _run_with_fake_clock(*args: object, **kwargs: object) -> object:
        return real_run_pipeline(
            *args,
            clock=lambda: clock_values.pop(0) if clock_values else 100.0,
            **kwargs,
        )

    monkeypatch.setattr(run_pipeline_once, "run_pipeline", _run_with_fake_clock)

    exit_code = run_pipeline_once.main(["--deadline-seconds=1"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == ExitCode.DEADLINE_REACHED
    assert report["outcome"] == "deadline_reached"
    assert report["stop_reason"] == "deadline"
    assert all(stage["status"] != "completed" for stage in report["stages"])


def test_run_pipeline_once_sigterm_returns_non_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SIGTERM stops the runner gracefully and no stage is marked completed."""
    _patch_run_pipeline_once_for_non_success(
        monkeypatch,
        {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 1},
    )

    @contextmanager
    def sigterm_stop(stop: StopSignal) -> Iterator[None]:
        stop.set("interrupted")
        yield

    monkeypatch.setattr(run_pipeline_once, "signal_stop", sigterm_stop)

    exit_code = run_pipeline_once.main(["--deadline-seconds=1"])
    report = json.loads(capsys.readouterr().out)

    assert exit_code == ExitCode.INTERRUPTED
    assert report["outcome"] == "interrupted"
    assert report["stop_reason"] == "interrupted"
    assert all(stage["status"] != "completed" for stage in report["stages"])


def _fake_source() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        source_type="fake",
        name="fake",
        configuration={},
        rate_limit_policy={},
        checkpoint=None,
    )


def _fake_collector_registry() -> SimpleNamespace:
    class _FakeCollector:
        capabilities = CollectorCapabilities(
            incremental_cursor=False, keyword_search=False
        )

    class _FakeRegistry:
        def resolve(self, _source_type: str) -> _FakeCollector:
            return _FakeCollector()

    return SimpleNamespace(registry=_FakeRegistry())


def _fake_service(
    sources: list[SimpleNamespace], executed: list[tuple[UUID, SimpleNamespace]]
) -> SimpleNamespace:
    base = _fake_collector_registry()

    class _FakeService:
        registry = base.registry

        def list_collectable_sources(self) -> list[SimpleNamespace]:
            return list(sources)

        def scheduling_state(
            self, _source: SimpleNamespace, *, timezone: str
        ) -> SourceSchedulingState:
            return SourceSchedulingState(schedule="0 * * * *", timezone=timezone)

        def run_may_close_absences(self, _run: SimpleNamespace) -> bool:
            return True

        async def execute(
            self,
            source_id: UUID,
            _request: CollectionRequest,
            *,
            deadline_seconds: float | None = None,
        ) -> SimpleNamespace:
            del deadline_seconds
            run = SimpleNamespace(
                id=uuid4(),
                status="SUCCEEDED",
                complete=True,
                items_persisted=1,
                items_seen=1,
                items_skipped=0,
                items_invalid=0,
                http_requests=1,
                retry_count=0,
                error_code=None,
                error_summary=None,
            )
            executed.append((source_id, run))
            return run

    return _FakeService()


class _FakeOpportunityService:
    def __init__(self) -> None:
        self.normalize_calls: list[UUID] = []
        self.closure_calls: list[UUID] = []

    def normalize_run(self, run_id: UUID) -> None:
        self.normalize_calls.append(run_id)

    def reconcile_run_closures(
        self, run_id: UUID, *, may_close: object = None
    ) -> None:
        del may_close
        self.closure_calls.append(run_id)


def _patch_collect_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeOpportunityService:
    fake = _FakeOpportunityService()
    monkeypatch.setattr(worker, "_operational_owner", lambda _sub, **kwargs: "owner")
    monkeypatch.setattr(
        worker, "observe_job", lambda _engine, **kwargs: nullcontext("corr")
    )
    monkeypatch.setattr(worker, "annotate_pass", lambda *_a, **_k: None)
    monkeypatch.setattr(
        worker, "Session", lambda _engine: nullcontext(SimpleNamespace(rollback=lambda: None))
    )
    monkeypatch.setattr(worker, "OpportunityService", lambda _session: fake)
    return fake


def test_collect_sigterm_between_sources_stops_pass_without_marking_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SIGTERM between sources skips the rest of the pass; no closure for skipped sources."""
    source1 = _fake_source()
    source2 = _fake_source()
    executed: list[tuple[UUID, SimpleNamespace]] = []
    fake = _patch_collect_dependencies(monkeypatch)

    # The stop flips once the fake service has executed the first source.
    result = worker.collect_enabled_sources(
        object(),
        monotonic_clock=lambda: 0.0,
        stop_requested=lambda: bool(executed),
        service_factory=lambda _session: _fake_service([source1, source2], executed),
    )

    assert result == {"input": 2, "completed": 1, "failed": 0, "skipped": 1, "stopped": 1}
    assert [source_id for source_id, _ in executed] == [source1.id]
    completed_run = executed[0][1]
    assert completed_run.complete is True
    assert fake.normalize_calls == [completed_run.id]
    assert fake.closure_calls == [completed_run.id]
    assert source2.id not in [source_id for source_id, _ in executed]
    assert len(executed) == 1  # skipped source produced no run object at all


def test_collect_deadline_between_sources_stops_pass_without_marking_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deadline expiry between sources skips the rest; no closure for skipped sources."""
    source1 = _fake_source()
    source2 = _fake_source()
    executed: list[tuple[UUID, SimpleNamespace]] = []
    fake = _patch_collect_dependencies(monkeypatch)

    # The clock stays at 0.0 until the first source has executed, then jumps past the
    # pass deadline so source2 is skipped before its execute() is ever called.
    result = worker.collect_enabled_sources(
        object(),
        monotonic_clock=lambda: 2.0 if executed else 0.0,
        pass_deadline_seconds=1.0,
        service_factory=lambda _session: _fake_service([source1, source2], executed),
    )

    assert result == {"input": 2, "completed": 1, "failed": 0, "skipped": 1, "stopped": 0}
    assert [source_id for source_id, _ in executed] == [source1.id]
    completed_run = executed[0][1]
    assert completed_run.complete is True
    assert fake.normalize_calls == [completed_run.id]
    assert fake.closure_calls == [completed_run.id]
    assert source2.id not in [source_id for source_id, _ in executed]
    assert len(executed) == 1  # skipped source produced no run object at all


# --- R55-E2: the real `retention` stage closure ----------------------------------------


class _RetentionHarness:
    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, *, days: int = 7, apply: bool = False
    ) -> None:
        from opportunity_radar.operations.opportunity_retention import (
            OpportunityRetentionReport,
        )

        self.report = OpportunityRetentionReport(
            dry_run=not apply, retention_days=days, cutoff=None
        )
        self.due = True
        self.raises: Exception | None = None
        self.record_raises = False
        self.runs: list[dict[str, object]] = []
        self.records: list[dict[str, object]] = []
        self.due_checks: list[str] = []
        harness = self

        def run(_engine: object, **kwargs: object):
            harness.runs.append(kwargs)
            if harness.raises:
                raise harness.raises
            return harness.report

        def due(_engine: object, *, job_name: str = "opportunity_retention", **_kw: object):
            harness.due_checks.append(job_name)
            return harness.due

        def record(_engine: object, **kwargs: object) -> None:
            harness.records.append(kwargs)
            if harness.record_raises:
                raise RuntimeError("record failed")

        monkeypatch.setattr(run_pipeline_once, "run_opportunity_retention", run)
        monkeypatch.setattr(run_pipeline_once, "retention_due", due)
        monkeypatch.setattr(run_pipeline_once, "record_retention_attempt", record)
        settings = _run_pipeline_once_settings(
            opportunity_retention_days=days, opportunity_retention_apply=apply
        )
        self.stage = run_pipeline_once._stages(object(), settings)[3]
        assert self.stage.name == "retention"

    def run(self, *, stopped: bool = False) -> StageCounts:
        stop = StopSignal()
        if stopped:
            stop.set("signal")
        return self.stage.run(StageContext("owner", Deadline(60), stop))


def test_retention_stage_disabled_with_zero_days(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _RetentionHarness(monkeypatch, days=0)
    assert harness.run() == StageCounts(skipped=1)
    assert harness.runs == [] and harness.due_checks == []


def test_retention_stage_skips_when_not_due(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _RetentionHarness(monkeypatch)
    harness.due = False
    assert harness.run() == StageCounts(skipped=1)
    assert harness.runs == [] and harness.records == []


def test_retention_stage_stop_before_start_runs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = _RetentionHarness(monkeypatch, apply=True)
    assert harness.run(stopped=True) == StageCounts(stopped=1)
    assert harness.runs == [] and harness.records == []


def test_retention_stage_defaults_to_dry_run_tracked_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _RetentionHarness(monkeypatch, apply=False)
    assert harness.run() == StageCounts(input=1, completed=1)
    assert harness.runs[0]["dry_run"] is True
    assert harness.due_checks == ["opportunity_retention_dry_run"]
    assert harness.records == [{"success": True, "job_name": "opportunity_retention_dry_run"}]


def test_retention_stage_applies_only_when_the_flag_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _RetentionHarness(monkeypatch, apply=True)
    assert harness.run() == StageCounts(input=1, completed=1)
    assert harness.runs[0]["dry_run"] is False
    assert harness.runs[0]["batch_size"] == 500
    assert harness.runs[0]["ai_call_record_retention_days"] == 7
    assert harness.due_checks == ["opportunity_retention"]
    assert harness.records == [{"success": True, "job_name": "opportunity_retention"}]


def test_retention_stage_stopped_run_is_not_recorded_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _RetentionHarness(monkeypatch, apply=True)
    harness.report.stopped = True
    harness.report.complete = False
    assert harness.run() == StageCounts(input=1, stopped=1)
    assert harness.records == []


def test_retention_stage_step_errors_are_recorded_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _RetentionHarness(monkeypatch, apply=True)
    harness.report.errors = {"ai_call_record": "ValueError"}
    harness.report.complete = False
    assert harness.run() == StageCounts(input=1, failed=1)
    assert harness.records == [
        {"success": False, "error": "ai_call_record", "job_name": "opportunity_retention"}
    ]


def test_retention_stage_exception_is_recorded_and_not_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _RetentionHarness(monkeypatch, apply=True)
    harness.raises = ValueError("original")
    harness.record_raises = True  # recording the failure fails too
    with pytest.raises(ValueError, match="original"):
        harness.run()
    assert harness.records[0]["success"] is False


def test_retention_apply_setting_defaults_to_false_and_reads_the_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opportunity_radar.platform.config import Settings

    url = "postgresql+psycopg://u:p@localhost:5432/x_test"
    assert Settings(database_url=url).opportunity_retention_apply is False
    assert Settings(database_url=url, opportunity_retention_apply=True).opportunity_retention_apply
    monkeypatch.setenv("OPPORTUNITY_RETENTION_APPLY", "true")
    assert Settings(database_url=url).opportunity_retention_apply is True
