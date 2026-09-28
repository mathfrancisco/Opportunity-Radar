"""No real network or database in the unit tests below: `_collect_one` is monkeypatched
to a fake so `_collect`'s concurrency/ordering/host-serialization can be asserted without
either. The DB-integration tests at the bottom exercise the real `AcquisitionService`
against a fake in-process collector, gated the same way the rest of this suite gates a
real database (`RUN_DATABASE_INTEGRATION=1`)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
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
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from scripts import collect


def _source(source_type: str, name: str, **config) -> SourceDefinitionModel:
    return SourceDefinitionModel(
        id=uuid4(), source_type=source_type, name=name, enabled=True, configuration=config
    )


def test_collect_preserves_source_order_regardless_of_completion_order(monkeypatch) -> None:
    sources = [
        _source("ashby", "A", board_identifier="a"),
        _source("lever", "B", site_identifier="b"),
        _source("greenhouse", "C", board_token="c"),
    ]
    delays = {"A": 0.03, "B": 0.02, "C": 0.01}

    async def fake_collect_one(engine, source, **kwargs) -> dict[str, object]:
        await asyncio.sleep(delays[source.name])
        return {"source_id": str(source.id), "source_name": source.name, "status": "COMPLETED"}

    monkeypatch.setattr(collect, "_collect_one", fake_collect_one)

    report = asyncio.run(
        collect._collect(
            object(),
            sources,
            mode=CollectionMode.DISCOVERY,
            keywords=(),
            max_items=None,
            correlation_id="test",
            settings=object(),
            concurrency=8,
        )
    )

    assert [item["source_name"] for item in report] == ["A", "B", "C"]


def test_collect_serializes_two_sources_on_the_same_provider_host(monkeypatch) -> None:
    sources = [
        _source("ashby", "A1", board_identifier="a1"),
        _source("ashby", "A2", board_identifier="a2"),
    ]
    active = 0
    max_active = 0

    async def fake_collect_one(engine, source, **kwargs) -> dict[str, object]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return {"source_id": str(source.id), "source_name": source.name, "status": "COMPLETED"}

    monkeypatch.setattr(collect, "_collect_one", fake_collect_one)

    asyncio.run(
        collect._collect(
            object(),
            sources,
            mode=CollectionMode.DISCOVERY,
            keywords=(),
            max_items=None,
            correlation_id="test",
            settings=object(),
            concurrency=8,
        )
    )

    assert max_active == 1


def test_collect_default_concurrency_is_one() -> None:
    assert collect.DEFAULT_COLLECT_CONCURRENCY == 1


_requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


class _StubCollector:
    def __init__(self, source_type: str) -> None:
        self.source_type = source_type
        self.capabilities = CollectorCapabilities(keyword_search=False)

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        yield CollectedItem(
            source_type=self.source_type,
            external_id=uuid4().hex,
            title="Cobol Mainframe Analyst",
            raw_payload={"title": "Cobol Mainframe Analyst"},
        )


class _MisbehavingCollector(_StubCollector):
    """Raises a plain `RuntimeError` (never `AcquisitionError`) just from being asked
    what it supports — the collector-runtime failures `AcquisitionService.execute`
    itself already turns into a `FAILED` run without raising; this is the other kind of
    failure, before `execute` is even called, that used to crash the whole batch."""

    @property
    def capabilities(self) -> CollectorCapabilities:
        raise RuntimeError("boom, not an AcquisitionError")

    @capabilities.setter
    def capabilities(self, value: CollectorCapabilities) -> None:
        pass


def _seed_source(session: Session, *, source_type: str) -> UUID:
    source = SourceDefinitionModel(
        source_type=source_type,
        name=f"collect-test:{source_type}-{uuid4().hex[:8]}",
        enabled=True,
        configuration={},
        rate_limit_policy={},
        evidence_status="confirmed",
        reviewed_at=datetime.now(UTC),
        terms_reviewed=True,
        collector_local_tested=True,
    )
    session.add(source)
    session.commit()
    return source.id


def _cleanup(session: Session, source_ids: list[UUID]) -> None:
    for model in (RawItemModel, SourceRunModel, SourceCheckpointModel):
        session.execute(delete(model).where(model.source_definition_id.in_(source_ids)))
    session.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id.in_(source_ids)))
    session.commit()


@pytest.mark.integration
@_requires_database
def test_collect_one_catches_a_bare_exception_and_reports_it_as_error(monkeypatch) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    source_type = f"collect_test_raising_{uuid4().hex[:8]}"
    with Session(engine) as session:
        source_id = _seed_source(session, source_type=source_type)
        source = session.get(SourceDefinitionModel, source_id)
        assert source is not None

        monkeypatch.setattr(
            collect,
            "_registry",
            lambda settings: CollectorRegistry([_MisbehavingCollector(source_type)]),
        )
        try:
            result = asyncio.run(
                collect._collect_one(
                    engine,
                    source,
                    mode=CollectionMode.DISCOVERY,
                    keywords=(),
                    max_items=None,
                    correlation_id="test",
                    settings=Settings(),  # type: ignore[call-arg]
                )
            )
            assert result["status"] == "ERROR"
            assert result["error_code"] == "UNKNOWN_ERROR"
            assert "boom" in result["error_summary"]
        finally:
            _cleanup(session, [source_id])


@pytest.mark.integration
@_requires_database
def test_collect_runs_two_sources_concurrently_with_independent_sessions(monkeypatch) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    type_a = f"collect_test_ok_a_{uuid4().hex[:8]}"
    type_b = f"collect_test_ok_b_{uuid4().hex[:8]}"
    with Session(engine) as session:
        id_a = _seed_source(session, source_type=type_a)
        id_b = _seed_source(session, source_type=type_b)
        source_a = session.get(SourceDefinitionModel, id_a)
        source_b = session.get(SourceDefinitionModel, id_b)
        assert source_a is not None and source_b is not None

        monkeypatch.setattr(
            collect,
            "_registry",
            lambda settings: CollectorRegistry(
                [_StubCollector(type_a), _StubCollector(type_b)]
            ),
        )
        try:
            report = asyncio.run(
                collect._collect(
                    engine,
                    [source_a, source_b],
                    mode=CollectionMode.DISCOVERY,
                    keywords=(),
                    max_items=None,
                    correlation_id="test",
                    settings=Settings(),  # type: ignore[call-arg]
                    concurrency=2,
                )
            )
            statuses = {item["source_name"]: item["status"] for item in report}
            assert statuses[source_a.name] == "SUCCEEDED"
            assert statuses[source_b.name] == "SUCCEEDED"
        finally:
            _cleanup(session, [id_a, id_b])
