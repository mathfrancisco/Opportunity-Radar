"""Security boundaries for F53-14's local backup and restore helpers."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from opportunity_radar.platform.backup import pgpassfile_for_url
from scripts import backup, restore_check


def test_pgpassfile_keeps_password_out_of_environment_and_cleans_up() -> None:
    with pgpassfile_for_url(
        "postgresql://user:p%40ss%3Aword@host:5432/source_test"
    ) as env:
        passfile = Path(env["PGPASSFILE"])
        assert "PGPASSWORD" not in env
        if os.name != "nt":
            assert stat.S_IMODE(passfile.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
        assert "host:5432:source_test:user:p@ss\\:word" in passfile.read_text(
            encoding="utf-8"
        )
    assert not passfile.exists()


@pytest.mark.parametrize(
    ("runner", "arguments"),
    [
        (backup.run_pg_dump, ("postgresql://user:secret@host/source_test", Path("x.dump"))),
        (
            restore_check.restore,
            (Path("x.dump"), "postgresql://user:secret@host/source_test", "scratch_test"),
        ),
    ],
)
def test_postgres_tools_do_not_receive_dsn_or_password_in_argv(
    monkeypatch: pytest.MonkeyPatch, runner: Any, arguments: tuple[Any, ...]
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.8")
    monkeypatch.setenv("PGSERVICE", "unsafe-service")
    monkeypatch.setenv("PGDATABASE", "unsafe_database")
    runner(*arguments)

    assert "secret" not in " ".join(captured["command"])
    assert "postgresql://" not in " ".join(captured["command"])
    assert "PGPASSWORD" not in captured["env"]
    assert captured["env"]["PGDATABASE"] in {"source_test", "scratch_test"}
    assert "PGHOSTADDR" not in captured["env"]
    assert "PGSERVICE" not in captured["env"]
    if runner is restore_check.restore:
        assert "--dbname=scratch_test" in captured["command"]


@pytest.mark.parametrize("base_url", ["postgresql://u:p@host/source", "postgresql://u:p@host/source_test"])
def test_restore_isolation_requires_both_explicit_flags(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    monkeypatch.delenv("RUN_DATABASE_INTEGRATION", raising=False)
    monkeypatch.delenv("DATABASE_INTEGRATION_ISOLATED", raising=False)
    with pytest.raises(SystemExit, match="restore"):
        restore_check.guard_isolation(base_url, "scratch_test")


def test_restore_isolation_rejects_non_test_base_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DATABASE_INTEGRATION", "1")
    monkeypatch.setenv("DATABASE_INTEGRATION_ISOLATED", "1")
    with pytest.raises(SystemExit, match="base database must end in _test"):
        restore_check.guard_isolation("postgresql://u:p@host/source", "scratch_test")


def test_restore_isolation_accepts_explicit_test_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_DATABASE_INTEGRATION", "1")
    monkeypatch.setenv("DATABASE_INTEGRATION_ISOLATED", "1")
    restore_check.guard_isolation("postgresql://u:p@host/source_test", "scratch_test")


def test_tool_failure_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, command, stderr="password=secret")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(SystemExit, match="redacted") as error:
        backup.run_pg_dump("postgresql://u:secret@host/source_test", Path("x.dump"))
    assert "secret" not in str(error.value)
