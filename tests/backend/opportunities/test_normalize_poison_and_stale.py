"""R55-B1 review: a poison item does not stall the queue; stale postings are not resurrected."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.acquisition.models import RawItemModel
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
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


def _prior_failed_result(session: Session, raw_id) -> None:
    session.add(
        NormalizationResultModel(
            raw_item_id=raw_id,
            status="FAILED",
            normalizer_version="v6",
            reasons=[{"code": "INVALID_COLLECTED_ITEM_V1"}],
            error_summary="older version failure",
        )
    )
    session.commit()


def _age(session: Session, raw_id, days: int) -> None:
    session.execute(
        update(RawItemModel)
        .where(RawItemModel.id == raw_id)
        .values(fetched_at=datetime.now(UTC) - timedelta(days=days))
    )
    session.commit()


def _integrity_error() -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception("duplicate key value"))


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
            pending = OpportunityService(session).repository.pending_raw_item_ids(
                500, NORMALIZER_VERSION
            )
            assert not ours & set(pending)
        finally:
            monkeypatch.undo()
            fixture.cleanup()


def test_an_integrity_race_leaves_the_item_pending_and_the_batch_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raws = _collect(
                fixture,
                [
                    _item(fixture.source_type, external_id=f"i-{index}", title=f"Racer {index}")
                    for index in range(3)
                ],
            )
            racer = raws[0]
            original = OpportunityService.normalize

            def normalize(self: OpportunityService, raw_item_id):
                if raw_item_id == racer.id:
                    raise _integrity_error()
                return original(self, raw_item_id)

            monkeypatch.setattr(OpportunityService, "normalize", normalize)

            OpportunityService(session).normalize_pending(limit=50)

            assert _results(session, racer.id) == []  # no permanent FAILED
            for raw in raws[1:]:
                assert [r.status for r in _results(session, raw.id)] == ["SUCCEEDED"]
            pending = OpportunityService(session).repository.pending_raw_item_ids(
                500, NORMALIZER_VERSION
            )
            assert racer.id in pending  # tried again on the next pass
        finally:
            monkeypatch.undo()
            fixture.cleanup()


def test_an_integrity_race_returns_the_result_the_winner_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            [raw] = _collect(
                fixture, [_item(fixture.source_type, external_id="w-1", title="Raced Engineer")]
            )
            original = OpportunityService.normalize

            def normalize(self: OpportunityService, raw_item_id):
                original(self, raw_item_id)  # the concurrent winner commits its result
                raise _integrity_error()  # ... and this caller loses the race

            monkeypatch.setattr(OpportunityService, "normalize", normalize)

            batch = OpportunityService(session).normalize_pending(limit=50)

            assert batch.processed >= 1
            [stored] = _results(session, raw.id)
            assert stored.status == "SUCCEEDED"
        finally:
            monkeypatch.undo()
            fixture.cleanup()


def test_a_failure_while_recording_the_failure_rolls_back_and_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            _collect(
                fixture, [_item(fixture.source_type, external_id="f-1", title="Doomed Engineer")]
            )
            rolled_back: list[bool] = []

            def failing_normalize(self: OpportunityService, _raw_item_id):
                raise KeyError("poison")

            def failing_commit() -> None:
                raise RuntimeError("commit failed")

            monkeypatch.setattr(OpportunityService, "normalize", failing_normalize)
            monkeypatch.setattr(session, "commit", failing_commit)
            monkeypatch.setattr(session, "rollback", lambda: rolled_back.append(True))

            with pytest.raises(RuntimeError, match="commit failed"):
                OpportunityService(session).normalize_pending(limit=1)

            assert len(rolled_back) >= 2  # after the item error, and after the record error
        finally:
            monkeypatch.undo()
            fixture.cleanup()


def test_reprocessing_an_old_failed_item_does_not_resurrect_a_stale_posting() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            # Collected undated, so the collector's cutoff let it through; first stored 40 days
            # ago, failed under v6, and now reprocessed under v7 with no occurrence.
            [raw] = _collect(
                fixture, [_item(fixture.source_type, external_id="old-1", title="Old Engineer")]
            )
            _age(session, raw.id, 40)
            _prior_failed_result(session, raw.id)

            result = OpportunityService(session).normalize(raw.id)

            assert result.status == "FAILED"
            assert result.reasons == [{"code": "STALE_POSTING_SKIPPED"}]
            assert result.opportunity_id is None
            assert not session.scalars(
                select(SourceOccurrenceModel.id).where(SourceOccurrenceModel.raw_item_id == raw.id)
            ).all()
        finally:
            fixture.cleanup()


def test_a_fresh_undated_item_waiting_in_the_backlog_is_still_normalized() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            [raw] = _collect(
                fixture, [_item(fixture.source_type, external_id="w-1", title="Waiting Engineer")]
            )
            _age(session, raw.id, 9)  # waited 9 days, but never had a result: first time

            result = OpportunityService(session).normalize(raw.id)

            assert result.status == "SUCCEEDED"
            assert result.opportunity_id is not None
        finally:
            fixture.cleanup()


def test_a_reprocessed_item_whose_identity_was_stored_recently_is_not_stale() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            [raw] = _collect(
                fixture, [_item(fixture.source_type, external_id="r-1", title="Recent Engineer")]
            )
            _age(session, raw.id, 2)
            _prior_failed_result(session, raw.id)

            assert OpportunityService(session).normalize(raw.id).status == "SUCCEEDED"
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
            _age(session, raw.id, 30)

            result = service.normalize(raw.id)

            assert result.status == "SUCCEEDED"  # the occurrence exists: refreshed, not stale
        finally:
            fixture.cleanup()
