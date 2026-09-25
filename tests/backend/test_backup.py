"""A dump that restores is not proven by an exit code alone (card F20-41, old F18-08).

The unit tests below exercise the gate logic — the strict manifest check, the checksum
check, the comparison that now also covers relationships and extensions — without a real
Postgres. The one round trip that needs an actual server, `pg_dump` and `pg_restore` is
gated behind `RUN_DATABASE_INTEGRATION`, same as the rest of the database integration
suite, and skips itself if either tool is not on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from opportunity_radar.platform.backup import FORMAT_VERSION, sha256_file
from scripts import backup, restore_check


def _write_dump(path: Path, content: bytes = b"not a real dump, just bytes to hash") -> None:
    path.write_bytes(content)


def _manifest(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "alembic_revision": "abc123",
        "counts": {"companies": 3},
        "relationships": {"assessments_without_opportunity": 0},
        "extensions": ["vector"],
    }
    base.update(overrides)
    return base


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    import hashlib

    path = tmp_path / "sample.bin"
    _write_dump(path, b"some deterministic bytes")

    assert sha256_file(path) == hashlib.sha256(b"some deterministic bytes").hexdigest()


def test_run_pg_dump_passes_the_snapshot_flag_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backup.run_pg_dump("postgresql://u:p@h/db", Path("/tmp/x.dump"), snapshot="00000003-1")

    assert "--snapshot=00000003-1" in captured["command"]


def test_run_pg_dump_omits_the_snapshot_flag_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    backup.run_pg_dump("postgresql://u:p@h/db", Path("/tmp/x.dump"))

    assert not any(part.startswith("--snapshot=") for part in captured["command"])


def test_load_manifest_missing_file_fails_strict(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no manifest at"):
        restore_check.load_manifest(tmp_path / "missing.manifest.json", allow_missing=False)


def test_load_manifest_missing_file_allowed_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "missing.manifest.json"

    assert restore_check.load_manifest(path, allow_missing=True) is None


def test_load_manifest_incompatible_format_version_fails_strict(tmp_path: Path) -> None:
    path = tmp_path / "x.manifest.json"
    path.write_text(json.dumps(_manifest(format_version=999)), encoding="utf-8")

    with pytest.raises(SystemExit, match="format_version"):
        restore_check.load_manifest(path, allow_missing=False)


def test_load_manifest_incompatible_format_version_allowed_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "x.manifest.json"
    path.write_text(json.dumps(_manifest(format_version=999)), encoding="utf-8")

    assert restore_check.load_manifest(path, allow_missing=True) is None


def test_load_manifest_reads_a_valid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "x.manifest.json"
    manifest = _manifest()
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert restore_check.load_manifest(path, allow_missing=False) == manifest


def test_verify_checksum_accepts_a_match(tmp_path: Path) -> None:
    dump = tmp_path / "x.dump"
    _write_dump(dump)

    restore_check.verify_checksum(dump, _manifest(sha256=sha256_file(dump)))  # does not raise


def test_verify_checksum_rejects_a_mismatch(tmp_path: Path) -> None:
    dump = tmp_path / "x.dump"
    _write_dump(dump)

    with pytest.raises(SystemExit, match="checksum mismatch"):
        restore_check.verify_checksum(dump, _manifest(sha256="0" * 64))


def test_verify_checksum_is_a_no_op_without_a_recorded_hash(tmp_path: Path) -> None:
    dump = tmp_path / "x.dump"
    _write_dump(dump)

    restore_check.verify_checksum(dump, _manifest(sha256=None))  # does not raise


def test_compare_is_clean_when_everything_matches() -> None:
    manifest = _manifest()
    restored = {
        "alembic_revision": manifest["alembic_revision"],
        "counts": dict(manifest["counts"]),
        "relationships": dict(manifest["relationships"]),
        "extensions": list(manifest["extensions"]),
    }

    assert restore_check.compare(manifest, restored) == []


def test_compare_flags_a_diverging_count() -> None:
    manifest = _manifest()
    restored = {
        "alembic_revision": manifest["alembic_revision"],
        "counts": {"companies": 2},
        "relationships": manifest["relationships"],
        "extensions": manifest["extensions"],
    }

    problems = restore_check.compare(manifest, restored)

    assert any("companies" in problem for problem in problems)


def test_compare_flags_a_broken_relationship() -> None:
    manifest = _manifest()
    restored = {
        "alembic_revision": manifest["alembic_revision"],
        "counts": manifest["counts"],
        "relationships": {"assessments_without_opportunity": 1},
        "extensions": manifest["extensions"],
    }

    problems = restore_check.compare(manifest, restored)

    assert any("assessments_without_opportunity" in problem for problem in problems)


def test_compare_flags_a_missing_extension() -> None:
    manifest = _manifest()
    restored = {
        "alembic_revision": manifest["alembic_revision"],
        "counts": manifest["counts"],
        "relationships": manifest["relationships"],
        "extensions": [],
    }

    problems = restore_check.compare(manifest, restored)

    assert any("vector" in problem for problem in problems)


def test_compare_flags_a_different_migration_revision() -> None:
    manifest = _manifest()
    restored = {
        "alembic_revision": "different",
        "counts": manifest["counts"],
        "relationships": manifest["relationships"],
        "extensions": manifest["extensions"],
    }

    problems = restore_check.compare(manifest, restored)

    assert any("migration revision" in problem for problem in problems)


def test_prune_removes_dumps_and_manifests_past_the_retention(tmp_path: Path) -> None:
    import time

    old_dump = tmp_path / "old.dump"
    old_manifest = tmp_path / "old.manifest.json"
    new_dump = tmp_path / "new.dump"
    for path in (old_dump, old_manifest, new_dump):
        path.write_text("x", encoding="utf-8")
    old_time = time.time() - (40 * 86400)
    os.utime(old_dump, (old_time, old_time))
    os.utime(old_manifest, (old_time, old_time))

    removed = backup.prune(tmp_path, retention_days=30)

    assert removed == [old_dump]
    assert not old_dump.exists()
    assert not old_manifest.exists()
    assert new_dump.exists()


def test_prune_does_nothing_when_retention_is_not_positive(tmp_path: Path) -> None:
    dump = tmp_path / "old.dump"
    dump.write_text("x", encoding="utf-8")

    assert backup.prune(tmp_path, retention_days=0) == []
    assert dump.exists()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
@pytest.mark.skipif(
    shutil.which("pg_dump") is None or shutil.which("pg_restore") is None,
    reason="pg_dump/pg_restore are not on PATH in this environment",
)
def test_backup_and_restore_round_trip_matches_the_manifest(tmp_path: Path) -> None:
    """The full round trip: dump the live test database, restore it, compare."""
    url = os.environ["DATABASE_URL"]
    target = tmp_path / "roundtrip.dump"

    manifest = backup.take_backup(url, target)
    manifest["sha256"] = sha256_file(target)

    dump = target
    manifest_path = dump.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    loaded = restore_check.load_manifest(manifest_path, allow_missing=False)
    assert loaded is not None
    restore_check.verify_checksum(dump, loaded)

    name = restore_check.scratch_name("f20_41_test")
    restore_check.create_database(url, name)
    try:
        restore_check.restore(dump, url, name)
        restored = restore_check.smoke_queries(url, name)
    finally:
        restore_check.drop_database(url, name)

    assert restore_check.compare(loaded, restored) == []


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
@pytest.mark.skipif(
    shutil.which("pg_dump") is None or shutil.which("pg_restore") is None,
    reason="pg_dump/pg_restore are not on PATH in this environment",
)
def test_restore_check_main_fails_on_a_tampered_dump(tmp_path: Path) -> None:
    """A dump edited after the backup wrote it must never be restored as if it were intact."""
    url = os.environ["DATABASE_URL"]
    target = tmp_path / "tampered.dump"

    manifest = backup.take_backup(url, target)
    manifest["sha256"] = sha256_file(target)
    manifest_path = target.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with target.open("ab") as handle:
        handle.write(b"\x00tampered")

    with pytest.raises(SystemExit, match="checksum mismatch"):
        restore_check.main(["--dump", str(target), "--backup-dir", str(tmp_path)])
