from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from scripts import measure_host_resources


class _Completed:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class _Connection:
    """The psycopg 3 connection surface only: no `set_session`, no other attributes."""

    __slots__ = (
        "read_only",
        "autocommit",
        "statements",
        "closed",
        "cursor_closed",
        "rollback_called",
    )

    def __init__(self) -> None:
        self.read_only = False
        self.autocommit = False
        self.statements: list[str] = []
        self.closed = False
        self.cursor_closed = False
        self.rollback_called = False

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def rollback(self) -> None:
        self.rollback_called = True

    def close(self) -> None:
        self.closed = True


class _Cursor:
    __slots__ = ("connection",)

    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def execute(self, statement: str) -> None:
        self.connection.statements.append(statement)

    def fetchall(self) -> list[tuple[str | None, int]]:
        return [("active", 2), ("idle", 1)]

    def close(self) -> None:
        self.connection.cursor_closed = True


def test_measurement_emits_only_aggregate_metrics_and_uses_stats_only() -> None:
    commands: list[list[str]] = []
    connection = _Connection()
    connection_calls: list[tuple[str, dict[str, Any]]] = []

    def runner(command: list[str], **_: Any) -> _Completed:
        commands.append(command)
        if command[:2] == ["docker", "stats"]:
            return _Completed(
                '{"Name":"api","CPUPerc":"1.2%","MemUsage":"10MiB / 1GiB",'
                '"MemPerc":"1.0%","Secret":"do-not-copy"}\n'
            )
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return _Completed("abc123\n")
        return _Completed("", returncode=1)

    def connect(dsn: str, **kwargs: Any) -> _Connection:
        connection_calls.append((dsn, kwargs))
        return connection

    record = measure_host_resources.collect_measurement(
        phase="peak",
        database_url="postgresql://user:password@host/db",
        runner=runner,
        connect=connect,
    )

    assert record["phase"] == "peak"
    assert record["git_commit"] == "abc123"
    assert record["docker"] == [
        {"name": "api", "cpu_percent": "1.2%", "memory": "10MiB / 1GiB", "memory_percent": "1.0%"}
    ]
    assert connection.read_only is True
    assert connection.autocommit is False
    assert connection_calls == [
        (
            "postgresql://user:password@host/db",
            {
                "connect_timeout": 3,
                "options": "-c statement_timeout=3000 -c default_transaction_read_only=on",
            },
        )
    ]
    assert connection.closed is True
    assert connection.cursor_closed is True
    assert connection.rollback_called is True
    assert all(
        statement.lstrip().upper().startswith("SELECT")
        for statement in connection.statements
    )
    assert ["docker", "stats", "--no-stream", "--format", "{{json .}}"] in commands
    assert not any(command[0:2] == ["docker", "inspect"] for command in commands)
    assert not any(command[0:2] == ["docker", "exec"] for command in commands)
    serialized = json.dumps(record)
    assert "password" not in serialized
    assert "Secret" not in serialized


def test_measurement_does_not_copy_environment_or_database_url(monkeypatch: Any) -> None:
    monkeypatch.setenv("PRIVATE_TEST_SECRET", "secret-value")
    record = measure_host_resources.collect_measurement(
        phase="idle",
        runner=lambda *_args, **_kwargs: _Completed(returncode=1),
        connect=None,
    )

    serialized = json.dumps(record)
    assert "PRIVATE_TEST_SECRET" not in serialized
    assert "secret-value" not in serialized
    assert "DATABASE_URL" not in serialized


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1"
    or os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1",
    reason="database integration is enabled only in the isolated PostgreSQL database",
)
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").split("?")[0].rstrip("/").endswith("_test"),
    reason="database integration requires a database name ending in _test",
)
@pytest.mark.parametrize("scheme", ["postgresql+psycopg", "postgresql"])
def test_postgres_measurement_reads_aggregates_and_closes_connection(scheme: str) -> None:
    parsed = urlsplit(os.environ["DATABASE_URL"])
    database_url = urlunsplit(parsed._replace(scheme=scheme))
    connections: list[_TrackedConnection] = []

    def connect(dsn: str, **kwargs: Any) -> _TrackedConnection:
        connection = _TrackedConnection(psycopg.connect(dsn, **kwargs))
        connections.append(connection)
        return connection

    rows = measure_host_resources._postgres_connections(database_url, connect)

    assert len(connections) == 1
    assert connections[0].closed is True
    assert connections[0].read_only_value is True
    assert connections[0].autocommit_value is None
    assert connections[0].connection.autocommit is False
    assert rows
    assert all(set(row) == {"state", "count"} for row in rows)
    assert all(isinstance(row["count"], int) and row["count"] >= 0 for row in rows)
    assert sum(row["count"] for row in rows) >= 1


class _TrackedConnection:
    def __init__(self, connection: psycopg.Connection[Any]) -> None:
        self.connection = connection
        self.closed = False
        self.read_only_value: bool | None = None
        self.autocommit_value: bool | None = None

    @property
    def read_only(self) -> bool:
        return self.connection.read_only is True

    @read_only.setter
    def read_only(self, value: bool) -> None:
        self.read_only_value = value
        self.connection.read_only = value

    @property
    def autocommit(self) -> bool:
        return self.connection.autocommit

    @autocommit.setter
    def autocommit(self, value: bool) -> None:
        self.autocommit_value = value
        self.connection.autocommit = value

    def cursor(self) -> Any:
        return self.connection.cursor()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()
        self.closed = True
