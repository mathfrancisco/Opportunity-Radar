"""R55-B2: when a source with no cron ("manual" or empty schedule) is due for the window."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from opportunity_radar import worker
from opportunity_radar.acquisition.scheduling import (
    CollectionGate,
    HostBudgetState,
    SourceRunHistory,
    SourceSchedulingState,
    evaluate_gate,
    is_manual_schedule,
    next_due_at,
)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _state(
    schedule: str | None,
    *,
    success_ago: timedelta | None = None,
    failures: int = 0,
    budget: HostBudgetState | None = None,
) -> SourceSchedulingState:
    last_success = None if success_ago is None else NOW - success_ago
    return SourceSchedulingState(
        schedule=schedule,
        timezone="UTC",
        history=SourceRunHistory(
            last_started_at=last_success,
            consecutive_failures=failures,
            last_failure_at=NOW - timedelta(seconds=30) if failures else None,
            last_success_at=last_success,
        ),
        host="example",
        host_budget=budget,
    )


@pytest.mark.parametrize("schedule", [None, "", "  ", "manual", "Manual", " MANUAL "])
def test_manual_spellings_are_recognised(schedule: str | None) -> None:
    assert is_manual_schedule(schedule)


def test_a_cron_is_not_manual() -> None:
    assert not is_manual_schedule("0 * * * *")


@pytest.mark.parametrize("schedule", [None, "manual"])
def test_without_an_interval_a_manual_source_is_never_scheduled(schedule: str | None) -> None:
    gate = evaluate_gate(_state(schedule, success_ago=timedelta(days=30)), now=NOW)
    assert gate is CollectionGate.NOT_SCHEDULED


@pytest.mark.parametrize("schedule", [None, "manual"])
def test_a_manual_source_that_never_succeeded_is_due(schedule: str | None) -> None:
    assert evaluate_gate(_state(schedule), now=NOW, manual_min_interval=HOUR) is CollectionGate.DUE


@pytest.mark.parametrize("schedule", [None, "manual"])
def test_a_manual_source_is_due_once_its_last_success_is_older_than_the_interval(
    schedule: str | None,
) -> None:
    stale = _state(schedule, success_ago=HOUR + timedelta(minutes=1))
    exactly = _state(schedule, success_ago=HOUR)
    assert evaluate_gate(stale, now=NOW, manual_min_interval=HOUR) is CollectionGate.DUE
    assert evaluate_gate(exactly, now=NOW, manual_min_interval=HOUR) is CollectionGate.DUE


@pytest.mark.parametrize("schedule", [None, "manual"])
def test_a_recently_collected_manual_source_is_not_due(schedule: str | None) -> None:
    fresh = _state(schedule, success_ago=timedelta(minutes=59))
    assert evaluate_gate(fresh, now=NOW, manual_min_interval=HOUR) is CollectionGate.NOT_DUE
    due_at, reason = next_due_at(fresh, now=NOW, manual_min_interval=HOUR)
    assert reason == "freshness"
    assert due_at == NOW + timedelta(minutes=1)


def test_the_interval_is_configurable() -> None:
    state = _state(None, success_ago=timedelta(hours=3))
    assert (
        evaluate_gate(state, now=NOW, manual_min_interval=timedelta(hours=6))
        is CollectionGate.NOT_DUE
    )
    assert (
        evaluate_gate(state, now=NOW, manual_min_interval=timedelta(hours=2))
        is CollectionGate.DUE
    )


def test_a_failing_manual_source_still_backs_off() -> None:
    state = _state("manual", success_ago=timedelta(days=2), failures=3)
    assert evaluate_gate(state, now=NOW, manual_min_interval=HOUR) is CollectionGate.BACKING_OFF


def test_an_exhausted_host_budget_holds_a_due_manual_source_back() -> None:
    exhausted = HostBudgetState(
        host="example", window_start=NOW - timedelta(minutes=5), requests_used=500,
        requests_ceiling=500,
    )
    state = _state(None, success_ago=timedelta(days=1), budget=exhausted)
    assert evaluate_gate(state, now=NOW, manual_min_interval=HOUR) is CollectionGate.RATE_LIMITED
    _, reason = next_due_at(state, now=NOW, manual_min_interval=HOUR)
    assert reason == "budget"


def test_a_host_budget_with_room_lets_it_run() -> None:
    roomy = HostBudgetState(
        host="example", window_start=NOW - timedelta(minutes=5), requests_used=10,
        requests_ceiling=500,
    )
    state = _state(None, success_ago=timedelta(days=1), budget=roomy)
    assert evaluate_gate(state, now=NOW, manual_min_interval=HOUR) is CollectionGate.DUE


def test_cron_sources_ignore_the_manual_interval() -> None:
    state = _state("0 * * * *", success_ago=timedelta(minutes=10))
    # Started at 11:50 and the cron fires on the hour: at 11:55 it is not due, whatever the
    # manual interval says.
    gate = evaluate_gate(
        state, now=NOW - timedelta(minutes=5), manual_min_interval=timedelta(0)
    )
    assert gate is CollectionGate.NOT_DUE


def test_the_window_reports_executed_over_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    exhausted = HostBudgetState(
        host="example", window_start=NOW, requests_used=500, requests_ceiling=500
    )
    states = {
        "stale": _state("manual", success_ago=timedelta(hours=5)),
        "never": _state(None),
        "fresh": _state("manual", success_ago=timedelta(minutes=5)),
        "blocked": _state("manual", success_ago=timedelta(hours=9), budget=exhausted),
    }
    sources = [SimpleNamespace(id=name) for name in states]
    executed: list[str] = []

    class Service:
        def list_collectable_sources(self) -> list[object]:
            return sources

        def scheduling_state(self, source: SimpleNamespace, *, timezone: str) -> object:
            del timezone
            return states[source.id]

        async def execute(self, source_id: str, _request: object, **_kwargs: object):
            executed.append(source_id)
            return SimpleNamespace(
                complete=False, status="SUCCEEDED", id=f"run-{source_id}", items_persisted=1
            )

    monkeypatch.setattr(worker, "observe_job", lambda *_a, **_k: nullcontext("pass"))
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(worker, "annotate_pass", lambda *_a, **_k: None)
    monkeypatch.setattr(
        worker,
        "_scheduled_request_with_rotation",
        lambda _service, source, _correlation: (SimpleNamespace(keywords=()), None, 0),
    )

    result = worker.collect_enabled_sources(
        object(),  # type: ignore[arg-type]
        owner_sub="worker-owner-synthetic",
        service_factory=lambda _session: Service(),  # type: ignore[arg-type,return-value]
        now=NOW,
        manual_min_interval_hours=1,
    )

    assert executed == ["stale", "never"]
    assert result["eligible"] == 3  # stale, never and the budget-blocked one
    assert result["executed"] == 2
    assert result["completed"] == 2
    assert result["skipped"] == 2  # fresh (not due) and blocked (host budget)


def test_without_the_interval_the_window_skips_manual_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [SimpleNamespace(id="manual")]

    class Service:
        def list_collectable_sources(self) -> list[object]:
            return sources

        def scheduling_state(self, _source: object, *, timezone: str) -> object:
            del timezone
            return _state("manual", success_ago=timedelta(days=9))

        async def execute(self, *_args: object, **_kwargs: object):
            pytest.fail("a manual source must not run without the interval")

    monkeypatch.setattr(worker, "observe_job", lambda *_a, **_k: nullcontext("pass"))
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(worker, "annotate_pass", lambda *_a, **_k: None)

    result = worker.collect_enabled_sources(
        object(),  # type: ignore[arg-type]
        owner_sub="worker-owner-synthetic",
        service_factory=lambda _session: Service(),  # type: ignore[arg-type,return-value]
        now=NOW,
    )

    assert (result["eligible"], result["executed"], result["skipped"]) == (0, 0, 1)
