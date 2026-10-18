"""R55-E6: migration 20261016_0071 sets lz4 on the large columns and reverts cleanly."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from opportunity_radar.platform.backup import with_database
from opportunity_radar.platform.database import create_database_engine
from scripts.restore_check import create_database, drop_database

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION = "20261016_0071"
PREVIOUS = "20261016_0070"
COLUMNS = (
    ("acquisition", "raw_item_payload", "payload"),
    ("opportunities", "opportunity", "description"),
)


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        ["alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url, "OWNER_SUB_BACKFILL": "test-toast-migration"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _compression(url: str) -> dict[str, str]:
    engine = create_database_engine(url)
    try:
        with engine.connect() as connection:
            return {
                column: connection.execute(
                    text(
                        "SELECT attcompression FROM pg_attribute "
                        "WHERE attrelid = to_regclass(:rel) AND attname = :col"
                    ),
                    {"rel": f"{schema}.{table}", "col": column},
                ).scalar_one()
                for schema, table, column in COLUMNS
            }
    finally:
        engine.dispose()


@pytest.fixture
def scratch() -> Iterator[str]:
    url = os.environ["DATABASE_URL"]
    name = f"r55e6_mig_{uuid4().hex[:12]}_test"
    create_database(url, name)
    try:
        yield with_database(url, name)
    finally:
        drop_database(url, name)


def test_upgrade_sets_lz4_and_downgrade_restores_the_default(scratch: str) -> None:
    _alembic(scratch, "upgrade", PREVIOUS)
    assert set(_compression(scratch).values()) == {""}  # server default

    _alembic(scratch, "upgrade", REVISION)
    assert _compression(scratch) == {"payload": "l", "description": "l"}

    _alembic(scratch, "downgrade", PREVIOUS)
    assert set(_compression(scratch).values()) == {""}

    _alembic(scratch, "upgrade", REVISION)
    assert _compression(scratch) == {"payload": "l", "description": "l"}


def test_new_values_are_stored_with_lz4(scratch: str) -> None:
    _alembic(scratch, "upgrade", REVISION)
    engine = create_database_engine(scratch)
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(
                text(
                    "INSERT INTO opportunities.opportunity (id, fingerprint, "
                    "fingerprint_version, canonical_title, normalized_title, description) "
                    "VALUES (gen_random_uuid(), 'f', 'v1', 't', 't', repeat('lorem ipsum ', 5000))"
                )
            )
            method = connection.execute(
                text(
                    "SELECT pg_column_compression(description) "
                    "FROM opportunities.opportunity LIMIT 1"
                )
            ).scalar_one()
        assert method == "lz4"
    finally:
        engine.dispose()
