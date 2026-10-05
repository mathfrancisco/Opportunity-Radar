"""F50-04: a changed off-target item under the noise filter is still seen as present."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
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
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _VersionedCollector:
    capabilities = CollectorCapabilities()

    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        self.version = 1

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type,
            external_id="sales-1",
            title="Account Executive",
            raw_payload={"id": "sales-1", "title": "Account Executive", "v": self.version},
            cursor="sales-1",
        )


class _LowShareRepository(AcquisitionRepository):
    def target_area_share(self, source_id: object, *, runs: int = 3) -> float | None:
        del source_id, runs
        return 0.0


def _cleanup(session: Session, source: SourceDefinitionModel) -> None:
    session.rollback()
    raw_ids = list(
        session.scalars(
            select(RawItemModel.id).where(RawItemModel.source_definition_id == source.id)
        )
    )
    occurrence_ids = list(
        session.scalars(
            select(SourceOccurrenceModel.id).where(
                SourceOccurrenceModel.source_definition_id == source.id
            )
        )
    )
    opportunity_ids = list(
        session.scalars(
            select(SourceOccurrenceModel.opportunity_id).where(
                SourceOccurrenceModel.id.in_(occurrence_ids)
            )
        )
    )
    session.execute(
        delete(SourceOccurrenceObservationModel).where(
            SourceOccurrenceObservationModel.raw_item_id.in_(raw_ids)
            | SourceOccurrenceObservationModel.source_occurrence_id.in_(occurrence_ids)
        )
    )
    session.execute(
        delete(NormalizationResultModel).where(NormalizationResultModel.raw_item_id.in_(raw_ids))
    )
    session.execute(
        delete(SourceOccurrenceModel).where(SourceOccurrenceModel.id.in_(occurrence_ids))
    )
    session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
    session.execute(
        delete(SourceCheckpointModel).where(SourceCheckpointModel.source_definition_id == source.id)
    )
    session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_ids)))
    session.execute(delete(SourceRunModel).where(SourceRunModel.source_definition_id == source.id))
    session.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id))
    session.commit()


def test_changed_off_target_item_is_not_closed_as_absent() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        source_type = f"filtered_{uuid4().hex[:8]}"
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type=source_type,
            name=f"filtered {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(source)
        session.commit()
        collector = _VersionedCollector(source_type)
        registry = CollectorRegistry((collector,))  # type: ignore[arg-type]

        def run(*, filtered: bool) -> SourceRunModel:
            service = AcquisitionService(
                session,
                registry=registry,
                repository=(
                    _LowShareRepository(session) if filtered else AcquisitionRepository(session)
                ),
                target_role_families=(lambda: ("SOFTWARE_ENGINEERING",)) if filtered else None,
                target_area_floor=0.30 if filtered else 0.0,
            )
            return asyncio.run(
                service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )

        try:
            run(filtered=False)
            raw_ids = list(
                session.scalars(
                    select(RawItemModel.id).where(RawItemModel.source_definition_id == source.id)
                )
            )
            assert len(raw_ids) == 1
            OpportunityService(session).normalize(raw_ids[0])

            collector.version = 2  # content changed: the envelope lookup now misses
            second = run(filtered=True)
            third = run(filtered=True)

            assert second.complete and third.complete
            assert third.items_persisted == 0
            assert (
                len(
                    list(
                        session.scalars(
                            select(RawItemModel.id).where(
                                RawItemModel.source_definition_id == source.id
                            )
                        )
                    )
                )
                == 1
            )
            missing = OpportunityRepository(session).occurrences_missing_from_both_runs(
                source.id, current_run_id=third.id, previous_complete_run_id=second.id
            )
            assert missing == []
        finally:
            _cleanup(session, source)
