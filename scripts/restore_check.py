"""Restore a dump into a scratch database and prove the data came back.

Section 65 of the roadmap is explicit that creating a dump does not satisfy the backup
criterion. This restores into a throwaway database, runs smoke queries against it, and
compares them with the manifest written at backup time. The working database is never
touched, and the scratch one is dropped afterwards unless asked to stay.

    python scripts/restore_check.py                       # newest dump in data/backups
    python scripts/restore_check.py --dump path/to.dump   # a specific one
    python scripts/restore_check.py --keep                # leave the scratch DB behind
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from opportunity_radar.platform.backup import (
    MANIFEST_QUERIES,
    database_url,
    postgres_dsn,
    with_database,
)

DEFAULT_BACKUP_DIR = Path("data/backups")


def newest_dump(directory: Path) -> Path:
    dumps = sorted(directory.glob("*.dump"), key=lambda path: path.stat().st_mtime)
    if not dumps:
        raise SystemExit(f"no dump found in {directory}; run scripts/backup.py first")
    return dumps[-1]


def scratch_name(prefix: str = "restore_check") -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"


def admin_engine(url: str) -> Any:
    """Connect to `postgres` so the scratch database can be created and dropped."""
    return create_engine(with_database(url, "postgres"), isolation_level="AUTOCOMMIT")


def create_database(url: str, name: str) -> None:
    with admin_engine(url).connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))


def drop_database(url: str, name: str) -> None:
    with admin_engine(url).connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": name},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))


def restore(dump: Path, url: str, name: str) -> None:
    command = [
        "pg_restore",
        "--no-owner",
        "--no-privileges",
        "--exit-on-error",
        f"--dbname={postgres_dsn(with_database(url, name))}",
        str(dump),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise SystemExit(
            "pg_restore is not available; run this through `make restore-check`"
        ) from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"pg_restore failed: {error.stderr.strip()}") from error


def smoke_queries(url: str, name: str) -> dict[str, Any]:
    engine = create_engine(with_database(url, name))
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        for label, query in MANIFEST_QUERIES.items():
            counts[label] = int(connection.execute(text(query)).scalar_one())
    engine.dispose()
    return {"alembic_revision": revision, "counts": counts}


def compare(manifest: dict[str, Any], restored: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if manifest.get("alembic_revision") != restored["alembic_revision"]:
        problems.append(
            f"migration revision differs: dump {manifest.get('alembic_revision')}, "
            f"restore {restored['alembic_revision']}"
        )
    for label, expected in manifest.get("counts", {}).items():
        actual = restored["counts"].get(label)
        if actual != expected:
            problems.append(f"{label}: expected {expected}, restored {actual}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--keep", action="store_true", help="do not drop the scratch DB")
    args = parser.parse_args(argv)

    url = database_url()
    dump = args.dump or newest_dump(args.backup_dir)
    manifest_path = dump.with_suffix(".manifest.json")
    manifest: dict[str, Any] = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    if not manifest:
        print(
            f"no manifest beside {dump.name}; the restore will be checked for "
            "readability only",
            file=sys.stderr,
        )

    name = scratch_name()
    print(f"restoring {dump} into {name}")
    create_database(url, name)
    try:
        restore(dump, url, name)
        restored = smoke_queries(url, name)
    finally:
        if args.keep:
            print(f"scratch database kept: {name}")
        else:
            drop_database(url, name)

    for label, value in restored["counts"].items():
        print(f"  {label}: {value}")

    problems = compare(manifest, restored) if manifest else []
    if problems:
        print("restore check failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print("restore check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
