from __future__ import annotations

import json
from typing import Any

from scripts import measure_host_resources


class _Completed:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class _Connection:
    def __init__(self) -> None:
        self.readonly = False
        self.statements: list[str] = []
        self.closed = False

    def set_session(self, *, readonly: bool, autocommit: bool) -> None:
        self.readonly = readonly and not autocommit

    def cursor(self) -> _Connection:
        return self

    def execute(self, statement: str) -> None:
        self.statements.append(statement)

    def fetchall(self) -> list[tuple[str | None, int]]:
        return [("active", 2), ("idle", 1)]

    def close(self) -> None:
        self.closed = True

    def rollback(self) -> None:
        return None


def test_measurement_emits_only_aggregate_metrics_and_uses_stats_only() -> None:
    commands: list[list[str]] = []
    connection = _Connection()

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

    record = measure_host_resources.collect_measurement(
        phase="peak",
        database_url="postgresql://user:password@host/db",
        runner=runner,
        connect=lambda *_args, **_kwargs: connection,
    )

    assert record["phase"] == "peak"
    assert record["git_commit"] == "abc123"
    assert record["docker"] == [
        {"name": "api", "cpu_percent": "1.2%", "memory": "10MiB / 1GiB", "memory_percent": "1.0%"}
    ]
    assert connection.readonly is True
    assert connection.closed is True
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
