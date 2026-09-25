"""Dump the local database and record what the dump contains.

Section 65 of the roadmap: producing a file is not the criterion. The manifest written
next to each dump is what makes the restore check able to assert that the data came back,
instead of only asserting that a restore command exited zero.

Card F20-41 (old F18-08) closed two gaps in that manifest:

- The manifest used to be read from its own connection, separately from `pg_dump`. A
  write landing between the two saw a different database in each, so a real divergence
  and an artefact of timing looked the same. `pg_export_snapshot()` ties them to the one
  transaction `pg_dump --snapshot` also reads, so both describe the exact same instant.
- The manifest now carries a `format_version` and the dump's `sha256`, and both files are
  written under a temporary name and renamed into place, so a reader never sees a partial
  dump or a manifest for a dump that is still being written.

    python scripts/backup.py                      # writes data/backups/<stamp>.dump
    python scripts/backup.py --output-dir /tmp    # somewhere else
    python scripts/backup.py --prune-days 14      # drop dumps older than the retention
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from opportunity_radar.platform.backup import (
    ALEMBIC_REVISION_QUERY,
    EXTENSIONS_QUERY,
    FORMAT_VERSION,
    MANIFEST_QUERIES,
    RELATIONSHIP_QUERIES,
    database_name,
    database_url,
    postgres_dsn,
    sha256_file,
)
from opportunity_radar.platform.database import create_database_engine

DEFAULT_OUTPUT_DIR = Path("data/backups")


def take_backup(url: str, target: Path) -> dict[str, Any]:
    """Dump `url` into `target` and return a manifest from the same snapshot.

    The exporting transaction stays open, read-only, for as long as `pg_dump` runs: that
    is what makes its snapshot id still valid when `pg_dump` asks for it.
    """
    engine = create_database_engine(url)
    connection = engine.raw_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY, DEFERRABLE")
        cursor.execute("SELECT pg_export_snapshot()")
        snapshot_id = cursor.fetchone()[0]
        manifest = _read_manifest(cursor)
        run_pg_dump(url, target, snapshot=snapshot_id)
    finally:
        connection.rollback()
        connection.close()
    return manifest


def _read_manifest(cursor: Any) -> dict[str, Any]:
    cursor.execute(ALEMBIC_REVISION_QUERY)
    revision = cursor.fetchone()[0]
    counts: dict[str, int] = {}
    for label, query in MANIFEST_QUERIES.items():
        cursor.execute(query)
        counts[label] = int(cursor.fetchone()[0])
    relationships: dict[str, int] = {}
    for label, query in RELATIONSHIP_QUERIES.items():
        cursor.execute(query)
        relationships[label] = int(cursor.fetchone()[0])
    cursor.execute(EXTENSIONS_QUERY)
    extensions = [row[0] for row in cursor.fetchall()]
    return {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "alembic_revision": revision,
        "counts": counts,
        "relationships": relationships,
        "extensions": extensions,
    }


def run_pg_dump(url: str, target: Path, *, snapshot: str | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={target}",
    ]
    if snapshot is not None:
        command.append(f"--snapshot={snapshot}")
    command.append(postgres_dsn(url))
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise SystemExit(
            "pg_dump is not available; run this through `make backup`"
        ) from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"pg_dump failed: {error.stderr.strip()}") from error


def prune(directory: Path, retention_days: int) -> list[Path]:
    if retention_days <= 0:
        return []
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed: list[Path] = []
    for dump in sorted(directory.glob("*.dump")):
        stamp = datetime.fromtimestamp(dump.stat().st_mtime, UTC)
        if stamp < cutoff:
            dump.unlink()
            dump.with_suffix(".manifest.json").unlink(missing_ok=True)
            removed.append(dump)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--label", default=None, help="name the dump instead of stamping it")
    parser.add_argument(
        "--prune-days",
        type=int,
        default=int(os.environ.get("BACKUP_RETENTION_DAYS", "0") or 0),
    )
    args = parser.parse_args(argv)

    url = database_url()
    stamp = args.label or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = args.output_dir / f"{stamp}.dump"
    manifest_path = target.with_suffix(".manifest.json")
    target_tmp = target.with_name(target.name + ".tmp")
    manifest_tmp = manifest_path.with_name(manifest_path.name + ".tmp")

    manifest = take_backup(url, target_tmp)
    manifest["file"] = target.name
    manifest["bytes"] = target_tmp.stat().st_size
    manifest["sha256"] = sha256_file(target_tmp)
    manifest["database"] = database_name(url)
    manifest_tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # The dump is complete and hashed, and the manifest fully written, before either one
    # takes its real name: a reader never sees a dump with no manifest, or a half file.
    os.replace(target_tmp, target)
    os.replace(manifest_tmp, manifest_path)

    removed = prune(args.output_dir, args.prune_days)
    print(f"wrote {target} ({manifest['bytes']} bytes, sha256 {manifest['sha256'][:12]}...)")
    print(f"wrote {manifest_path}")
    for dump in removed:
        print(f"pruned {dump}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
