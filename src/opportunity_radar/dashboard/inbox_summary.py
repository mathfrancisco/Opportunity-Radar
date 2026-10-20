"""Inbox header summary: how many postings are worth the time, how many were collected
since yesterday, and when the next collection runs (DESIGN.md section 8).

The counts reuse the Inbox query with its server defaults (areas of the active profile,
recent postings only), so the numbers match what the default Inbox lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.scheduling import (
    DEFAULT_BACKOFF_BASE,
    DEFAULT_BACKOFF_CEILING,
    is_manual_schedule,
    next_due_at,
)
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.dashboard.queries import InboxQuery, count_opportunity_inbox
from opportunity_radar.matching.domain import Verdict
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

#: The day in "desde ontem" is the owner's day, not the server's.
SUMMARY_TIMEZONE = ZoneInfo("America/Sao_Paulo")
WORTH_VERDICTS = (Verdict.HIGH_PRIORITY.value, Verdict.RECOMMENDED.value)


@dataclass(frozen=True, slots=True)
class InboxSummary:
    worth_count: int
    collected_count: int
    since: datetime
    next_collection_at: datetime | None


def summary_since(now: datetime) -> datetime:
    """00:00 of yesterday in America/Sao_Paulo, as a UTC instant."""
    local = now.astimezone(SUMMARY_TIMEZONE)
    midnight = (local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC)


def inbox_summary(
    session: Session,
    owner_sub: str,
    *,
    now: datetime,
    collection_timezone: str = "UTC",
    backoff_base: timedelta = DEFAULT_BACKOFF_BASE,
    backoff_ceiling: timedelta = DEFAULT_BACKOFF_CEILING,
) -> InboxSummary:
    since = summary_since(now)
    try:
        active = ProfileService(session, owner_sub).get_active()
        role_families = tuple(active.snapshot.preferences.target_role_families)
    except ProfileNotFoundError:
        role_families = ()
    collected = InboxQuery(
        role_families=role_families, only_recent=True, first_seen_after=since, now=now
    )
    worth = InboxQuery(
        role_families=role_families,
        only_recent=True,
        first_seen_after=since,
        verdicts=WORTH_VERDICTS,
        now=now,
    )
    return InboxSummary(
        worth_count=count_opportunity_inbox(session, worth, owner_sub=owner_sub),
        collected_count=count_opportunity_inbox(session, collected, owner_sub=owner_sub),
        since=since,
        next_collection_at=_next_collection_at(
            session,
            now=now,
            timezone=collection_timezone,
            backoff_base=backoff_base,
            backoff_ceiling=backoff_ceiling,
        ),
    )


def _next_collection_at(
    session: Session,
    *,
    now: datetime,
    timezone: str,
    backoff_base: timedelta,
    backoff_ceiling: timedelta,
) -> datetime | None:
    """Earliest future due time among enabled sources with a schedule; `None` when there
    is none (all manual, or nothing enabled). A time is never invented."""
    service = AcquisitionService(session)
    upcoming: list[datetime] = []
    for source in service.list_collectable_sources():
        state = service.scheduling_state(source, timezone=timezone)
        if is_manual_schedule(state.schedule):
            continue
        due_at, _ = next_due_at(
            state, now=now, backoff_base=backoff_base, backoff_ceiling=backoff_ceiling
        )
        if due_at is not None and due_at <= now:
            # Already due: the worker picks it up within a minute, so what the owner can
            # still look forward to is the next slot of its own schedule.
            due_at = CronTrigger.from_crontab(
                state.schedule or "", timezone=state.timezone
            ).get_next_fire_time(None, now)
        if due_at is not None and due_at > now:
            upcoming.append(due_at)
    return min(upcoming) if upcoming else None
