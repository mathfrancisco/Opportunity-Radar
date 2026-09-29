"""Restore a dump into a scratch database and prove the data came back.

Section 65 of the roadmap is explicit that creating a dump does not satisfy the backup
criterion. This restores into a throwaway database, runs smoke queries against it, and
compares them with the manifest written at backup time. The working database is never
touched, and the scratch one is dropped afterwards unless asked to stay.

Card F20-41 (old F18-08): the gate is strict by default — no manifest, an incompatible
`format_version`, or a dump whose sha256 no longer matches the manifest all fail the run
before anything is restored. `--allow-missing-manifest` is the one, explicit way past
that, for a dump that predates this manifest shape; it downgrades the check to
readability-only, and the run says so on every line it prints. The comparison itself now
also covers the relationship counts and the extensions the manifest recorded, not just
row counts: a restore that lost a foreign key's other side, or came up in an image
without pgvector, fails here instead of only failing the first query that needs it.

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
    ALEMBIC_REVISION_QUERY,
    EXTENSIONS_QUERY,
    FORMAT_VERSION,
    MANIFEST_QUERIES,
    RELATIONSHIP_QUERIES,
    database_url,
    postgres_dsn,
    sha256_file,
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
    relationships: dict[str, int] = {}
    with engine.connect() as connection:
        revision = connection.execute(text(ALEMBIC_REVISION_QUERY)).scalar_one()
        for label, query in MANIFEST_QUERIES.items():
            counts[label] = int(connection.execute(text(query)).scalar_one())
        for label, query in RELATIONSHIP_QUERIES.items():
            relationships[label] = int(connection.execute(text(query)).scalar_one())
        extensions = [
            row[0] for row in connection.execute(text(EXTENSIONS_QUERY)).all()
        ]
    engine.dispose()
    return {
        "alembic_revision": revision,
        "counts": counts,
        "relationships": relationships,
        "extensions": extensions,
    }


def load_manifest(path: Path, *, allow_missing: bool) -> dict[str, Any] | None:
    """The manifest a restore is graded against, or `None` for a readability-only run.

    Strict by default: an absent manifest or an incompatible `format_version` fails the
    whole run rather than silently checking less than the caller thinks it is checking.
    `allow_missing` is the explicit override for a dump that predates this manifest shape.
    """
    if not path.is_file():
        if allow_missing:
            print(
                f"no manifest at {path}; checking readability only "
                "(--allow-missing-manifest)",
                file=sys.stderr,
            )
            return None
        raise SystemExit(
            f"no manifest at {path}; refusing to grade this restore without one "
            "(pass --allow-missing-manifest to check readability only)"
        )
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != FORMAT_VERSION:
        if allow_missing:
            print(
                f"manifest format_version {manifest.get('format_version')!r} is not "
                f"supported (expected {FORMAT_VERSION}); checking readability only "
                "(--allow-missing-manifest)",
                file=sys.stderr,
            )
            return None
        raise SystemExit(
            f"manifest format_version {manifest.get('format_version')!r} is not "
            f"supported (expected {FORMAT_VERSION}); pass --allow-missing-manifest to "
            "check readability only"
        )
    return manifest


def verify_checksum(dump: Path, manifest: dict[str, Any]) -> None:
    """Refuse to restore a dump that no longer matches the checksum its manifest recorded."""
    expected = manifest.get("sha256")
    if expected is None:
        return
    actual = sha256_file(dump)
    if actual != expected:
        raise SystemExit(
            f"{dump.name}: checksum mismatch, expected {expected}, got {actual} "
            "(the file changed after the backup wrote it)"
        )


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
    for label, expected in manifest.get("relationships", {}).items():
        actual = restored["relationships"].get(label)
        if actual != expected:
            problems.append(f"relationship {label}: expected {expected}, restored {actual}")
    missing_extensions = sorted(set(manifest.get("extensions", [])) - set(restored["extensions"]))
    if missing_extensions:
        problems.append(f"extensions missing after restore: {', '.join(missing_extensions)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", type=Path, default=None)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--keep", action="store_true", help="do not drop the scratch DB")
    parser.add_argument(
        "--allow-missing-manifest",
        action="store_true",
        help="check readability only when no valid manifest is found, instead of failing",
    )
    args = parser.parse_args(argv)

    url = database_url()
    dump = args.dump or newest_dump(args.backup_dir)
    manifest_path = dump.with_suffix(".manifest.json")
    manifest = load_manifest(manifest_path, allow_missing=args.allow_missing_manifest)
    if manifest is not None:
        verify_checksum(dump, manifest)

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
    if restored["extensions"]:
        print(f"  extensions: {', '.join(restored['extensions'])}")

    problems = compare(manifest, restored) if manifest is not None else []
    if problems:
        print("restore check failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if manifest is not None:
        print("restore check passed")
    else:
        print("restore check passed (readability only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
