"""F48-07: migration 20260929_0055 upgrades, downgrades and upgrades again cleanly."""

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
REVISION = "20260929_0055"
PREVIOUS = "20260929_0054"


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        ["alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _shape(url: str) -> tuple[set[str], bool]:
    engine = create_database_engine(url)
    try:
        with engine.connect() as connection:
            columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'acquisition' AND table_name = 'source_run'"
                    )
                )
            }
            history = connection.execute(
                text("SELECT to_regclass('platform.worker_pass_history') IS NOT NULL")
            ).scalar_one()
        return columns, bool(history)
    finally:
        engine.dispose()


@pytest.fixture
def scratch() -> Iterator[str]:
    url = os.environ["DATABASE_URL"]
    name = f"f4807_mig_{uuid4().hex[:12]}"
    create_database(url, name)
    try:
        yield with_database(url, name)
    finally:
        drop_database(url, name)


def test_migration_round_trip(scratch: str) -> None:
    _alembic(scratch, "upgrade", "head")
    columns, history = _shape(scratch)
    assert {"bytes_received", "newest_item_age_seconds"} <= columns
    assert history

    _alembic(scratch, "downgrade", PREVIOUS)
    columns, history = _shape(scratch)
    assert not {"bytes_received", "newest_item_age_seconds"} & columns
    assert not history

    _alembic(scratch, "upgrade", "head")
    columns, history = _shape(scratch)
    assert {"bytes_received", "newest_item_age_seconds"} <= columns
    assert history
