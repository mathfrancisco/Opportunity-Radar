"""Scheduling decisions under a controlled clock.

Every moment is passed in, so a backoff that is supposed to last a day is asserted in
microseconds rather than trusted.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from opportunity_radar.acquisition.scheduling import (
    CollectionGate,
    SourceRunHistory,
    SourceSchedulingState,
    backoff_delay,
    evaluate_gate,
    is_due,
)

_HOURLY = "0 * * * *"
_NOON = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)


def _state(**overrides: object) -> SourceSchedulingState:
    defaults: dict[str, object] = {"schedule": _HOURLY, "timezone": "UTC"}
    defaults.update(overrides)
    return SourceSchedulingState(**defaults)  # type: ignore[arg-type]


def test_a_source_without_a_schedule_never_runs_by_the_clock() -> None:
    gate = evaluate_gate(_state(schedule=None), now=_NOON)

    assert gate is CollectionGate.NOT_SCHEDULED
    assert gate.outcome == "skipped"


def test_a_scheduled_source_that_never_ran_starts_on_the_first_pass() -> None:
    # Asking the trigger for the next fire time always answers in the future, so a source
    # with no previous run would otherwise wait for a tick landing on the exact second.
    assert is_due(_HOURLY, timezone="UTC", previous_run_at=None, now=_NOON)
    assert evaluate_gate(_state(), now=_NOON) is CollectionGate.DUE


def test_the_cron_expression_holds_a_source_until_it_comes_round() -> None:
    history = SourceRunHistory(last_started_at=_NOON)

    within_the_hour = evaluate_gate(
        _state(history=history), now=_NOON + timedelta(minutes=30)
    )
    after_the_hour = evaluate_gate(
        _state(history=history), now=_NOON + timedelta(minutes=61)
    )

    assert within_the_hour is CollectionGate.NOT_DUE
    assert within_the_hour.outcome == "skipped"
    assert after_the_hour is CollectionGate.DUE


def test_the_minimum_interval_blocks_a_due_source_without_running_it() -> None:
    state = _state(
        history=SourceRunHistory(last_started_at=_NOON - timedelta(hours=2)),
        last_http_attempt_at=_NOON - timedelta(seconds=30),
        minimum_run_interval_seconds=120.0,
    )

    blocked = evaluate_gate(state, now=_NOON)
    elapsed = evaluate_gate(state, now=_NOON + timedelta(seconds=91))

    assert blocked is CollectionGate.RATE_LIMITED
    assert blocked.outcome == "blocked"
    assert elapsed is CollectionGate.DUE


def test_the_backoff_doubles_with_each_consecutive_failure_up_to_the_ceiling() -> None:
    base, ceiling = timedelta(minutes=5), timedelta(hours=24)

    delays = [
        backoff_delay(failures, base=base, ceiling=ceiling) for failures in range(0, 6)
    ]

    assert delays == [
        timedelta(0),
        timedelta(minutes=5),
        timedelta(minutes=10),
        timedelta(minutes=20),
        timedelta(minutes=40),
        timedelta(minutes=80),
    ]
    assert backoff_delay(40, base=base, ceiling=ceiling) == ceiling


def test_a_failing_source_is_held_back_until_its_backoff_elapses() -> None:
    failed_at = _NOON
    state = _state(
        history=SourceRunHistory(
            last_started_at=_NOON - timedelta(hours=3),
            consecutive_failures=2,
            last_failure_at=failed_at,
        )
    )

    during = evaluate_gate(state, now=failed_at + timedelta(minutes=9))
    after = evaluate_gate(state, now=failed_at + timedelta(minutes=11))

    assert during is CollectionGate.BACKING_OFF
    assert during.outcome == "blocked"
    assert after is CollectionGate.DUE


def test_a_success_removes_the_backoff_left_by_earlier_failures() -> None:
    # The streak is counted from the most recent runs, so a success ends it by existing.
    recovered = SourceRunHistory(
        last_started_at=_NOON - timedelta(hours=3),
        consecutive_failures=0,
        last_failure_at=None,
    )

    assert evaluate_gate(_state(history=recovered), now=_NOON) is CollectionGate.DUE


def test_the_backoff_never_pushes_the_next_attempt_beyond_the_ceiling() -> None:
    failed_at = _NOON
    state = _state(
        history=SourceRunHistory(
            last_started_at=_NOON - timedelta(days=5),
            consecutive_failures=30,
            last_failure_at=failed_at,
        )
    )

    assert (
        evaluate_gate(state, now=failed_at + timedelta(hours=23))
        is CollectionGate.BACKING_OFF
    )
    assert (
        evaluate_gate(state, now=failed_at + timedelta(hours=25)) is CollectionGate.DUE
    )
