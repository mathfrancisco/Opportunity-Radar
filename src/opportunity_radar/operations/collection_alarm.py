"""Alarm for a hole in scheduled collection (card F48-07, problem V16).

A source that is scheduled but has not run in more than twice its cadence is not "quiet":
something between the clock and the collector is broken. The same rule applies to the
system as a whole, against its fastest cadence, because a worker that is down looks like
every source being merely slow. Everything is derived from persisted `source_run` rows and
takes the clock as an argument, so it is exact in a test and never reads a log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel, SourceRunModel

#: A run is late once it is this many cadences overdue.
GAP_FACTOR = 2.0

#: Fire times sampled to find the longest normal gap of an irregular cron ("weekdays").
_SAMPLED_FIRES = 8


@dataclass(frozen=True, slots=True)
class SourceGap:
    source_definition_id: UUID
    name: str
    cadence_seconds: float
    #: `None` when no scheduled run ever happened; `age_seconds` then counts from creation.
    last_scheduled_run_at: datetime | None
    age_seconds: float


@dataclass(frozen=True, slots=True)
class CollectionGapReport:
    now: datetime
    factor: float
    evaluated_sources: int
    #: The fastest cadence among evaluated sources: how often *something* should run.
    global_cadence_seconds: float | None
    last_scheduled_run_at: datetime | None
    global_overdue: bool
    overdue_sources: tuple[SourceGap, ...]

    @property
    def overdue_source_ids(self) -> frozenset[UUID]:
        return frozenset(gap.source_definition_id for gap in self.overdue_sources)

    @property
    def alarming(self) -> bool:
        return self.global_overdue or bool(self.overdue_sources)


def cadence_seconds(schedule: str, *, reference: datetime) -> float | None:
    """Longest gap between consecutive fires of `schedule` from `reference`, in seconds.

    The longest, not the mean: "weekdays only" legitimately goes silent over a weekend.
    `None` for an expression that never fires twice.
    """
    trigger = CronTrigger.from_crontab(schedule, timezone="UTC")
    fires: list[datetime] = []
    previous: datetime | None = None
    moment = reference
    for _ in range(_SAMPLED_FIRES):
        fire = trigger.get_next_fire_time(previous, moment)
        if fire is None:
            break
        fires.append(fire)
        previous, moment = fire, fire
    if len(fires) < 2:
        return None
    return max((b - a).total_seconds() for a, b in zip(fires, fires[1:], strict=False))


def collection_gap_report(
    session: Session, *, now: datetime | None = None, factor: float = GAP_FACTOR
) -> CollectionGapReport:
    reference = now or datetime.now(UTC)
    sources = list(
        session.scalars(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.enabled.is_(True),
                SourceDefinitionModel.source_type != "manual",
                SourceDefinitionModel.schedule.is_not(None),
            )
        )
    )
    last_runs: dict[UUID, datetime] = {
        source_id: started
        for source_id, started in session.execute(
            select(SourceRunModel.source_definition_id, func.max(SourceRunModel.started_at))
            .where(
                SourceRunModel.execution_trigger == "SCHEDULED",
                SourceRunModel.started_at.is_not(None),
            )
            .group_by(SourceRunModel.source_definition_id)
        )
    }
    gaps: list[SourceGap] = []
    cadences: list[float] = []
    latest: datetime | None = None
    for source in sources:
        cadence = cadence_seconds(source.schedule or "", reference=reference)
        if cadence is None:
            continue
        cadences.append(cadence)
        last = last_runs.get(source.id)
        if last is not None and (latest is None or last > latest):
            latest = last
        anchor = last or source.created_at
        age = (reference - anchor).total_seconds()
        if age > factor * cadence:
            gaps.append(SourceGap(source.id, source.name, cadence, last, age))
    gaps.sort(key=lambda gap: gap.age_seconds / gap.cadence_seconds, reverse=True)
    global_cadence = min(cadences) if cadences else None
    if global_cadence is None:
        global_overdue = False
    elif latest is None:
        global_overdue = bool(gaps)
    else:
        global_overdue = (reference - latest) > timedelta(seconds=factor * global_cadence)
    return CollectionGapReport(
        now=reference,
        factor=factor,
        evaluated_sources=len(cadences),
        global_cadence_seconds=global_cadence,
        last_scheduled_run_at=latest,
        global_overdue=global_overdue,
        overdue_sources=tuple(gaps),
    )
