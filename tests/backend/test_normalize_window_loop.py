"""R55-B1: the window normalizes its whole backlog in batches, and stops between them."""

from __future__ import annotations

import asyncio
import os
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar import worker
from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.opportunities.models import NormalizationResultModel
from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from tests.backend.acquisition.test_delta_presence_resume import (
    _engine,
    _Fixture,
    _item,
    _StaticCollector,
)


def _patch_unit(monkeypatch: pytest.MonkeyPatch, service: object) -> None:
    monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(object()))
    monkeypatch.setattr(worker, "OpportunityService", lambda _session: service)
    monkeypatch.setattr(worker, "observe_job", lambda *_args, **_kwargs: nullcontext())


def test_normalize_loops_until_the_backlog_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    backlog = [225]
    limits: list[int] = []

    class Service:
        def normalize_pending(self, limit: int, *, should_stop=None) -> SimpleNamespace:
            limits.append(limit)
            taken = min(limit, backlog[0])
            backlog[0] -= taken
            return SimpleNamespace(
                processed=taken, succeeded=taken - 1 if taken else 0, review_required=0,
                failed=1 if taken else 0,
            )

    _patch_unit(monkeypatch, Service())

    result = worker.normalize_opportunities(object(), stop_requested=lambda: False, batch_size=50)

    assert limits == [50, 50, 50, 50, 50]  # 4 full batches and a last one of 25
    assert backlog == [0]
    assert result["input"] == 225
    assert result["completed"] == 220  # one invalid item per non-empty batch
    assert result["failed"] == 5
    assert result["stopped"] == 0


def test_normalize_without_a_stop_callback_also_drains_the_backlog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backlog = [130]

    class Service:
        def normalize_pending(self, limit: int, *, should_stop=None) -> SimpleNamespace:
            taken = min(limit, backlog[0])
            backlog[0] -= taken
            return SimpleNamespace(processed=taken, succeeded=taken, review_required=0, failed=0)

    _patch_unit(monkeypatch, Service())

    assert worker.normalize_opportunities(object())["input"] == 130


def test_deadline_stops_between_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    batches: list[int] = []

    class Service:
        def normalize_pending(self, limit: int, *, should_stop=None) -> SimpleNamespace:
            batches.append(limit)
            return SimpleNamespace(processed=limit, succeeded=limit, review_required=0, failed=0)

    _patch_unit(monkeypatch, Service())

    # The deadline passes once two batches have run: no third batch is started.
    result = worker.normalize_opportunities(
        object(), stop_requested=lambda: len(batches) >= 2, batch_size=10
    )

    assert batches == [10, 10]
    assert result["input"] == 20
    assert result["stopped"] == 1


def test_a_batch_cut_short_by_the_stop_does_not_start_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    class Service:
        def normalize_pending(self, limit: int, *, should_stop=None) -> SimpleNamespace:
            calls.append(limit)
            return SimpleNamespace(processed=3, succeeded=3, review_required=0, failed=0)

    _patch_unit(monkeypatch, Service())

    result = worker.normalize_opportunities(object(), stop_requested=lambda: False, batch_size=10)

    assert calls == [10]  # fewer than a full batch means the backlog is empty
    assert result["input"] == 3


requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


@requires_database
def test_225_collected_items_are_all_normalized_in_one_stage_call() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            items = [
                _item(
                    fixture.source_type,
                    external_id=f"b1-{index:03d}",
                    title=f"Backend Engineer {index}",
                    description="Python and SQL.",
                )
                for index in range(225)
            ]
            collector = _StaticCollector(fixture.source_type, [items])
            asyncio.run(
                fixture.service(collector).execute(
                    fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
                )
            )
            raw_ids = [raw.id for raw in fixture.raw_items()]
            assert len(raw_ids) == 225

            result = worker.normalize_opportunities(engine, stop_requested=lambda: False)

            assert result["input"] >= 225  # the shared test database may hold other backlog
            session.expire_all()
            done = session.scalar(
                select(func.count(NormalizationResultModel.id)).where(
                    NormalizationResultModel.raw_item_id.in_(raw_ids),
                    NormalizationResultModel.normalizer_version == NORMALIZER_VERSION,
                )
            )
            assert done == 225
        finally:
            fixture.cleanup()
