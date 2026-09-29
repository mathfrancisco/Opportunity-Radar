"""F20-39 parser-envelope uniqueness and rollback guards."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
    content_hashes,
)
from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel, SourceRunModel
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.service import (
    AcquisitionService,
    canonical_payload_hash,
    collected_item_v1,
)
from opportunity_radar.platform.database import create_database_engine


def _migration_module():
    path = (
        Path(__file__).parents[3]
        / "migrations"
        / "versions"
        / "20260926_0042_raw_item_parser_variants.py"
    )
    spec = importlib.util.spec_from_file_location("raw_item_parser_variants_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _boundary(*, parser_version: str | None, description: str = "Build APIs.") -> dict[str, object]:
    item = CollectedItem(
        source_type="example",
        external_id="job-1",
        title="Backend Engineer",
        description=description,
        raw_payload={"id": "job-1", "body": "unchanged bytes"},
        metadata={} if parser_version is None else {"parser_version": parser_version},
    )
    return collected_item_v1(item)


def test_parser_version_is_canonical_even_when_missing_from_metadata() -> None:
    missing = _boundary(parser_version=None)
    present = _boundary(parser_version="example-v2")

    assert missing["parser_version"] is None
    assert missing["metadata"] == {}
    assert content_hashes(missing, raw_hash="a" * 64).semantic_hash != content_hashes(
        present, raw_hash="a" * 64
    ).semantic_hash


def test_same_bytes_different_interpretation_has_distinct_semantic_envelopes() -> None:
    raw_payload = {"id": "job-1", "body": "unchanged bytes"}
    parser_v1 = _boundary(parser_version="example-v1")
    parser_v2 = _boundary(parser_version="example-v2")
    corrected = _boundary(parser_version="example-v2", description="Build APIs with Python.")

    raw_hash = canonical_payload_hash(raw_payload)
    hashes = [
        content_hashes(boundary, raw_hash=raw_hash)
        for boundary in (parser_v1, parser_v2, corrected)
    ]

    assert len({value.raw_hash for value in hashes}) == 1
    assert len({value.semantic_hash for value in hashes}) == 3


class _ScalarResult:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class _Connection:
    def __init__(self, collisions: int) -> None:
        self.collisions = collisions
        self.executed: list[object] = []

    def execute(self, statement: object) -> _ScalarResult:
        self.executed.append(statement)
        return _ScalarResult(self.collisions)


class _Operations:
    def __init__(self, collisions: int) -> None:
        self.connection = _Connection(collisions)
        self.actions: list[str] = []

    def get_bind(self) -> _Connection:
        return self.connection

    def drop_constraint(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.actions.append("drop")

    def create_unique_constraint(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.actions.append("create")


def test_downgrade_refuses_variant_collision_without_executing_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration_module()
    operations = _Operations(collisions=1)
    monkeypatch.setattr(migration, "op", operations)

    with pytest.raises(RuntimeError, match="refusing raw_item parser-variant downgrade"):
        migration.downgrade()

    assert operations.actions == []
    assert len(operations.connection.executed) == 1


def test_downgrade_nonconflicting_variants_restores_old_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _migration_module()
    operations = _Operations(collisions=0)
    monkeypatch.setattr(migration, "op", operations)

    migration.downgrade()

    assert operations.actions == ["drop", "create"]


class _ParserVersionCollector:
    """Yields the same raw payload under successive parser versions, then repeats the
    last one — the real shape a parser upgrade takes: identical bytes, a new boundary
    interpretation, then a plain revisit with no further change."""

    capabilities = CollectorCapabilities()

    def __init__(self, source_type: str, parser_versions: list[str]) -> None:
        self.source_type = source_type
        self._parser_versions = list(parser_versions)
        self.calls = 0

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        version = self._parser_versions[min(self.calls, len(self._parser_versions) - 1)]
        self.calls += 1
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            title="Backend Engineer",
            raw_payload={"id": "job-1", "body": "unchanged bytes"},
            metadata={"parser_version": version},
        )


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_a_real_parser_upgrade_appends_a_variant_instead_of_colliding() -> None:
    """The F20-39 card's pending acceptance item for migration 20260926_0042: proven here
    against a real Postgres instance (not the mocked migration module above), exercising
    the actual `AcquisitionService` write path a parser upgrade takes in production.

    Same raw bytes, three real runs: parser v1, parser v2 (a real upgrade — same bytes,
    new boundary), then v2 again (a plain revisit, no further change). The widened unique
    constraint must accept the v1/v2 split as two append-only evidence rows and still
    dedupe the v2 revisit into presence-only, exactly as the pre-0042 constraint deduped
    same-parser revisits.
    """
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source_type = f"parser_variant_probe_{uuid4().hex[:8]}"
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type=source_type,
            name=f"parser variant probe {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(source)
        session.commit()
        try:
            collector = _ParserVersionCollector(
                source_type, ["example-v1", "example-v2", "example-v2"]
            )
            service = AcquisitionService(
                session,
                registry=CollectorRegistry((collector,)),  # type: ignore[arg-type]
                repository=AcquisitionRepository(session),
            )

            first_run = asyncio.run(
                service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            assert first_run.items_persisted == 1

            second_run = asyncio.run(
                service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            # A genuine parser upgrade over identical bytes: a second, distinct envelope
            # is appended, not collided with the first (this is exactly what the widened
            # constraint in migration 20260926_0042 exists to permit).
            assert second_run.items_persisted == 1

            third_run = asyncio.run(
                service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
            # A plain revisit under the same (now current) parser version: still deduped,
            # not a third variant.
            assert third_run.items_persisted == 0
            assert third_run.items_skipped == 1

            raw_items = list(
                session.scalars(
                    select(RawItemModel)
                    .where(RawItemModel.source_definition_id == source.id)
                    .order_by(RawItemModel.fetched_at)
                )
            )
            assert len(raw_items) == 2
            assert {item.parser_version for item in raw_items} == {"example-v1", "example-v2"}
            assert len({item.payload_hash for item in raw_items}) == 1
            assert len({item.semantic_hash for item in raw_items}) == 2
        finally:
            session.rollback()
            run_ids = list(
                session.scalars(
                    select(SourceRunModel.id).where(
                        SourceRunModel.source_definition_id == source.id
                    )
                )
            )
            raw_item_ids = list(
                session.scalars(
                    select(RawItemModel.id).where(RawItemModel.source_definition_id == source.id)
                )
            )
            from sqlalchemy import delete

            from opportunity_radar.acquisition.models import SourceCheckpointModel
            from opportunity_radar.opportunities.models import SourceOccurrenceObservationModel

            session.execute(
                delete(SourceCheckpointModel).where(
                    SourceCheckpointModel.source_definition_id == source.id
                )
            )
            session.execute(
                delete(SourceOccurrenceObservationModel).where(
                    SourceOccurrenceObservationModel.raw_item_id.in_(raw_item_ids)
                )
            )
            session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_item_ids)))
            session.execute(delete(SourceRunModel).where(SourceRunModel.id.in_(run_ids)))
            session.execute(
                delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id)
            )
            session.commit()
