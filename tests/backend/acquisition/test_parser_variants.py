"""F20-39 parser-envelope uniqueness and rollback guards."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from opportunity_radar.acquisition.domain import CollectedItem, content_hashes
from opportunity_radar.acquisition.service import canonical_payload_hash, collected_item_v1


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
