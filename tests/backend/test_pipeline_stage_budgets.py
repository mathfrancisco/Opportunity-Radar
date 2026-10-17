"""R55-B1 review: stage budgets, and a finished stage is never reported as stopped."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from opportunity_radar import worker
from opportunity_radar.platform.pipeline import (
    Deadline,
    ExitCode,
    StageContext,
    StageCounts,
    StageSpec,
    StopSignal,
    run_pipeline,
)
from scripts import run_pipeline_once
from tests.backend.test_pipeline_runner import _run_pipeline_once_settings, _stages


def test_a_stage_that_finished_its_work_is_not_marked_stopped() -> None:
    now = [0.0]

    def finishing(_context: StageContext) -> StageCounts:
        now[0] = 100.0  # the deadline passes just as the stage completes its work
        return StageCounts(input=1, completed=1)

    events: list[str] = []
    stages = [StageSpec("collect_enabled_sources", finishing)] + _stages(events)[1:]

    report = run_pipeline(
        stages,
        owner_sub="owner",
        deadline_seconds=10,
        claim_factory=nullcontext,
        clock=lambda: now[0],
    )

    assert report.stages[0].status == "completed"
    assert report.stages[0].counts.completed == 1
    # The loop head still refuses to start the next stage past the deadline.
    assert [stage.status for stage in report.stages[1:]] == ["skipped", "skipped"]
    assert events == []
    assert report.exit_code == ExitCode.DEADLINE_REACHED


def test_a_stage_that_returns_stopped_counts_is_marked_stopped() -> None:
    stages = [
        StageSpec("collect_enabled_sources", lambda _c: StageCounts(input=1, stopped=1))
    ] + _stages([])[1:]

    report = run_pipeline(
        stages, owner_sub="owner", deadline_seconds=30, claim_factory=nullcontext
    )

    assert report.stages[0].status == "stopped"
    assert [stage.status for stage in report.stages[1:]] == ["skipped", "skipped"]


def _stage(monkeypatch: pytest.MonkeyPatch, name: str, clock):
    monkeypatch.setattr(run_pipeline_once, "monotonic", clock)
    stages = run_pipeline_once._stages(object(), _run_pipeline_once_settings())
    return {stage.name: stage for stage in stages}[name]


def test_collect_spending_its_own_budget_is_a_partial_completion_not_a_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    seen: dict[str, float] = {}

    def fake_collect(_engine: object, **kwargs: object) -> dict[str, int]:
        seen["pass_deadline"] = kwargs["pass_deadline_seconds"]  # type: ignore[assignment]
        now[0] += 500  # past 40% of the window, well before its end
        assert kwargs["stop_requested"]()  # type: ignore[operator]
        return {
            "input": 5, "completed": 2, "failed": 0, "skipped": 3, "stopped": 1,
            "eligible": 5, "executed": 2,
        }

    monkeypatch.setattr(run_pipeline_once, "collect_enabled_sources", fake_collect)
    monkeypatch.setattr(run_pipeline_once, "collection_service_factory", lambda _s: object())
    stage = _stage(monkeypatch, "collect_enabled_sources", lambda: now[0])
    context = StageContext("owner", Deadline(900, clock=lambda: now[0]), StopSignal())

    counts = stage.run(context)

    assert seen["pass_deadline"] == pytest.approx(360.0)  # 40% of 900 s
    assert counts.stopped == 0
    assert counts.completed == 2 and counts.skipped == 3
    assert counts.metrics["budget_spent"] == 1
    assert counts.metrics["eligible"] == 5
    assert not context.should_stop()  # evaluation and analysis still get their time


def test_normalize_budget_stops_between_batches_without_stopping_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]

    def fake_normalize(_engine: object, *, stop_requested) -> dict[str, int]:
        assert not stop_requested()
        now[0] += 300  # 30% of 900 s is 270 s
        assert stop_requested()
        return {"input": 40, "completed": 40, "failed": 0, "skipped": 0, "stopped": 1}

    monkeypatch.setattr(run_pipeline_once, "normalize_opportunities", fake_normalize)
    stage = _stage(monkeypatch, "normalize_opportunities", lambda: now[0])
    context = StageContext("owner", Deadline(900, clock=lambda: now[0]), StopSignal())

    counts = stage.run(context)

    assert counts.stopped == 0 and counts.completed == 40
    assert counts.metrics == {"budget_spent": 1}


def test_a_real_window_deadline_inside_a_budgeted_stage_still_stops_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]

    def fake_normalize(_engine: object, *, stop_requested) -> dict[str, int]:
        now[0] += 1000  # past the window itself
        return {"input": 1, "completed": 1, "failed": 0, "skipped": 0, "stopped": 0}

    monkeypatch.setattr(run_pipeline_once, "normalize_opportunities", fake_normalize)
    stage = _stage(monkeypatch, "normalize_opportunities", lambda: now[0])
    context = StageContext("owner", Deadline(900, clock=lambda: now[0]), StopSignal())

    assert stage.run(context).stopped == 1


def test_a_budget_cut_stage_leaves_the_exit_success_and_later_stages_running() -> None:
    now = [0.0]
    ran: list[str] = []

    def cut(_context: StageContext) -> StageCounts:
        now[0] += 400  # its own share is spent, the window (900 s) is not
        return StageCounts(input=9, completed=4, skipped=5, metrics={"budget_spent": 1})

    def later(name: str):
        return StageSpec(name, lambda _c: ran.append(name) or StageCounts(input=1, completed=1))

    report = run_pipeline(
        [
            StageSpec("collect_enabled_sources", cut),
            later("normalize_opportunities"),
            later("evaluate_pending"),
            later("analyze_pending"),
        ],
        owner_sub="owner",
        deadline_seconds=900,
        claim_factory=nullcontext,
        clock=lambda: now[0],
    )

    assert ran == ["normalize_opportunities", "evaluate_pending", "analyze_pending"]
    assert report.exit_code == ExitCode.SUCCESS
    assert [stage.status for stage in report.stages] == ["completed"] * 4


def test_an_unreached_probe_failure_rolls_the_session_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rolled_back: list[bool] = []

    class Service:
        session = SimpleNamespace(rollback=lambda: rolled_back.append(True))

        def scheduling_state(self, *_a: object, **_k: object) -> object:
            raise RuntimeError("transaction aborted")

    ctx = SimpleNamespace(
        timezone="UTC", backoff_base=None, backoff_ceiling=None, manual_min_interval=None,
        summary=worker._PassSummary(),
    )

    worker._count_unreached_if_eligible(Service(), object(), ctx, None)  # type: ignore[arg-type]

    assert rolled_back == [True]
    assert ctx.summary.eligible == 0
