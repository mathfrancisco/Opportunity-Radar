"""R55-B1 review: a poison item does not stall the queue; stale postings are not resurrected."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.acquisition.models import RawItemModel
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.service import NORMALIZER_VERSION, OpportunityService
from tests.backend.acquisition.test_delta_presence_resume import (
    _engine,
    _Fixture,
    _item,
    _StaticCollector,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _collect(fixture: _Fixture, items: list) -> list[RawItemModel]:
    collector = _StaticCollector(fixture.source_type, [items])
    asyncio.run(
        fixture.service(collector).execute(
            fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
        )
    )
    return fixture.raw_items()


def _results(session: Session, raw_id) -> list[NormalizationResultModel]:
    return list(
        session.scalars(
            select(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id == raw_id,
                NormalizationResultModel.normalizer_version == NORMALIZER_VERSION,
            )
        )
    )


def test_a_poison_item_is_recorded_as_failed_and_the_next_one_is_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            items = [
                _item(fixture.source_type, external_id=f"p-{index}", title=f"Engineer {index}")
                for index in range(3)
            ]
            raws = _collect(fixture, items)
            poison = raws[0]
            original = OpportunityService.normalize

            def normalize(self: OpportunityService, raw_item_id):
                if raw_item_id == poison.id:
                    raise RuntimeError("synthetic poison")
                return original(self, raw_item_id)

            monkeypatch.setattr(OpportunityService, "normalize", normalize)

            batch = OpportunityService(session).normalize_pending(limit=50)

            ours = {raw.id for raw in raws}
            assert batch.processed >= 3
            [failed] = _results(session, poison.id)
            assert failed.status == "FAILED"
            assert failed.reasons[0]["code"] == "NORMALIZATION_ERROR"
            for raw in raws[1:]:
                assert [r.status for r in _results(session, raw.id)] == ["SUCCEEDED"]
            # Not pending again: the next pass does not meet the poison item.
            pending = OpportunityService(session).repository.pending_raw_item_ids(
                500, NORMALIZER_VERSION
            )
            assert not ours & set(pending)
        finally:
            monkeypatch.undo()
            fixture.cleanup()


def test_renormalizing_an_old_failed_item_does_not_resurrect_a_stale_posting() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            # Collected undated, so the collector's own cutoff lets it through; it is judged
            # at normalization by when it was first stored.
            old = _item(fixture.source_type, external_id="old-1", title="Backend Engineer")
            [raw] = _collect(fixture, [old])
            # A v6-era FAILED item without occurrence, collected before the ingestion cutoff.
            session.execute(
                update(RawItemModel)
                .where(RawItemModel.id == raw.id)
                .values(fetched_at=datetime.now(UTC) - timedelta(days=40))
            )
            session.commit()

            result = OpportunityService(session).normalize(raw.id)

            assert result.status == "FAILED"
            assert result.reasons == [{"code": "STALE_POSTING_SKIPPED"}]
            assert result.opportunity_id is None
            assert not session.scalars(
                select(SourceOccurrenceModel.id).where(SourceOccurrenceModel.raw_item_id == raw.id)
            ).all()
        finally:
            fixture.cleanup()


def test_an_undated_item_first_stored_long_ago_is_stale_but_a_recent_one_is_not() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raws = _collect(
                fixture,
                [
                    _item(fixture.source_type, external_id="u-old", title="Old Engineer"),
                    _item(fixture.source_type, external_id="u-new", title="New Engineer"),
                ],
            )
            old = next(raw for raw in raws if raw.external_id == "u-old")
            new = next(raw for raw in raws if raw.external_id == "u-new")
            session.execute(
                update(RawItemModel)
                .where(RawItemModel.id == old.id)
                .values(fetched_at=datetime.now(UTC) - timedelta(days=9))
            )
            session.commit()
            service = OpportunityService(session)

            assert service.normalize(old.id).status == "FAILED"
            assert service.normalize(new.id).status == "SUCCEEDED"
            stale_title = OpportunityModel.canonical_title == "Old Engineer"
            assert session.scalar(select(OpportunityModel.id).where(stale_title)) is None
        finally:
            fixture.cleanup()


def test_a_posting_that_already_has_an_occurrence_is_refreshed_not_skipped() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            [raw] = _collect(
                fixture, [_item(fixture.source_type, external_id="k-1", title="Kept Engineer")]
            )
            service = OpportunityService(session)
            assert service.normalize(raw.id).status == "SUCCEEDED"
            session.execute(
                update(NormalizationResultModel)
                .where(NormalizationResultModel.raw_item_id == raw.id)
                .values(normalizer_version="v6")
            )
            session.execute(
                update(RawItemModel)
                .where(RawItemModel.id == raw.id)
                .values(fetched_at=datetime.now(UTC) - timedelta(days=30))
            )
            session.commit()

            result = service.normalize(raw.id)

            assert result.status == "SUCCEEDED"  # the occurrence exists: refreshed, not stale
        finally:
            fixture.cleanup()
