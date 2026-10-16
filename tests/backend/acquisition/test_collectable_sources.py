"""Which sources the scheduled pass considers (card F48-01).

`collect_enabled_sources` used to read the first 100 definitions by name and filter
afterwards, so an eligible source past position 100 never entered the clock.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionRequest,
    CollectorCapabilities,
    ExecutionTrigger,
    HealthResult,
)
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.worker import collect_enabled_sources as _collect_enabled_sources

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_NOON = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
_PREFIX = "collectable-test:"
_TEST_OWNER = "collectable-sources-test-owner"


def collect_enabled_sources(*args: object, **kwargs: object) -> None:
    """Run the pass as this fixture's explicit synthetic operational identity."""
    _collect_enabled_sources(*args, owner_sub=_TEST_OWNER, **kwargs)  # type: ignore[arg-type]


def _engine():
    return create_database_engine(os.environ["DATABASE_URL"])


@pytest.fixture(autouse=True)
def _remove_seeded_sources() -> Iterator[None]:
    yield
    with Session(_engine()) as session:
        ids = list(
            session.scalars(
                select(SourceDefinitionModel.id).where(
                    SourceDefinitionModel.name.startswith(_PREFIX)
                )
            )
        )
        for model in (RawItemModel, SourceRunModel, SourceCheckpointModel):
            session.execute(delete(model).where(model.source_definition_id.in_(ids)))
        session.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id.in_(ids)))
        session.commit()


class _StubCollector:
    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        self.capabilities = CollectorCapabilities(keyword_search=False)

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        # No items: a run is enough to prove the source was reached, and it leaves no
        # raw items or occurrences behind to clean up.
        del request
        return
        yield  # pragma: no cover - keeps this an async generator


_CRON = "0 * * * *"


def _seed(
    session: Session,
    source_type: str,
    name: str,
    *,
    enabled: bool = True,
    schedule: str | None = _CRON,
    company_source_id: UUID | None = None,
) -> UUID:
    source = SourceDefinitionModel(
        source_type=source_type,
        name=f"{_PREFIX}{name}",
        enabled=enabled,
        schedule=schedule,
        company_source_id=company_source_id,
        evidence_status="confirmed",
        reviewed_at=datetime.now(UTC),
        terms_reviewed=True,
        collector_local_tested=True,
    )
    session.add(source)
    session.commit()
    return source.id


