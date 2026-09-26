"""Integration proof for the F20-41 backup acceptance criteria that need a real
Postgres: a concurrent writer during the dump must not cause an artificial count
divergence between the manifest and the restored database.

`tests/backend/test_backup.py` already unit-tests the strict gate (missing/incompatible
manifest, checksum mismatch — acceptance criterion 2), the comparison logic including
relationships and extensions (acceptance criterion 3), and runs the full round trip
against the live test database. This file adds the one scenario those unit tests cannot
cover without a real server: a write landing between the manifest read and the `pg_dump`
that reads the same exported snapshot.

Gated behind `RUN_DATABASE_INTEGRATION=1`, same as the rest of the database integration
suite; skips itself if `pg_dump`/`pg_restore` are not on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from opportunity_radar.platform.backup import sha256_file
from opportunity_radar.platform.database import create_database_engine
from scripts import backup, restore_check

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
    pytest.mark.skipif(
        shutil.which("pg_dump") is None or shutil.which("pg_restore") is None,
        reason="pg_dump/pg_restore are not on PATH in this environment",
    ),
]


def test_concurrent_writer_does_not_cause_artificial_count_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row inserted after the manifest's snapshot is exported, but before `pg_dump`
    runs, must be invisible to both the manifest and the dump — never counted in one
    and not the other. That is exactly what `pg_export_snapshot()` + `pg_dump
    --snapshot` buys: the concurrent write is consistently excluded from both, so the
    restore's counts equal the manifest's counts with no divergence to explain away.
    """
    url = os.environ["DATABASE_URL"]
    target = tmp_path / "concurrent.dump"
    engine = create_database_engine(url)

    inserted = threading.Event()

    real_run_pg_dump = backup.run_pg_dump

    def racing_run_pg_dump(dump_url: str, dump_target: Path, **kwargs: object) -> None:
        # Simulate a writer landing in the window between the manifest's snapshot
        # export and pg_dump actually reading it.
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO company_radar.company "
                    "(id, canonical_name, normalized_name, priority, radar_status, "
                    "verification_state, version) "
                    "VALUES (:id, :name, :name, 'normal', 'active', 'unverified', 1)"
                ),
                {"id": str(uuid.uuid4()), "name": f"race-condition-co-{uuid.uuid4()}"},
            )
        inserted.set()
        real_run_pg_dump(dump_url, dump_target, **kwargs)

    monkeypatch.setattr(backup, "run_pg_dump", racing_run_pg_dump)

    manifest = backup.take_backup(url, target)
    assert inserted.is_set(), "the concurrent insert must have run before pg_dump"
    manifest["sha256"] = sha256_file(target)
    manifest_path = target.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    loaded = restore_check.load_manifest(manifest_path, allow_missing=False)
    assert loaded is not None
    restore_check.verify_checksum(target, loaded)

    name = restore_check.scratch_name("f20_41_concurrent")
    restore_check.create_database(url, name)
    try:
        restore_check.restore(target, url, name)
        restored = restore_check.smoke_queries(url, name)
    finally:
        restore_check.drop_database(url, name)

    # The row inserted mid-dump must not appear in the restore: the snapshot pinned
    # both the manifest and the dump to the instant before the insert.
    assert restore_check.compare(loaded, restored) == []
