"""When an enabled source may be collected by the clock, and why it may not.

Pure decision logic: no session, no network, and the moment is always passed in. A
scheduling rule that reads the wall clock internally can only be tested by waiting, which
is how backoff and minimum-interval bugs stay hidden until production.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
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

# How long a host's request counter accumulates before it rolls over to a fresh window.
# A cooldown from Retry-After survives the rollover regardless: a provider that asked for
# quiet does not get a fresh allowance just because an hour ticked over (F20-38).
DEFAULT_HOST_BUDGET_WINDOW = timedelta(hours=1)

# Used only when a host has never been observed before and no persisted ceiling exists.
# It is intentionally generous: the ceiling is a shared-abuse guard, not a per-source
# throttle (that is `minimum_run_interval_seconds`), so a wrong default here should err
# on the side of not starving every source of a healthy host.
DEFAULT_HOST_REQUESTS_CEILING = 1000


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
class HostBudgetState:
    """Request budget shared by every source of one host/provider, persisted across runs.

    Sources of the same provider (e.g. every Greenhouse board) compete for the same
    window: one source spending its own turn's requests must show up here so the next
    source evaluated in the same pass sees a smaller remaining allowance, not a full one.
    `cooldown_until` is set from a provider's `Retry-After` and is independent of the
    request counter — it can hold even a freshly rolled-over window to zero.
    """

    host: str
    window_start: datetime
    requests_used: int
    requests_ceiling: int
    cooldown_until: datetime | None = None
    # Exploration reserve (SPEC 39 §7 / SPEC 43): a low-yield or never-observed source
    # would otherwise starve forever behind well-observed sources that spend the budget
    # first. Reserving a slice of the ceiling for it is what "revisited within the
    # configured maximum" (acceptance criterion 2) actually requires.
    exploration_reserve_ratio: float = 0.10

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("host cannot be empty")
        if self.requests_used < 0:
            raise ValueError("requests_used cannot be negative")
        if self.requests_ceiling < 0:
            raise ValueError("requests_ceiling cannot be negative")
        if not 0.0 <= self.exploration_reserve_ratio < 1.0:
            raise ValueError("exploration_reserve_ratio must be within [0, 1)")

    def rolled_over(
        self, *, now: datetime, window: timedelta = DEFAULT_HOST_BUDGET_WINDOW
    ) -> "HostBudgetState":
        """The state a caller should act on at `now`: a fresh counter once the window
        has fully elapsed, otherwise unchanged. `cooldown_until` is never cleared here —
        only its own expiry (comparing against `now`) ends it."""
        if now - self.window_start < window:
            return self
        return replace(self, window_start=now, requests_used=0)

    def effective_ceiling(self, *, is_low_yield: bool) -> int:
        """The ceiling this caller may spend up to, after setting aside the reserve.

        A well-observed source never gets to spend the reserve; that slice exists only so
        a low-yield/new source is not permanently crowded out by it (see class docstring).
        """
        if is_low_yield:
            return self.requests_ceiling
        return int(self.requests_ceiling * (1 - self.exploration_reserve_ratio))

    def has_capacity(
        self,
        *,
        now: datetime,
        is_low_yield: bool = False,
        window: timedelta = DEFAULT_HOST_BUDGET_WINDOW,
    ) -> bool:
        current = self.rolled_over(now=now, window=window)
        if current.cooldown_until is not None and now < current.cooldown_until:
            return False
        return current.requests_used < current.effective_ceiling(is_low_yield=is_low_yield)


@dataclass(frozen=True, slots=True)
class ConditionalRequestHeaders:
    """`If-None-Match`/`If-Modified-Since` for the next request against one representation.

    Never built across scopes: a checkpoint's validators only apply to the exact
    representation that produced them (SPEC 39 §7 — "não compartilhar validadores entre
    escopos diferentes"), so a caller building this from a checkpoint must first confirm
    the checkpoint belongs to the same scope as the request it is conditioning.
    """

    if_none_match: str | None = None
    if_modified_since: str | None = None

    def is_empty(self) -> bool:
        return self.if_none_match is None and self.if_modified_since is None

    def as_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.if_none_match:
            headers["If-None-Match"] = self.if_none_match
        if self.if_modified_since:
            headers["If-Modified-Since"] = self.if_modified_since
        return headers


@dataclass(frozen=True, slots=True)
class SourceSchedulingState:
    schedule: str | None
    timezone: str
    history: SourceRunHistory = SourceRunHistory()
    last_http_attempt_at: datetime | None = None
    minimum_run_interval_seconds: float | None = None
    # The host/provider this source shares a budget with, and that budget's state as
    # already read by the caller (F20-38). `None` in both preserves today's behaviour:
    # a source with no shared budget is judged only on its own schedule/backoff/interval.
    host: str | None = None
    host_budget: HostBudgetState | None = None
    # Whether this source counts as low-yield/under-observed for the exploration reserve.
    # The caller decides this (e.g. from coverage/yield metrics, F20-35) — scheduling only
    # spends the reserve it is told to.
    is_low_yield: bool = False


#: Cron schedules for a company source that names no schedule of its own. Cadence follows
#: `Company.priority` (the user's interest) and nothing else: `research_confidence` (how
#: mature the catalogue is, F48-14) is operational and never lowers a company to weekly.
#: A high-priority company is worth checking far more often than a low one; every
#: cadence here stays well inside a source's own minimum run interval for any policy
#: this codebase configures.
DEFAULT_SCHEDULE_BY_COMPANY_PRIORITY = {
    "high": "0 */6 * * *",  # every 6 hours
    "normal": "0 0 * * *",  # once a day
    "low": "0 0 * * 0",  # once a week
}


def default_schedule_for_priority(
    priority: str, *, minimum_run_interval_seconds: float | None = None
) -> str:
    """The default cron schedule for a company source of this priority.

    Falls back to the next cadence down whenever the network policy's own minimum run
    interval would make the priority's usual cadence tighter than the source allows.
    """
    order = ("high", "normal", "low")
    start = order.index(priority) if priority in order else order.index("normal")
    for candidate in order[start:]:
        schedule = DEFAULT_SCHEDULE_BY_COMPANY_PRIORITY[candidate]
        if minimum_run_interval_seconds is None or _cron_interval_seconds(
            schedule
        ) >= minimum_run_interval_seconds:
            return schedule
    return DEFAULT_SCHEDULE_BY_COMPANY_PRIORITY["low"]


def _cron_interval_seconds(schedule: str) -> float:
    """A cheap lower bound on how often `schedule` can fire, for the fallback above."""
    reference = datetime(2026, 1, 1, tzinfo=UTC)
    trigger = CronTrigger.from_crontab(schedule, timezone="UTC")
    first = trigger.get_next_fire_time(None, reference)
    second = trigger.get_next_fire_time(first, first)
    if first is None or second is None:
        return float("inf")
    return (second - first).total_seconds()


def validate_cron_schedule(schedule: str) -> None:
    """Raises `ValueError` unless `schedule` is a crontab expression this scheduler
    can run (the same `CronTrigger.from_crontab` the running scheduler uses below).

    `None`/unscheduled is a caller-level concern, not this function's — a source with no
    schedule is valid and simply never reaches this check.
    """
    CronTrigger.from_crontab(schedule, timezone="UTC")


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
    # Checked last, per the same "clock first" rule: a source that is individually due is
    # reported as blocked (not skipped) only once every other reason has been ruled out.
    if state.host_budget is not None and not state.host_budget.has_capacity(
        now=now, is_low_yield=state.is_low_yield
    ):
        return CollectionGate.RATE_LIMITED
    return CollectionGate.DUE


def next_due_at(
    state: SourceSchedulingState,
    *,
    now: datetime,
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
    backoff_ceiling: timedelta = DEFAULT_BACKOFF_CEILING,
) -> tuple[datetime | None, str]:
    """When this source becomes eligible again, and why it is not eligible now.

    Mirrors `evaluate_gate`'s own order of checks so the two functions can never disagree
    about *why* a source is held back — only `evaluate_gate` decides the verdict, this
    only explains it (for the API/dashboard, per SPEC 39 §7). Returns `(now, "due")` when
    the source is already eligible.
    """
    if not state.schedule:
        return None, "not_scheduled"
    if not is_due(
        state.schedule,
        timezone=state.timezone,
        previous_run_at=state.history.last_started_at,
        now=now,
    ):
        trigger = CronTrigger.from_crontab(state.schedule, timezone=state.timezone)
        due_at = trigger.get_next_fire_time(state.history.last_started_at, now)
        return due_at, "freshness"
    if state.history.consecutive_failures > 0 and state.history.last_failure_at is not None:
        resume_at = state.history.last_failure_at + backoff_delay(
            state.history.consecutive_failures, base=backoff_base, ceiling=backoff_ceiling
        )
        if now < resume_at:
            return resume_at, "backoff"
    interval = state.minimum_run_interval_seconds
    if interval and state.last_http_attempt_at is not None:
        resume_at = state.last_http_attempt_at + timedelta(seconds=interval)
        if now < resume_at:
            return resume_at, "rate_limited"
    budget = state.host_budget
    if budget is not None and not budget.has_capacity(now=now, is_low_yield=state.is_low_yield):
        current = budget.rolled_over(now=now)
        if current.cooldown_until is not None and now < current.cooldown_until:
            return current.cooldown_until, "cooldown"
        window_end = current.window_start + DEFAULT_HOST_BUDGET_WINDOW
        return window_end, "budget"
    return now, "due"


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
