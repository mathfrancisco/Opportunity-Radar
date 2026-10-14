"""F48-16: `20260929_0057` backfills `recency_basis` on populated rows and reverses."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from opportunity_radar.platform.backup import with_database
from opportunity_radar.platform.database import create_database_engine
from scripts.restore_check import create_database, drop_database

REPO_ROOT = Path(__file__).resolve().parents[2]
BEFORE = "20260929_0055"
REVISION = "20260929_0057"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        ["alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _columns(url: str) -> set[str]:
    engine = create_database_engine(url)
    try:
        with engine.connect() as connection:
            return {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'opportunities' AND table_name = 'opportunity'"
                    )
                )
            }
    finally:
        engine.dispose()


@pytest.fixture
def scratch_database() -> Any:
    url = os.environ["DATABASE_URL"]
    name = f"f4816_recency_{uuid4().hex[:12]}_test"
    create_database(url, name)
    try:
        yield with_database(url, name)
    finally:
        drop_database(url, name)


def test_recency_basis_migration_backfills_and_round_trips(scratch_database: str) -> None:
    # Target the revisions by id, not `head`: another card's revision may sit beside this one.
    _alembic(scratch_database, "upgrade", BEFORE)
    assert "recency_basis" not in _columns(scratch_database)

    engine = create_database_engine(scratch_database)
    try:
        with engine.begin() as connection:
            for label, published, updated in (
                ("pub", "now()", "now()"),
                ("upd", "NULL", "now()"),
                ("seen", "NULL", "NULL"),
            ):
                connection.execute(
                    text(
                        "INSERT INTO opportunities.opportunity (id, fingerprint, "
                        "fingerprint_version, canonical_title, normalized_title, "
                        "work_mode, seniority, contract_type, lifecycle_status, version, "
                        "published_at, source_updated_at) VALUES (gen_random_uuid(), "
                        f"'{label}{uuid4().hex}', 'v1', '{label}', '{label}', 'UNKNOWN', "
                        f"'UNKNOWN', 'UNKNOWN', 'ACTIVE', 1, {published}, {updated})"
                    )
                )
    finally:
        engine.dispose()

    _alembic(scratch_database, "upgrade", REVISION)
    engine = create_database_engine(scratch_database)
    try:
        with engine.connect() as connection:
            rows = dict(
                connection.execute(
                    text("SELECT canonical_title, recency_basis FROM opportunities.opportunity")
                ).all()
            )
        assert rows == {"pub": "published", "upd": "updated", "seen": "first_seen"}
        with engine.connect() as connection, pytest.raises(Exception):  # noqa: B017
            connection.execute(text("UPDATE opportunities.opportunity SET recency_basis = 'x'"))
    finally:
        engine.dispose()

    _alembic(scratch_database, "downgrade", BEFORE)
    assert "recency_basis" not in _columns(scratch_database)
    _alembic(scratch_database, "upgrade", REVISION)
    assert "recency_basis" in _columns(scratch_database)
