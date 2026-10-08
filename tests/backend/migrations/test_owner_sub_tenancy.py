"""Controlled, isolated migration coverage for immutable personal-data ownership."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from opportunity_radar.platform.backup import with_database
from opportunity_radar.platform.database import create_database_engine
from scripts.restore_check import create_database, drop_database

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1"
    or os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1",
    reason="owner_sub migration tests require the isolated database suite",
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PREVIOUS = "20261006_0068"
REVISION = "20261008_0069"
BACKFILL_OWNER = "synthetic-owner-a"
PERSONAL_TABLES = (
    ("profile", "career_profile"),
    ("crm", "application_process"),
    ("dashboard", "saved_search"),
    ("opportunities", "relevance_mark"),
    ("matching", "match_assessment"),
)


def _assert_isolated_test_url(url: str) -> None:
    database = url.rsplit("/", maxsplit=1)[-1].split("?", maxsplit=1)[0]
    if not database.endswith("_test"):
        raise RuntimeError("DATABASE_URL must select a database ending in _test")


def _alembic(
    url: str, *args: str, owner_sub: str | None = BACKFILL_OWNER
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "DATABASE_URL": url}
    if owner_sub is None:
        environment.pop("OWNER_SUB_BACKFILL", None)
    else:
        environment["OWNER_SUB_BACKFILL"] = owner_sub
    return subprocess.run(
        ["alembic", *args],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def scratch() -> Iterator[str]:
    url = os.environ["DATABASE_URL"]
    _assert_isolated_test_url(url)
    name = f"f53_owner_{uuid4().hex[:12]}_test"
    create_database(url, name)
    try:
        yield with_database(url, name)
    finally:
        drop_database(url, name)


def _column_is_required(connection, schema: str, table: str) -> bool:
    return bool(
        connection.execute(
            text(
                "SELECT is_nullable = 'NO' FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = :table "
                "AND column_name = 'owner_sub'"
            ),
            {"schema": schema, "table": table},
        ).scalar_one()
    )


def _owner_indexes(connection, schema: str, table: str) -> set[str]:
    return set(
        connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = :table "
                "AND indexdef LIKE '%(owner_sub)%'"
            ),
            {"schema": schema, "table": table},
        ).scalars()
    )


def test_upgrade_backfills_audits_and_preserves_owner_data_on_downgrade(scratch: str) -> None:
    assert _alembic(scratch, "upgrade", PREVIOUS).returncode == 0
    engine = create_database_engine(scratch)
    career_id = uuid4()
    saved_search_id = uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO profile.career_profile (id, singleton_key, version) "
                    "VALUES (:id, true, 0)"
                ),
                {"id": career_id},
            )
            connection.execute(
                text(
                    "INSERT INTO dashboard.saved_search (id, name, filters) "
                    "VALUES (:id, 'synthetic search', '{}'::jsonb)"
                ),
                {"id": saved_search_id},
            )

        result = _alembic(scratch, "upgrade", REVISION)
        assert result.returncode == 0, result.stderr
        with engine.begin() as connection:
            for schema, table in PERSONAL_TABLES:
                assert _column_is_required(connection, schema, table)
                assert _owner_indexes(connection, schema, table)
                assert connection.execute(
                    text(f"SELECT count(*) FROM {schema}.{table} WHERE owner_sub IS NULL")
                ).scalar_one() == 0

            assert connection.execute(
                text("SELECT owner_sub FROM profile.career_profile WHERE id = :id"),
                {"id": career_id},
            ).scalar_one() == BACKFILL_OWNER
            assert connection.execute(
                text("SELECT owner_sub FROM dashboard.saved_search WHERE id = :id"),
                {"id": saved_search_id},
            ).scalar_one() == BACKFILL_OWNER
            connection.execute(
                text(
                    "INSERT INTO dashboard.saved_search (id, owner_sub, name, filters) "
                    "VALUES (:id, 'synthetic-owner-b', 'other tenant', '{}'::jsonb)"
                ),
                {"id": uuid4()},
            )
            assert connection.execute(
                text("SELECT count(*) FROM dashboard.saved_search WHERE owner_sub = :owner"),
                {"owner": BACKFILL_OWNER},
            ).scalar_one() == 1
            with pytest.raises(DBAPIError, match="owner_sub is immutable"):
                with connection.begin_nested():
                    connection.execute(
                        text(
                            "UPDATE dashboard.saved_search SET owner_sub = "
                            "'synthetic-owner-c' WHERE id = :id"
                        ),
                        {"id": saved_search_id},
                    )

        result = _alembic(scratch, "downgrade", PREVIOUS)
        assert result.returncode == 0, result.stderr
        with engine.connect() as connection:
            assert _column_is_required(connection, "dashboard", "saved_search")
            assert connection.execute(
                text("SELECT owner_sub FROM dashboard.saved_search WHERE id = :id"),
                {"id": saved_search_id},
            ).scalar_one() == BACKFILL_OWNER
    finally:
        engine.dispose()


def test_upgrade_refuses_to_backfill_without_an_explicit_subject(scratch: str) -> None:
    assert _alembic(scratch, "upgrade", PREVIOUS).returncode == 0
    result = _alembic(scratch, "upgrade", REVISION, owner_sub=None)
    assert result.returncode != 0
    assert "OWNER_SUB_BACKFILL is required" in result.stderr
    engine = create_database_engine(scratch)
    try:
        with engine.connect() as connection:
            for schema, table in PERSONAL_TABLES:
                assert connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema = :schema AND table_name = :table "
                        "AND column_name = 'owner_sub'"
                    ),
                    {"schema": schema, "table": table},
                ).scalar_one() == 0
    finally:
        engine.dispose()
