"""A 72-hour operating window, proved in minutes against a controlled clock.

The real gate is three days of a worker nobody touches. Waiting three days per change is
not a gate anyone runs, so the same window is replayed here step by step: the jobs are the
production ones, the database is real, and only time is simulated. What must not be
simulated is the semantics of time — the delay threshold, the failure streak and the
retention horizon are all evaluated against the simulated clock, so shortening the wall
clock cannot shorten any of them.

The scripted source is the point of the exercise. A gate where everything succeeds proves
only that nothing was tried: this one takes the source down for three consecutive passes
and brings it back, so the alert, its deduplication and the recovery are all observed
rather than assumed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar import worker
from opportunity_radar.acquisition.alerts import SourceAlertService
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionRequest,
    CollectorCapabilities,
    HealthcheckContext,
    HealthResult,
)
from opportunity_radar.acquisition.models import (
    PayloadRetentionEventModel,
    RawItemModel,
    RawItemPayloadModel,
    SourceAlertIncidentModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.dashboard.metrics import source_metrics
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.operations.models import WorkerJobStateModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    ProfileNotFoundError,
    ProfileSnapshot,
    Skill,
)
from opportunity_radar.profile.service import ProfileService

#: The window the roadmap asks the system to survive without intervention.
SOAK_HOURS = 72
#: One simulated pass per hour keeps every job's schedule inside its own interval.
SOAK_STEP_MINUTES = 60
#: The scripted outage: three consecutive failures, which is exactly the alert threshold.
OUTAGE_STEPS = (24, 25, 26)
SOAK_SOURCE_TYPE = "soak-probe"


@dataclass(frozen=True, slots=True)
class SoakCheck:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class SoakResult:
    hours: int
    steps: int
    started_at: datetime
    ended_at: datetime
    checks: tuple[SoakCheck, ...] = ()

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "hours": self.hours,
            "steps": self.steps,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "passed": self.passed,
            "checks": [check.as_dict() for check in self.checks],
        }


class ScriptedCollector:
    """A source whose availability the gate decides, one pass at a time."""

    source_type = SOAK_SOURCE_TYPE
    capabilities = CollectorCapabilities()

    def __init__(self) -> None:
        self.step = 0
        self.available = True

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        return HealthResult(healthy=self.available, summary="scripted probe")

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        del request
        if not self.available:
            raise AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                "scripted outage",
            )
        yield CollectedItem(
            source_type=self.source_type,
            raw_payload={"title": f"Soak posting {self.step}"},
            external_id=f"soak-{self.step}",
            url=f"https://soak.invalid/jobs/{self.step}",
            title="Senior Python Engineer",
            company_name="Soak Probe",
            location_text="Remote",
            description="Required: Python.",
            metadata={"seniority": "senior"},
        )


@dataclass
class _Bootstrap:
    source_id: UUID
    aged_raw_item_id: UUID
    collector: ScriptedCollector
    service_factory: Callable[[Session], AcquisitionService]
    checks: list[SoakCheck] = field(default_factory=list)


def run_soak(
    engine: Engine,
    settings: Settings,
    *,
    hours: int = SOAK_HOURS,
    step_minutes: int = SOAK_STEP_MINUTES,
    start: datetime | None = None,
    retention_days: int = 365,
) -> SoakResult:
    """Replay `hours` of unattended operation and report what the window proved.

    `start` must not be in the past. A run stamps itself with the wall clock, and the
    schedule is evaluated against the simulated one: a window that began before now would
    ask whether a source that just ran was due an hour *before* it ran, and the answer —
    correctly — would be no, for every pass after the first.
    """
    started_at = start or datetime.now(UTC)
    steps = max(1, (hours * 60) // step_minutes)
    bootstrap = _bootstrap(engine, settings, started_at, retention_days=retention_days)
    adapter = build_analysis_adapter(settings, engine)

    clock = started_at
    for step in range(steps):
        clock = started_at + timedelta(minutes=step_minutes * step)
        bootstrap.collector.step = step
        bootstrap.collector.available = step not in OUTAGE_STEPS
        worker.collect_enabled_sources(
            engine,
            timezone="UTC",
            now=clock,
            backoff_base_seconds=settings.collection_backoff_base_seconds,
            backoff_ceiling_seconds=settings.collection_backoff_ceiling_seconds,
            service_factory=bootstrap.service_factory,
        )
        worker.normalize_opportunities(engine)
        worker.evaluate_pending(engine, batch_size=settings.worker_evaluate_batch_size)
        worker.analyze_pending(
            engine,
            adapter,
            batch_size=settings.worker_analyze_batch_size,
            eligible_verdicts=settings.analysis_eligible_verdicts,
        )
        # Retention runs on its own slower cadence, exactly as the scheduler drives it.
        if step % 6 == 0:
            worker.expire_raw_payloads(
                engine,
                retention_days=retention_days,
                batch_size=settings.payload_retention_batch_size,
                now=clock,
            )

    checks = _verify(engine, bootstrap, retention_days=retention_days)
    return SoakResult(
        hours=hours,
        steps=steps,
        started_at=started_at,
        ended_at=clock,
        checks=tuple(checks),
    )


def _bootstrap(
    engine: Engine,
    settings: Settings,
    started_at: datetime,
    *,
    retention_days: int,
) -> _Bootstrap:
    """Everything the gate is allowed to do by hand. After this, only jobs run."""
    collector = ScriptedCollector()
    registry = CollectorRegistry((collector,))

    def service_factory(session: Session) -> AcquisitionService:
        return AcquisitionService(
            session,
            registry=registry,
            alerts=SourceAlertService(
                session,
                notifier=None,
                threshold=settings.source_alert_failure_threshold,
            ),
        )

    with Session(engine) as session:
        _ensure_active_profile(session)
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type=SOAK_SOURCE_TYPE,
            name=f"soak probe {uuid4().hex[:8]}",
            enabled=True,
            schedule="* * * * *",
            configuration={},
            rate_limit_policy={},
            evidence_status="confirmed",
            reviewed_at=started_at,
            terms_reviewed=True,
            collector_local_tested=True,
        )
        session.add(source)
        session.flush()
        aged = _aged_raw_item(session, source, started_at, retention_days=retention_days)
        session.commit()
        return _Bootstrap(
            source_id=source.id,
            aged_raw_item_id=aged,
            collector=collector,
            service_factory=service_factory,
        )


def _ensure_active_profile(session: Session) -> None:
    service = ProfileService(session)
    try:
        service.get_active()
        return
    except ProfileNotFoundError:
        pass
    snapshot = ProfileSnapshot(
        skills=(Skill(canonical_name="python"),),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(
            work_modes=("REMOTE",),
            contracts=("FULL_TIME",),
            countries=("BR",),
            compensation_min=Decimal("1"),
            compensation_currency="USD",
            compensation_period="YEAR",
        ),
    )
    versions = service.list_versions()
    version = service.create_version(snapshot, len(versions))
    published = service.publish(version.id, len(versions) + 1)
    service.activate(published.id, len(versions) + 2)


def _aged_raw_item(
    session: Session,
    source: SourceDefinitionModel,
    started_at: datetime,
    *,
    retention_days: int,
) -> UUID:
    """A payload already past the horizon, so retention has something to decide about."""
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="ON_DEMAND",
        status="SUCCEEDED",
        started_at=started_at - timedelta(days=retention_days + 30),
        finished_at=started_at - timedelta(days=retention_days + 30),
    )
    session.add(run)
    session.flush()
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=f"aged-{uuid4().hex[:8]}",
        identity_key=f"external:aged-{uuid4().hex[:8]}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    raw_item.payload_record = RawItemPayloadModel(
        payload={"title": "Aged posting"},
        stored_at=started_at - timedelta(days=retention_days + 30),
    )
    session.add(raw_item)
    session.flush()
    return raw_item.id


def _verify(
    engine: Engine,
    bootstrap: _Bootstrap,
    *,
    retention_days: int,
) -> list[SoakCheck]:
    with Session(engine) as session:
        return [
            _check_jobs(session),
            _check_collection(session, bootstrap.source_id),
            _check_alert_and_recovery(session, bootstrap.source_id),
            # Metrics aggregate the timestamps the runs actually carry, and a run stamps
            # itself with the wall clock. Asking about the simulated window would ask
            # about hours in which, on the real clock, nothing was ever written.
            _check_metrics(session, bootstrap.source_id, datetime.now(UTC)),
            _check_retention(session, bootstrap.aged_raw_item_id, retention_days),
        ]


def _check_jobs(session: Session) -> SoakCheck:
    expected = set(worker.FUNCTIONAL_JOB_IDS)
    states = {
        state.job_name: state
        for state in session.scalars(select(WorkerJobStateModel))
        if state.job_name in expected
    }
    missing = sorted(expected - set(states))
    if missing:
        return SoakCheck(
            "jobs", False, f"no persisted state for: {', '.join(missing)}"
        )
    never_succeeded = sorted(
        name for name, state in states.items() if state.last_success_at is None
    )
    if never_succeeded:
        return SoakCheck(
            "jobs",
            False,
            f"job(s) never completed a pass: {', '.join(never_succeeded)}",
        )
    silently_failed = sorted(
        name
        for name, state in states.items()
        if state.last_failure_at is not None
        and state.last_success_at is not None
        and state.last_failure_at > state.last_success_at
    )
    if silently_failed:
        return SoakCheck(
            "jobs", False, f"job(s) ended the window failing: {', '.join(silently_failed)}"
        )
    return SoakCheck(
        "jobs", True, f"{len(states)} job(s) ran and ended the window healthy"
    )


def _check_collection(session: Session, source_id: UUID) -> SoakCheck:
    runs = list(
        session.scalars(
            select(SourceRunModel).where(
                SourceRunModel.source_definition_id == source_id,
                SourceRunModel.execution_trigger == "SCHEDULED",
            )
        )
    )
    succeeded = [run for run in runs if run.status == "SUCCEEDED"]
    failed = [run for run in runs if run.status == "FAILED"]
    if len(failed) < len(OUTAGE_STEPS):
        return SoakCheck(
            "collection",
            False,
            f"the scripted outage produced {len(failed)} failure(s), expected "
            f"{len(OUTAGE_STEPS)}",
        )
    if not succeeded:
        return SoakCheck("collection", False, "no scheduled run ever succeeded")
    persisted = sum(run.items_persisted for run in succeeded)
    if persisted == 0:
        return SoakCheck("collection", False, "collection never persisted an item")
    return SoakCheck(
        "collection",
        True,
        f"{len(succeeded)} successful and {len(failed)} failed scheduled run(s), "
        f"{persisted} item(s) persisted",
    )


def _check_alert_and_recovery(session: Session, source_id: UUID) -> SoakCheck:
    incidents = list(
        session.scalars(
            select(SourceAlertIncidentModel)
            .where(SourceAlertIncidentModel.source_definition_id == source_id)
            .order_by(SourceAlertIncidentModel.opened_at)
        )
    )
    if len(incidents) != 1:
        return SoakCheck(
            "alerting",
            False,
            f"expected exactly one incident for the scripted outage, found {len(incidents)}",
        )
    incident = incidents[0]
    if incident.consecutive_failures < len(OUTAGE_STEPS):
        return SoakCheck(
            "alerting",
            False,
            f"the incident opened after {incident.consecutive_failures} failure(s)",
        )
    if incident.recovered_at is None:
        return SoakCheck("alerting", False, "the incident never recovered")
    return SoakCheck(
        "alerting",
        True,
        "one incident opened after "
        f"{incident.consecutive_failures} failures and recovered at "
        f"{incident.recovered_at.isoformat()}",
    )


def _check_metrics(session: Session, source_id: UUID, ended_at: datetime) -> SoakCheck:
    report = source_metrics(session, now=ended_at)
    if not report.windows:
        return SoakCheck("metrics", False, "the metrics report answered no window")
    for window in report.windows:
        metrics = next(
            (
                item
                for item in window.sources
                if item.source_definition_id == source_id
            ),
            None,
        )
        if metrics is None:
            return SoakCheck(
                "metrics", False, f"the {window.window} window omits the soak source"
            )
        if not metrics.has_runs:
            return SoakCheck(
                "metrics",
                False,
                f"the {window.window} window reports no run for the soak source",
            )
    return SoakCheck(
        "metrics",
        True,
        f"{len(report.windows)} window(s) report the soak source with runs",
    )


def _check_retention(
    session: Session, raw_item_id: UUID, retention_days: int
) -> SoakCheck:
    payload = session.get(RawItemPayloadModel, raw_item_id)
    envelope = session.get(RawItemModel, raw_item_id)
    if payload is None or envelope is None:
        return SoakCheck("retention", False, "the aged raw item disappeared")
    if payload.payload is not None:
        return SoakCheck(
            "retention",
            False,
            f"a payload older than {retention_days} days was not expired",
        )
    events = list(
        session.scalars(
            select(PayloadRetentionEventModel).where(
                PayloadRetentionEventModel.raw_item_id == raw_item_id
            )
        )
    )
    if len(events) != 1:
        return SoakCheck(
            "retention",
            False,
            f"expected one retention history row, found {len(events)}",
        )
    if envelope.payload_hash != events[0].payload_hash:
        return SoakCheck("retention", False, "the expiry did not preserve the hash")
    return SoakCheck(
        "retention",
        True,
        "the aged payload expired once, with its envelope and hash intact",
    )


__all__ = [
    "OUTAGE_STEPS",
    "SOAK_HOURS",
    "SOAK_SOURCE_TYPE",
    "SOAK_STEP_MINUTES",
    "ScriptedCollector",
    "SoakCheck",
    "SoakResult",
    "run_soak",
]
