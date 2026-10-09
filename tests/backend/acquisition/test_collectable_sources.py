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
from sqlalchemy import delete, select
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


def _seed(session: Session, source_type: str, name: str, *, enabled: bool = True) -> UUID:
    source = SourceDefinitionModel(
        source_type=source_type,
        name=f"{_PREFIX}{name}",
        enabled=enabled,
        schedule="0 * * * *",
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
