"""Card F50-10: `20261005_0063` backfills the pointers set-based and reverses."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.backup import with_database
from opportunity_radar.platform.database import create_database_engine
from scripts.restore_check import create_database, drop_database
from tests.backend.dashboard.test_queries import (
    _assessment,
    _company,
    _opportunity,
    _profile_version,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = REPO_ROOT / "migrations" / "versions" / "20261005_0063_current_assessment.py"
BEFORE = "20261005_0062"

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


def _table_exists(connection: Any) -> bool:
    return bool(connection.scalar(text("SELECT to_regclass('matching.current_assessment')")))


def _pointers(connection: Any) -> set[tuple[Any, Any, Any]]:
    return {
        tuple(row)
        for row in connection.execute(
            text(
                "SELECT opportunity_id, profile_version_id, assessment_id "
                "FROM matching.current_assessment"
            )
        )
    }


@pytest.fixture
def scratch_database() -> Any:
    url = os.environ["DATABASE_URL"]
    name = f"f5010_pointer_{uuid4().hex[:12]}"
    create_database(url, name)
    try:
        yield with_database(url, name)
    finally:
        drop_database(url, name)


def test_backfill_picks_the_latest_per_posting_and_profile_and_round_trips(
    scratch_database: str,
) -> None:
    spec = importlib.util.spec_from_file_location("migration_0063", MIGRATION)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    _alembic(scratch_database, "upgrade", "head")
    engine = create_database_engine(scratch_database)
    now = datetime.now(UTC)
    try:
        with Session(engine) as session:
            first, second = _profile_version(session), _profile_version(session)
            company = _company(session, "normal")
            expected = set()
            for title in ("a", "b"):
                posting = _opportunity(session, company, title=title, published_at=now)
                for profile in (first, second):
                    older = _assessment(
                        session, posting, profile.id,
                        verdict="WATCHLIST", score="40.0000", assessed_at=now - timedelta(hours=2),
                    )
                    newest = _assessment(
                        session, posting, profile.id,
                        verdict="RECOMMENDED", score="70.0000", assessed_at=now,
                    )
                    assert older.id != newest.id
                    expected.add((posting.id, profile.id, newest.id))
            session.commit()

        with engine.begin() as connection:
            connection.execute(text("DELETE FROM matching.current_assessment"))
            connection.execute(text(migration.BACKFILL_SQL))
            assert _pointers(connection) == expected

        _alembic(scratch_database, "downgrade", BEFORE)
        with engine.connect() as connection:
            assert not _table_exists(connection)

        _alembic(scratch_database, "upgrade", "head")
        with engine.connect() as connection:
            assert _table_exists(connection)
            assert _pointers(connection) == expected
    finally:
        engine.dispose()
