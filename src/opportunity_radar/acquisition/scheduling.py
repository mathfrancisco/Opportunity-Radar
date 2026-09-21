"""When an enabled source may be collected by the clock, and why it may not.

Pure decision logic: no session, no network, and the moment is always passed in. A
scheduling rule that reads the wall clock internally can only be tested by waiting, which
is how backoff and minimum-interval bugs stay hidden until production.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from apscheduler.triggers.cron import CronTrigger

# The first retry waits minutes rather than the next tick, because a source that just
# failed is usually still failing. The ceiling keeps a long outage from pushing the next
# attempt beyond a day, which would look indistinguishable from an abandoned source.
DEFAULT_BACKOFF_BASE = timedelta(minutes=5)
DEFAULT_BACKOFF_CEILING = timedelta(hours=24)

# 2**20 doublings of any sane base already exceeds the ceiling by orders of magnitude;
# the cap only exists so a corrupt failure count cannot overflow the shift.
_MAX_DOUBLINGS = 20


class CollectionGate(StrEnum):
    """The verdict for one source at one moment."""

    DUE = "DUE"
    NOT_SCHEDULED = "NOT_SCHEDULED"
    NOT_DUE = "NOT_DUE"
    BACKING_OFF = "BACKING_OFF"
    RATE_LIMITED = "RATE_LIMITED"

    @property
    def outcome(self) -> str:
        """How the pass summary reports a source that never got to run."""
        if self is CollectionGate.DUE:
            return "completed"
        if self in (CollectionGate.NOT_SCHEDULED, CollectionGate.NOT_DUE):
            return "skipped"
        return "blocked"


@dataclass(frozen=True, slots=True)
class SourceRunHistory:
    """What previous runs say about a source, reduced to the three facts scheduling needs."""

    last_started_at: datetime | None = None
    consecutive_failures: int = 0
    last_failure_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SourceSchedulingState:
    schedule: str | None
    timezone: str
    history: SourceRunHistory = SourceRunHistory()
    last_http_attempt_at: datetime | None = None
    minimum_run_interval_seconds: float | None = None


def backoff_delay(
    consecutive_failures: int,
    *,
    base: timedelta = DEFAULT_BACKOFF_BASE,
    ceiling: timedelta = DEFAULT_BACKOFF_CEILING,
) -> timedelta:
    """Double the wait per consecutive failure, never past the ceiling."""
    if consecutive_failures <= 0:
        return timedelta(0)
    doublings = min(consecutive_failures - 1, _MAX_DOUBLINGS)
    return min(base * (2**doublings), ceiling)


def evaluate_gate(
    state: SourceSchedulingState,
    *,
    now: datetime,
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
    backoff_ceiling: timedelta = DEFAULT_BACKOFF_CEILING,
) -> CollectionGate:
    """Decide whether this source may run now.

    Order matters for the summary: the clock is asked first, so a source that simply is
    not due reads as skipped rather than blocked, and only a source that *would* have run
    is reported as held back by a limit.
    """
    if not state.schedule:
        return CollectionGate.NOT_SCHEDULED
    if not is_due(
        state.schedule,
        timezone=state.timezone,
        previous_run_at=state.history.last_started_at,
        now=now,
    ):
        return CollectionGate.NOT_DUE
    if state.history.consecutive_failures > 0 and state.history.last_failure_at is not None:
        resume_at = state.history.last_failure_at + backoff_delay(
            state.history.consecutive_failures, base=backoff_base, ceiling=backoff_ceiling
        )
        if now < resume_at:
            return CollectionGate.BACKING_OFF
    interval = state.minimum_run_interval_seconds
    if interval and state.last_http_attempt_at is not None:
        if now < state.last_http_attempt_at + timedelta(seconds=interval):
            return CollectionGate.RATE_LIMITED
    return CollectionGate.DUE


def is_due(
    schedule: str,
    *,
    timezone: str,
    previous_run_at: datetime | None,
    now: datetime,
) -> bool:
    """Has the cron expression come round since the previous run started?"""
    if previous_run_at is None:
        # A source that never ran has no reference point, and asking the trigger yields
        # the *next* fire time — always in the future, so the first automatic run would
        # never happen. An enabled, scheduled source starts on the first pass instead.
        return True
    trigger = CronTrigger.from_crontab(schedule, timezone=timezone)
    due_at = trigger.get_next_fire_time(previous_run_at, now)
    return due_at is not None and due_at <= now