def test_the_pass_reaches_every_eligible_source_past_the_first_hundred(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_type = f"example_{uuid4().hex[:8]}"
    engine = _engine()
    with Session(engine) as session:
        # Names sort "a-000" .. "a-149": well beyond the old 100-row window.
        eligible = [_seed(session, source_type, f"a-{index:03d}") for index in range(150)]
        disabled = _seed(session, source_type, "a-075-disabled", enabled=False)
        manual = _seed(session, "manual", "a-076-manual")

    def build(session: Session) -> AcquisitionService:
        registry = CollectorRegistry([_StubCollector(source_type)])
        return AcquisitionService(session, registry=registry)

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        collect_enabled_sources(engine, now=_NOON, service_factory=build)

    reported = {
        getattr(record, "source_id", None): getattr(record, "outcome", None)
        for record in caplog.records
        if getattr(record, "source_id", None)
    }
    assert {reported.get(str(source_id)) for source_id in eligible} == {"completed"}
    assert str(disabled) not in reported
    assert str(manual) not in reported
    with Session(engine) as session:
        assert not session.scalars(
            select(SourceRunModel.id).where(
                SourceRunModel.source_definition_id.in_([disabled, manual])
            )
        ).all()


def test_collectable_sources_are_unbounded_and_never_collected_come_first() -> None:
    source_type = f"example_{uuid4().hex[:8]}"
    engine = _engine()
    with Session(engine) as session:
        early = _seed(session, source_type, "a-early")
        late = _seed(session, source_type, "b-late")
        never = _seed(session, source_type, "z-never")
        _seed(session, source_type, "c-off", enabled=False)
        _seed(session, "manual", "c-manual")
        for source_id, hours_ago in ((early, 3), (late, 1)):
            started_at = _NOON - timedelta(hours=hours_ago)
            session.add(
                SourceRunModel(
                    source_definition_id=source_id,
                    execution_trigger=ExecutionTrigger.SCHEDULED.value,
                    status="SUCCEEDED",
                    started_at=started_at,
                    finished_at=started_at + timedelta(seconds=5),
                )
            )
        session.commit()

    with Session(engine) as session:
        sources = AcquisitionRepository(session).list_collectable_sources()

    ours = [source.id for source in sources if source.name.startswith(_PREFIX)]
    # Never collected first even though it sorts last by name; then the rest by name.
    assert ours == [never, early, late]
    assert all(source.enabled and source.source_type != "manual" for source in sources)


class _OurSourcesService(AcquisitionService):
    """Only this module's seeded sources, so a shared test database's leftovers do not count."""

    def list_collectable_sources(self) -> list[SourceDefinitionModel]:
        return [s for s in super().list_collectable_sources() if s.name.startswith(_PREFIX)]


def _succeeded_run(session: Session, source_id: UUID, started_at: datetime) -> None:
    session.add(
        SourceRunModel(
            source_definition_id=source_id,
            execution_trigger=ExecutionTrigger.SCHEDULED.value,
            status="SUCCEEDED",
            started_at=started_at,
            finished_at=started_at + timedelta(seconds=5),
        )
    )
    session.commit()


def test_collectable_sources_are_ordered_by_staleness_weighted_by_priority() -> None:
    source_type = f"example_{uuid4().hex[:8]}"
    engine = _engine()
    suffix = uuid4().hex[:8]
    company_ids: list[UUID] = []
    with Session(engine) as session:
        try:
            linked: dict[str, UUID] = {}
            for priority in ("low", "high"):
                company = Company(
                    canonical_name=f"{_PREFIX}{priority}-{suffix}",
                    normalized_name=f"{_PREFIX}{priority}-{suffix}",
                    priority=priority,
                )
                company.sources.append(
                    CompanySource(source_type=source_type, endpoint=f"https://{priority}.test/{suffix}")
                )
                session.add(company)
                session.commit()
                company_ids.append(company.id)
                linked[priority] = company.sources[0].id
            low = _seed(session, source_type, "a-low", company_source_id=linked["low"])
            high = linked["high"]
            high_recent = _seed(session, source_type, "b-high-recent", company_source_id=high)
            high_stale = _seed(session, source_type, "c-high-stale", company_source_id=high)
            normal_never = _seed(session, source_type, "d-normal-never")
            now = datetime.now(UTC)
            for source_id, hours_ago in ((low, 40), (high_recent, 1), (high_stale, 20)):
                _succeeded_run(session, source_id, now - timedelta(hours=hours_ago))
            # A newer failure must not move the source: the order reads the last success.
            session.add(
                SourceRunModel(
                    source_definition_id=high_stale,
                    execution_trigger=ExecutionTrigger.SCHEDULED.value,
                    status="FAILED",
                    started_at=now,
                    finished_at=now,
                )
            )
            session.commit()

            sources = AcquisitionRepository(session).list_collectable_sources()
            ours = [source.id for source in sources if source.name.startswith(_PREFIX)]

            # Never succeeded first; then age x weight: high 20 h x 3 = 60, low 40 h x 1 = 40,
            # high 1 h x 3 = 3. A stale low-priority source runs before a fresh high one.
            assert ours == [normal_never, high_stale, low, high_recent]
            assert ours.index(low) < ours.index(high_recent)
        finally:
            session.rollback()
            session.execute(
                update(SourceDefinitionModel)
                .where(SourceDefinitionModel.name.startswith(_PREFIX))
                .values(company_source_id=None)
            )
            session.execute(delete(Company).where(Company.id.in_(company_ids)))
            session.commit()


def test_the_window_runs_due_manual_sources_and_reports_executed_over_eligible() -> None:
    source_type = f"example_{uuid4().hex[:8]}"
    engine = _engine()
    with Session(engine) as session:
        never = _seed(session, source_type, "a-null-never", schedule=None)
        stale = _seed(session, source_type, "b-manual-stale", schedule="manual")
        fresh = _seed(session, source_type, "c-manual-fresh", schedule="Manual")
        cron = _seed(session, source_type, "d-cron-due")
        _succeeded_run(session, stale, _NOON - timedelta(hours=2))
        _succeeded_run(session, fresh, _NOON - timedelta(minutes=10))
        _succeeded_run(session, cron, _NOON - timedelta(hours=3))

    def build(session: Session) -> AcquisitionService:
        return _OurSourcesService(
            session, registry=CollectorRegistry([_StubCollector(source_type)])
        )

    counts = _collect_enabled_sources(
        engine,
        now=_NOON,
        service_factory=build,
        owner_sub=_TEST_OWNER,
        manual_min_interval_hours=1,
    )

    assert counts["eligible"] == 3  # never, stale and the cron source; fresh is not due
    assert counts["executed"] == 3
    assert counts["completed"] == 3
    with Session(engine) as session:
        runs_per_source = {
            source_id: len(
                session.scalars(
                    select(SourceRunModel.id).where(
                        SourceRunModel.source_definition_id == source_id
                    )
                ).all()
            )
            for source_id in (never, stale, fresh, cron)
        }
    assert runs_per_source == {never: 1, stale: 2, fresh: 1, cron: 2}


def test_without_the_interval_manual_sources_stay_skipped() -> None:
    source_type = f"example_{uuid4().hex[:8]}"
    engine = _engine()
    with Session(engine) as session:
        never = _seed(session, source_type, "a-null-never", schedule=None)
        stale = _seed(session, source_type, "b-manual-stale", schedule="manual")
        _succeeded_run(session, stale, _NOON - timedelta(hours=2))

    def build(session: Session) -> AcquisitionService:
        return _OurSourcesService(
            session, registry=CollectorRegistry([_StubCollector(source_type)])
        )

    counts = _collect_enabled_sources(
        engine, now=_NOON, service_factory=build, owner_sub=_TEST_OWNER
    )

    assert counts["eligible"] == 0
    assert counts["executed"] == 0
    with Session(engine) as session:
        assert not session.scalars(
            select(SourceRunModel.id).where(
                SourceRunModel.source_definition_id == never,
            )
        ).all()
