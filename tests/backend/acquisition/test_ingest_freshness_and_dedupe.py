"""R55-E1 / R55-E3: stale items are dropped before storage; unchanged re-collection is free."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
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
    RawItemPayloadModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import STALE, AcquisitionRepository, RawEvidenceWrite
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _Collector:
    capabilities = CollectorCapabilities()

    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        self.items: list[CollectedItem] = []

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        for item in self.items:
            yield item


def _item(source_type: str, ext: str, *, published: datetime | None, v: int = 1) -> CollectedItem:
    return CollectedItem(
        source_type=source_type,
        external_id=ext,
        title=f"Backend Engineer {ext}",
        published_at=published,
        raw_payload={"id": ext, "title": f"Backend Engineer {ext}", "v": v},
        cursor=ext,
    )


class _World:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.source_type = f"fresh_{uuid4().hex[:8]}"
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type=self.source_type,
            name=f"fresh {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(self.source)
        session.commit()
        self.collector = _Collector(self.source_type)

    def run(self, *, max_age_days: int | None = None) -> SourceRunModel:
        service = AcquisitionService(
            self.session,
            registry=CollectorRegistry((self.collector,)),  # type: ignore[arg-type]
            ingest_max_age_days=max_age_days,
        )
        return asyncio.run(
            service.execute(self.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )

    def counts(self) -> tuple[int, int, int]:
        """(raw items, payloads, observations) stored for this source."""
        self.session.expire_all()
        raw_ids = select(RawItemModel.id).where(RawItemModel.source_definition_id == self.source.id)
        raw = self.session.scalar(select(func.count()).select_from(raw_ids.subquery())) or 0
        payload = (
            self.session.scalar(
                select(func.count())
                .select_from(RawItemPayloadModel)
                .where(RawItemPayloadModel.raw_item_id.in_(raw_ids))
            )
            or 0
        )
        obs = (
            self.session.scalar(
                select(func.count())
                .select_from(SourceOccurrenceObservationModel)
                .where(SourceOccurrenceObservationModel.raw_item_id.in_(raw_ids))
            )
            or 0
        )
        return raw, payload, obs

    def normalize_all(self) -> None:
        for raw_id in self.session.scalars(
            select(RawItemModel.id).where(RawItemModel.source_definition_id == self.source.id)
        ).all():
            OpportunityService(self.session).normalize(raw_id)

    def occurrence(self) -> SourceOccurrenceModel:
        self.session.expire_all()
        return self.session.scalars(
            select(SourceOccurrenceModel).where(
                SourceOccurrenceModel.source_definition_id == self.source.id
            )
        ).one()

    def cleanup(self) -> None:
        s = self.session
        s.rollback()
        raw_ids = list(
            s.scalars(
                select(RawItemModel.id).where(RawItemModel.source_definition_id == self.source.id)
            )
        )
        occ = list(
            s.scalars(
                select(SourceOccurrenceModel.id).where(
                    SourceOccurrenceModel.source_definition_id == self.source.id
                )
            )
        )
        opp = list(
            s.scalars(
                select(SourceOccurrenceModel.opportunity_id).where(
                    SourceOccurrenceModel.id.in_(occ)
                )
            )
        )
        s.execute(
            delete(SourceOccurrenceObservationModel).where(
                SourceOccurrenceObservationModel.raw_item_id.in_(raw_ids)
                | SourceOccurrenceObservationModel.source_occurrence_id.in_(occ)
            )
        )
        s.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id.in_(raw_ids)
            )
        )
        s.execute(delete(SourceOccurrenceModel).where(SourceOccurrenceModel.id.in_(occ)))
        s.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opp)))
        s.execute(
            delete(SourceCheckpointModel).where(
                SourceCheckpointModel.source_definition_id == self.source.id
            )
        )
        s.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_ids)))
        s.execute(
            delete(SourceRunModel).where(SourceRunModel.source_definition_id == self.source.id)
        )
        s.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id))
        s.commit()


def _session() -> Session:
    return Session(create_database_engine(os.environ["DATABASE_URL"]))


def _write(key: str, *, published: datetime | None) -> RawEvidenceWrite:
    return RawEvidenceWrite(
        identity_key=f"external:{key}",
        payload_hash=uuid4().hex + uuid4().hex,
        semantic_hash=None,
        semantic_hash_version=None,
        external_id=key,
        canonical_url=None,
        content_type=None,
        parser_version=None,
        metadata={},
        payload={"id": key},
        published_at=published,
    )


def test_age_boundary_six_seven_kept_eight_days_skipped() -> None:
    with _session() as session:
        world = _World(session)
        try:
            run = world.run()  # an empty run: only the FK parent the evidence rows need
            now = datetime.now(UTC)
            result = AcquisitionRepository(session).record_evidence_batch(
                source_id=world.source.id,
                run_id=run.id,
                writes=[
                    _write("d6", published=now - timedelta(days=6)),
                    _write("d7", published=now - timedelta(days=7)),
                    _write("d8", published=now - timedelta(days=8)),
                ],
                observed_at=now,
                stale_before=now - timedelta(days=7),
            )
            session.commit()
            assert result == [True, True, STALE]
            kept = set(
                session.scalars(
                    select(RawItemModel.external_id).where(
                        RawItemModel.source_definition_id == world.source.id
                    )
                )
            )
            assert kept == {"d6", "d7"}
        finally:
            world.cleanup()


def test_service_counts_skipped_stale_and_keeps_undated_new_items() -> None:
    with _session() as session:
        world = _World(session)
        try:
            now = datetime.now(UTC)
            world.collector.items = [
                _item(world.source_type, "fresh", published=now - timedelta(days=2)),
                _item(world.source_type, "old", published=now - timedelta(days=9)),
                _item(world.source_type, "undated", published=None),
            ]
            run = world.run(max_age_days=7)
            session.refresh(run)
            assert run.items_persisted == 2
            assert run.skipped_stale == 1
            assert run.items_skipped == 1
            stored = set(
                session.scalars(
                    select(RawItemModel.external_id).where(
                        RawItemModel.source_definition_id == world.source.id
                    )
                )
            )
            assert stored == {"fresh", "undated"}
        finally:
            world.cleanup()


def test_disabled_filter_keeps_old_items() -> None:
    with _session() as session:
        world = _World(session)
        try:
            old = datetime.now(UTC) - timedelta(days=30)
            world.collector.items = [_item(world.source_type, "old", published=old)]
            run = world.run(max_age_days=0)
            session.refresh(run)
            assert (run.items_persisted, run.skipped_stale) == (1, 0)
        finally:
            world.cleanup()


def test_undated_item_first_seen_over_a_week_ago_is_skipped_when_it_changes() -> None:
    with _session() as session:
        world = _World(session)
        try:
            world.collector.items = [_item(world.source_type, "u", published=None)]
            world.run(max_age_days=7)
            session.execute(
                update(RawItemModel)
                .where(RawItemModel.source_definition_id == world.source.id)
                .values(fetched_at=datetime.now(UTC) - timedelta(days=10))
            )
            session.commit()
            world.collector.items = [_item(world.source_type, "u", published=None, v=2)]
            run = world.run(max_age_days=7)
            session.refresh(run)
            assert run.skipped_stale == 1
            assert world.counts()[0] == 1  # no second raw item for the stale undated identity
        finally:
            world.cleanup()


def test_unchanged_recollection_writes_nothing_but_advances_last_seen() -> None:
    with _session() as session:
        world = _World(session)
        try:
            now = datetime.now(UTC)
            world.collector.items = [_item(world.source_type, "a", published=now)]
            first = world.run()
            world.normalize_all()
            before = world.counts()
            assert before == (1, 1, 1)
            seen_before = world.occurrence().last_seen_at

            second = world.run()
            assert world.counts() == before
            occurrence = world.occurrence()
            assert occurrence.last_seen_run_id == second.id != first.id
            assert occurrence.last_seen_at > seen_before
        finally:
            world.cleanup()


def test_changed_item_writes_new_raw_item_payload_and_observation() -> None:
    with _session() as session:
        world = _World(session)
        try:
            now = datetime.now(UTC)
            world.collector.items = [_item(world.source_type, "a", published=now)]
            world.run()
            world.normalize_all()
            world.collector.items = [_item(world.source_type, "a", published=now, v=2)]
            world.run()
            assert world.counts() == (2, 2, 2)
        finally:
            world.cleanup()


def test_reappearance_after_closure_keeps_an_observation() -> None:
    with _session() as session:
        world = _World(session)
        try:
            now = datetime.now(UTC)
            world.collector.items = [_item(world.source_type, "a", published=now)]
            world.run()
            world.normalize_all()
            occurrence = world.occurrence()
            session.execute(
                update(OpportunityModel)
                .where(OpportunityModel.id == occurrence.opportunity_id)
                .values(lifecycle_status="CLOSED")
            )
            session.commit()
            world.run()
            assert world.counts() == (1, 1, 2)
        finally:
            world.cleanup()


def test_stale_changed_item_with_stored_evidence_still_counts_as_present() -> None:
    from opportunity_radar.opportunities.models import OpportunityModel as _Opp
    from tests.backend.support.absence import age_occurrences

    with _session() as session:
        world = _World(session)
        try:
            now = datetime.now(UTC)
            world.collector.items = [_item(world.source_type, "a", published=now)]
            world.run(max_age_days=7)
            world.normalize_all()
            age_occurrences(session, [world.source.id])  # unseen for 25 h
            before = world.counts()

            # Changed content, and the source now dates it 10 days back: STALE, not stored.
            world.collector.items = [
                _item(world.source_type, "a", published=now - timedelta(days=10), v=2)
            ]
            run = world.run(max_age_days=7)
            session.refresh(run)
            assert run.skipped_stale == 1 and run.complete is True
            assert world.counts() == before  # no raw item, payload or observation
            occurrence = world.occurrence()
            assert occurrence.last_seen_run_id == run.id
            assert occurrence.last_seen_at > now - timedelta(hours=1)

            OpportunityService(session).reconcile_run_closures(run.id)
            assert session.get(_Opp, occurrence.opportunity_id).lifecycle_status != "CLOSED"

            # A closed opportunity reopens when its stale-changed posting is still listed.
            session.execute(
                update(_Opp)
                .where(_Opp.id == occurrence.opportunity_id)
                .values(lifecycle_status="CLOSED")
            )
            session.commit()
            again = world.run(max_age_days=7)
            OpportunityService(session).reconcile_run_closures(again.id)
            session.expire_all()
            assert session.get(_Opp, occurrence.opportunity_id).lifecycle_status != "CLOSED"
        finally:
            world.cleanup()


def test_brand_new_stale_item_is_not_present_anywhere() -> None:
    with _session() as session:
        world = _World(session)
        try:
            world.collector.items = [
                _item(world.source_type, "old", published=datetime.now(UTC) - timedelta(days=9))
            ]
            world.run(max_age_days=7)
            assert world.counts() == (0, 0, 0)
        finally:
            world.cleanup()


def test_stale_item_still_advances_the_checkpoint_cursor() -> None:
    with _session() as session:
        world = _World(session)
        try:
            now = datetime.now(UTC)
            world.collector.items = [
                _item(world.source_type, "a", published=now),
                _item(world.source_type, "z-old", published=now - timedelta(days=9)),
            ]
            world.run(max_age_days=7)
            cursor = session.scalar(
                select(SourceCheckpointModel.cursor).where(
                    SourceCheckpointModel.source_definition_id == world.source.id
                )
            )
            assert cursor == "z-old"
        finally:
            world.cleanup()
