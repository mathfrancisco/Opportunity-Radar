"""F48-08: migration 20260929_0056 splits aggregate host budgets per tenant, both ways."""

from __future__ import annotations

import json
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
PREVIOUS = "20260929_0055"
REVISION = "20260929_0056"


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        ["alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def scratch() -> Iterator[str]:
    url = os.environ["DATABASE_URL"]
    name = f"f4808_mig_{uuid4().hex[:12]}"
    create_database(url, name)
    try:
        yield with_database(url, name)
    finally:
        drop_database(url, name)


def _add_source(connection, source_type: str, name: str, configuration: dict) -> None:
    connection.execute(
        text(
            "INSERT INTO acquisition.source_definition "
            "(id, source_type, name, enabled, priority, rate_limit_policy, configuration, "
            "evidence_status, terms_reviewed, collector_local_tested, version) "
            "VALUES (gen_random_uuid(), :t, :n, false, 100, '{}'::jsonb, "
            "CAST(:c AS jsonb), 'unverified', false, false, 1)"
        ),
        {"t": source_type, "n": name, "c": json.dumps(configuration)},
    )


def _budget_rows(connection) -> dict[str, tuple[int, int]]:
    return {
        row[0]: (row[1], row[2])
        for row in connection.execute(
            text("SELECT host, requests_used, requests_ceiling FROM acquisition.host_budget_state")
        )
    }


def test_aggregate_rows_become_per_tenant_rows_and_back(scratch: str) -> None:
    _alembic(scratch, "upgrade", PREVIOUS)
    engine = create_database_engine(scratch)
    try:
        with engine.begin() as connection:
            for tenant in ("aig", "adobe"):
                _add_source(
                    connection,
                    "workday",
                    tenant,
                    {"tenant_identifier": f"{tenant}/site", "api_region": "wd5"},
                )
            _add_source(connection, "factorial", "f1", {"company_identifier": "acme"})
            _add_source(
                connection, "jobposting", "j1", {"page_url": "https://Careers.Acme.com/jobs"}
            )
            for host, used in (
                ("workday", 518),
                ("factorial", 146),
                ("jobposting", 3),
                ("lever", 40),
            ):
                connection.execute(
                    text(
                        "INSERT INTO acquisition.host_budget_state "
                        "(host, window_start, requests_used, requests_ceiling, "
                        "exploration_reserve_ratio) VALUES (:h, now(), :u, 200, 0.10)"
                    ),
                    {"h": host, "u": used},
                )

        _alembic(scratch, "upgrade", REVISION)
        with engine.connect() as connection:
            rows = _budget_rows(connection)
        assert rows == {
            "workday:aig/site:wd5": (0, 500),
            "workday:adobe/site:wd5": (0, 500),
            "factorial:acme": (0, 200),
            "jobposting:careers.acme.com": (0, 200),
            "lever": (40, 200),
        }

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE acquisition.host_budget_state SET requests_used = 7 "
                    "WHERE host LIKE 'workday:%'"
                )
            )
        _alembic(scratch, "downgrade", PREVIOUS)
        with engine.connect() as connection:
            rows = _budget_rows(connection)
        assert rows == {
            "workday": (14, 200),
            "factorial": (0, 200),
            "jobposting": (0, 200),
            "lever": (40, 200),
        }

        _alembic(scratch, "upgrade", REVISION)
        with engine.connect() as connection:
            assert "workday:aig/site:wd5" in _budget_rows(connection)
    finally:
        engine.dispose()
