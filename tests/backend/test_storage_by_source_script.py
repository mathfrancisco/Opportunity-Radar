"""R55-B5: the storage report fails loudly instead of showing a misleading zero."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "storage_by_source.py"


def _load():
    spec = importlib.util.spec_from_file_location("storage_by_source", SCRIPT)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_missing_owner_exits_with_a_message(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:1/none")
    monkeypatch.delenv("WORKER_OWNER_SUB", raising=False)

    with pytest.raises(SystemExit) as stop:
        module.main([])

    assert "WORKER_OWNER_SUB" in str(stop.value)


def test_unreadable_profile_exits_with_a_message(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load()
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:1/none")
    monkeypatch.setenv("WORKER_OWNER_SUB", "someone")

    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(module, "owner_target_scope", broken)

    with pytest.raises(SystemExit) as stop:
        module.main([])

    assert "could not read the active profile" in str(stop.value)
    assert "secret detail" not in str(stop.value)
