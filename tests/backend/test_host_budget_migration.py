"""F48-08: migration 20260929_0056 splits aggregate host budgets per tenant, both ways."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
F51_PREVIOUS = "20261005_0065"
F51_REVISION = "20261005_0066"


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


def test_workday_host_budget_downgrade_depletes_each_site_conservatively(
    scratch: str,
) -> None:
    """Rollback cannot multiply a physical host's balance across its configured sites."""
    _alembic(scratch, "upgrade", F51_PREVIOUS)
    engine = create_database_engine(scratch)
    cooldown = "2099-01-01 00:00:00+00"
    try:
        with engine.begin() as connection:
            _add_source(
                connection, "workday", "site-a",
                {"tenant_identifier": "acme/site-a", "api_region": "wd5"},
            )
            _add_source(
                connection, "workday", "site-b",
                {"tenant_identifier": "acme/site-b", "api_region": "wd5"},
            )
            for host, used in (
                ("workday:acme/site-a:wd5", 3),
                ("workday:acme/site-b:wd5", 4),
                ("acme.wd5.myworkdayjobs.com", 2),
            ):
                connection.execute(
                    text(
                        "INSERT INTO acquisition.host_budget_state "
                        "(host, window_start, requests_used, requests_ceiling, cooldown_until, "
                        "exploration_reserve_ratio) "
                        "VALUES (:host, now() - interval '3 days', :used, 20, :cooldown, 0.1)"
                    ),
                    {"host": host, "used": used, "cooldown": cooldown},
                )
        _alembic(scratch, "upgrade", F51_REVISION)
        with engine.begin() as connection:
            # Simulate a window rollover at the physical host after migration.
            connection.execute(
                text(
                    "UPDATE acquisition.host_budget_state SET window_start = now() - "
                    "interval '3 days', requests_used = 9, requests_ceiling = 20, "
                    "cooldown_until = :cooldown "
                    "WHERE host = 'acme.wd5.myworkdayjobs.com'"
                ),
                {"cooldown": cooldown},
            )
            # A legacy key can be recreated by another older process before rollback.
            connection.execute(
                text(
                    "INSERT INTO acquisition.host_budget_state "
                    "(host, window_start, requests_used, requests_ceiling, cooldown_until, "
                    "exploration_reserve_ratio) VALUES "
                    "('workday:acme/site-a:wd5', now() - interval '1 day', 1, 10, "
                    ":collision_cooldown, 0.2)"
                ),
                {"collision_cooldown": "2099-06-01 00:00:00+00"},
            )
        _alembic(scratch, "downgrade", F51_PREVIOUS)
        with engine.connect() as connection:
            rows = {
                row.host: row
                for row in connection.execute(
                    text(
                        "SELECT host, window_start, requests_used, requests_ceiling, "
                        "cooldown_until FROM acquisition.host_budget_state "
                        "WHERE host LIKE 'workday:%'"
                    )
                )
            }
        assert set(rows) == {"workday:acme/site-a:wd5", "workday:acme/site-b:wd5"}
        for host, row in rows.items():
            assert row.requests_used >= row.requests_ceiling
            assert row.window_start >= datetime.now(UTC) - timedelta(minutes=1)
        assert rows["workday:acme/site-a:wd5"].requests_used >= 20
        assert rows["workday:acme/site-a:wd5"].cooldown_until.isoformat().startswith("2099-06-01")
        assert rows["workday:acme/site-b:wd5"].cooldown_until.isoformat().startswith("2099-01-01")
    finally:
        engine.dispose()
