"""Dump the local database and record what the dump contains.

Section 65 of the roadmap: producing a file is not the criterion. The manifest written
next to each dump is what makes the restore check able to assert that the data came back,
instead of only asserting that a restore command exited zero.

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

from sqlalchemy import text

from opportunity_radar.platform.backup import (
    MANIFEST_QUERIES,
    database_name,
    database_url,
    postgres_dsn,
)
from opportunity_radar.platform.database import create_database_engine

DEFAULT_OUTPUT_DIR = Path("data/backups")


def collect_manifest(url: str) -> dict[str, Any]:
    engine = create_database_engine(url)
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        for label, query in MANIFEST_QUERIES.items():
            counts[label] = int(connection.execute(text(query)).scalar_one())
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "alembic_revision": revision,
        "database": database_name(url),
        "counts": counts,
    }


def run_pg_dump(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={target}",
        postgres_dsn(url),
    ]
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

    manifest = collect_manifest(url)
    run_pg_dump(url, target)
    manifest["file"] = target.name
    manifest["bytes"] = target.stat().st_size
    manifest_path = target.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    removed = prune(args.output_dir, args.prune_days)
    print(f"wrote {target} ({manifest['bytes']} bytes)")
    print(f"wrote {manifest_path}")
    for dump in removed:
        print(f"pruned {dump}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
