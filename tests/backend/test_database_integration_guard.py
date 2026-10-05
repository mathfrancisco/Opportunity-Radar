"""Process-level guard for destructive database integration tests."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTEST_COMMAND = [sys.executable, "-m", "pytest", "--collect-only", "tests/backend/test_worker.py"]


def _collect_with(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        PYTEST_COMMAND,
        cwd=ROOT,
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        check=False,
    )


def test_database_integration_requires_explicit_isolation_marker() -> None:
    result = _collect_with(
        {
            "RUN_DATABASE_INTEGRATION": "1",
            "DATABASE_INTEGRATION_ISOLATED": "",
            "DATABASE_URL": "postgresql+psycopg://user:password@invalid:5432/opportunity_radar",
        }
    )

    assert result.returncode != 0
    assert "requires DATABASE_INTEGRATION_ISOLATED=1" in result.stderr


def test_database_integration_rejects_non_test_database_before_collection() -> None:
    result = _collect_with(
        {
            "RUN_DATABASE_INTEGRATION": "1",
            "DATABASE_INTEGRATION_ISOLATED": "1",
            "DATABASE_URL": "postgresql+psycopg://user:password@invalid:5432/opportunity_radar",
        }
    )

    assert result.returncode != 0
    assert "database ending in _test" in result.stderr


def test_database_integration_accepts_explicit_dedicated_database() -> None:
    result = _collect_with(
        {
            "RUN_DATABASE_INTEGRATION": "1",
            "DATABASE_INTEGRATION_ISOLATED": "1",
            "DATABASE_URL": "postgresql+psycopg://user:password@invalid:5432/opportunity_radar_test",
        }
    )

    assert result.returncode == 0, result.stderr
