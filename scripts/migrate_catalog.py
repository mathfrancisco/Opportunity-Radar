"""Move the source/company catalogue (and recent raw items) between databases (card R55-A2/A3).

Two steps, so the private export can be inspected and kept off the network path:

    # 1. Export from the local development database (read-only; credentials stay in the
    #    container environment). The file lives under `.tmp/` (gitignored) and is private.
    python scripts/migrate_catalog.py export --from-container opportunity-radar-dev-postgres-1 \
        --out .tmp/catalog-export.jsonl

    # 2. Import into a target at the head revision. Dry-run by default: the whole import runs
    #    in one transaction and is rolled back, so the counts are exact and nothing is kept.
    DATABASE_URL=... python scripts/migrate_catalog.py import --export .tmp/catalog-export.jsonl \
        --owner-sub-file /path/to/owner-sub.txt [--apply]

Scope (owner decision): the catalogue only -- companies, aliases, company sources and their
revisions, startup evidence, source definitions and their probes (the homologation record) --
plus raw items fetched in the last `--job-days` days (default 7). Opportunities, assessments,
profile, CRM and AI telemetry are never migrated: the pipeline rebuilds what is derived.

Rules the import follows:

* Idempotent. Every insert is `ON CONFLICT DO NOTHING` (or `WHERE NOT EXISTS`) on the table's
  identity: company `normalized_name`/`domain`, company source (company, type, endpoint), source
  (type, name) -- and also (type, configuration), so the same board under another name is not
  duplicated --, raw item `uq_raw_item_source_identity_hash`. Rows already in the target are
  never modified.
* Schema drift (local at 0068, target at head) is absorbed by importing only the columns both
  sides have; target-only columns (e.g. `source_run.skipped_stale`) take their defaults.
* Sources arrive DISABLED unless they were homologated and enabled locally (the dashboard's
  homologation gate: confirmed evidence, `reviewed_at`, `terms_reviewed`,
  `collector_local_tested`; `manual` sources are exempt). `--all-disabled` disables every one.
* `owner_sub`: no catalogue table carries it at head (tenancy migration 0069 only owns the
  personal-data roots). The owner subject is still required, read from a file and never
  printed, and is written to any migrated table that does have the column.
* Raw items need a run; one synthetic SUCCEEDED run per source (deterministic id,
  `correlation_id = 'r55-catalog-migration'`) adopts them.

Output is counts per table only -- no identifiers, no subjects, no connection strings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

if TYPE_CHECKING:  # the container export needs only the standard library
    from sqlalchemy.engine import Connection

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_RUN_TAG = "r55-catalog-migration"
DEFAULT_JOB_DAYS = 7
EXPORT_VERSION = 1

#: Export order is also the import order (parents before children).
CATALOG_TABLES = (
    "company_radar.company",
    "company_radar.company_alias",
    "company_radar.company_source",
    "company_radar.company_source_revision",
    "company_radar.company_startup_evidence",
    "acquisition.source_definition",
    "acquisition.source_probe",
)
JOB_TABLES = ("acquisition.raw_item", "acquisition.raw_item_payload")
ALL_TABLES = CATALOG_TABLES + ("acquisition.source_run",) + JOB_TABLES

_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


# --------------------------------------------------------------------------- export


def _export_queries(job_days: int) -> dict[str, str]:
    recent = f"fetched_at >= now() - interval '{int(job_days)} days'"
    queries = {table: f"SELECT to_jsonb(t)::text FROM {table} t" for table in CATALOG_TABLES}
    queries["acquisition.raw_item"] = (
        f"SELECT to_jsonb(t)::text FROM acquisition.raw_item t WHERE t.{recent}"
    )
    queries["acquisition.raw_item_payload"] = (
        "SELECT to_jsonb(p)::text FROM acquisition.raw_item_payload p "
        f"JOIN acquisition.raw_item r ON r.id = p.raw_item_id WHERE r.{recent}"
    )
    return queries


def _rows_from_container(container: str, sql: str) -> Iterator[str]:
    """Run one SELECT inside the container, read-only, with credentials from its own env."""
    if not _CONTAINER_RE.match(container):
        raise SystemExit("invalid container name")
    script = (
        'PGOPTIONS="-c default_transaction_read_only=on" '
        'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -X -v ON_ERROR_STOP=1'
    )
    process = subprocess.Popen(
        ["docker", "exec", "-i", container, "sh", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(sql + ";\n")
    process.stdin.close()
    for line in process.stdout:
        line = line.rstrip("\n")
        if line:
            yield line
    process.wait()
    if process.returncode != 0:
        raise SystemExit("export query failed (see container logs; no data was written)")


def _rows_from_url(url: str, sql: str) -> Iterator[str]:
    from sqlalchemy import text

    from opportunity_radar.platform.database import create_database_engine

    engine = create_database_engine(url)
    with engine.connect() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        for (value,) in connection.execute(text(sql)):
            yield value
    engine.dispose()


def run_export(
    *, out: Path, container: str | None, source_url: str | None, job_days: int
) -> dict[str, int]:
    if (container is None) == (source_url is None):
        raise SystemExit("choose exactly one of --from-container or SOURCE_DATABASE_URL")
    reader = (
        (lambda sql: _rows_from_container(container, sql))
        if container is not None
        else (lambda sql: _rows_from_url(str(source_url), sql))
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    temporary = out.with_suffix(out.suffix + ".part")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        header = {
            "meta": {
                "version": EXPORT_VERSION,
                "exported_at": datetime.now(UTC).isoformat(),
                "job_days": job_days,
            }
        }
        handle.write(json.dumps(header) + "\n")
        for table, sql in _export_queries(job_days).items():
            counts[table] = 0
            for payload in reader(sql):
                handle.write(json.dumps({"table": table, "row": json.loads(payload)}) + "\n")
                counts[table] += 1
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(out)
    return counts


# --------------------------------------------------------------------------- import


def read_export(path: Path) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    meta: dict[str, Any] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            entry = json.loads(line)
            if "meta" in entry:
                meta = entry["meta"]
            else:
                tables[entry["table"]].append(entry["row"])
    if meta.get("version") != EXPORT_VERSION:
        raise SystemExit("unsupported export file")
    return meta, tables


def read_owner_sub(path: Path) -> str:
    owner_sub = path.read_text(encoding="utf-8").strip()
    if not owner_sub:
        raise SystemExit("owner sub file is empty")
    return owner_sub


def is_homologated(row: dict[str, Any]) -> bool:
    """The dashboard's homologation gate (`dashboard.metrics._is_homologated`)."""
    return row["source_type"] == "manual" or bool(
        row.get("evidence_status") == "confirmed"
        and row.get("reviewed_at") is not None
        and row.get("terms_reviewed")
        and row.get("collector_local_tested")
    )


def _head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


def _text(sql: str) -> Any:
    from sqlalchemy import text

    return text(sql)


def _table_columns(connection: Connection, qualified: str) -> dict[str, str]:
    rows = connection.execute(
        _text(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a WHERE a.attrelid = CAST(:rel AS regclass) "
            "AND a.attnum > 0 AND NOT a.attisdropped AND a.attgenerated = ''"
        ),
        {"rel": qualified},
    )
    return {name: type_sql for name, type_sql in rows}


def _count(connection: Connection, qualified: str) -> int:
    return int(connection.execute(_text(f"SELECT count(*) FROM {qualified}")).scalar_one())


def _bind(value: Any) -> Any:
    return json.dumps(value) if isinstance(value, (dict, list)) else value


class _Writer:
    """Bulk, conflict-tolerant inserts restricted to the columns both databases have."""

    def __init__(self, connection: Connection, owner_sub: str) -> None:
        self.connection = connection
        self.owner_sub = owner_sub
        self.owner_tables: list[str] = []

    def insert(
        self,
        qualified: str,
        rows: list[dict[str, Any]],
        *,
        guard: str | None = None,
    ) -> None:
        if not rows:
            return
        target = _table_columns(self.connection, qualified)
        columns = [name for name in rows[0] if name in target]
        has_owner = "owner_sub" in target
        if has_owner:
            self.owner_tables.append(qualified)
            if "owner_sub" not in columns:
                columns.append("owner_sub")
        values = ", ".join(f"CAST(:{name} AS {target[name]})" for name in columns)
        names = ", ".join(f'"{name}"' for name in columns)
        if guard is None:
            statement = (
                f"INSERT INTO {qualified} ({names}) VALUES ({values}) ON CONFLICT DO NOTHING"
            )
        else:
            statement = (
                f"INSERT INTO {qualified} ({names}) SELECT {values} WHERE {guard} "
                "ON CONFLICT DO NOTHING"
            )
        parameters = []
        for row in rows:
            bound = {name: _bind(row.get(name)) for name in columns}
            if has_owner:
                bound["owner_sub"] = self.owner_sub
            parameters.append(bound)
        self.connection.execute(_text(statement), parameters)


def _lookup(
    connection: Connection, sql: str, key_columns: tuple[str, ...]
) -> dict[tuple[Any, ...], Any]:
    return {
        tuple(row[name] for name in key_columns): row["id"]
        for row in connection.execute(_text(sql)).mappings()
    }


def _import_catalog(
    connection: Connection,
    writer: _Writer,
    tables: dict[str, list[dict[str, Any]]],
    *,
    all_disabled: bool,
    job_days: int,
    exported_at: datetime,
) -> dict[str, int]:
    notes: dict[str, int] = defaultdict(int)

    # Companies: identity is the normalized name (and the unique domain).
    companies = tables["company_radar.company"]
    writer.insert("company_radar.company", companies)
    company_ids = {
        row["normalized_name"]: row["id"]
        for row in connection.execute(
            _text("SELECT id, normalized_name FROM company_radar.company")
        ).mappings()
    }
    company_map = {
        row["id"]: company_ids[row["normalized_name"]]
        for row in companies
        if row["normalized_name"] in company_ids
    }

    def remap(rows: list[dict[str, Any]], column: str, mapping: dict[Any, Any]) -> list[dict]:
        kept = []
        for row in rows:
            if row[column] in mapping:
                kept.append({**row, column: mapping[row[column]]})
            else:
                notes["orphans_skipped"] += 1
        return kept

    writer.insert(
        "company_radar.company_alias",
        remap(tables["company_radar.company_alias"], "company_id", company_map),
    )

    company_sources = remap(tables["company_radar.company_source"], "company_id", company_map)
    writer.insert("company_radar.company_source", company_sources)
    target_company_sources = _lookup(
        connection,
        "SELECT id, company_id, source_type, endpoint FROM company_radar.company_source",
        ("company_id", "source_type", "endpoint"),
    )
    company_source_map = {}
    for row in company_sources:
        key = (row["company_id"], row["source_type"], row["endpoint"])
        if key in target_company_sources:
            company_source_map[row["id"]] = target_company_sources[key]
    writer.insert(
        "company_radar.company_source_revision",
        remap(
            tables["company_radar.company_source_revision"],
            "company_source_id",
            company_source_map,
        ),
    )
    writer.insert(
        "company_radar.company_startup_evidence",
        remap(tables["company_radar.company_startup_evidence"], "company_id", company_map),
    )

    # Sources: identity is (type, name) by constraint and (type, configuration) by meaning.
    existing_by_config = {
        (row["source_type"], _canonical_json(row["configuration"])): row["id"]
        for row in connection.execute(
            _text("SELECT id, source_type, configuration FROM acquisition.source_definition")
        ).mappings()
    }
    source_rows = []
    config_matched: dict[Any, Any] = {}
    for row in tables["acquisition.source_definition"]:
        config_key = (row["source_type"], _canonical_json(row["configuration"]))
        match = existing_by_config.get(config_key)
        if match is not None:
            config_matched[row["id"]] = match
            notes["sources_matched_by_config"] += 1
            continue
        homologated = is_homologated(row)
        enabled = bool(row["enabled"]) and homologated and not all_disabled
        notes["sources_enabled" if enabled else "sources_disabled"] += 1
        if row["enabled"] and not enabled:
            notes["sources_force_disabled"] += 1
        source_rows.append(
            {
                **row,
                "enabled": enabled,
                "company_source_id": company_source_map.get(row["company_source_id"]),
            }
        )
    writer.insert("acquisition.source_definition", source_rows)
    target_sources = _lookup(
        connection,
        "SELECT id, source_type, name FROM acquisition.source_definition",
        ("source_type", "name"),
    )
    source_map = dict(config_matched)
    for row in tables["acquisition.source_definition"]:
        found = target_sources.get((row["source_type"], row["name"]))
        if row["id"] not in source_map and found is not None:
            source_map[row["id"]] = found

    probes = remap(tables["acquisition.source_probe"], "source_definition_id", source_map)
    writer.insert(
        "acquisition.source_probe",
        probes,
        guard=(
            "NOT EXISTS (SELECT 1 FROM acquisition.source_probe p "
            "WHERE p.source_definition_id = CAST(:source_definition_id AS uuid) "
            "AND p.started_at = CAST(:started_at AS timestamptz) "
            "AND p.requested_by = :requested_by)"
        ),
    )

    # Recent raw items, adopted by one synthetic run per source.
    raw_items = remap(tables["acquisition.raw_item"], "source_definition_id", source_map)
    per_source: dict[Any, int] = defaultdict(int)
    for row in raw_items:
        per_source[row["source_definition_id"]] += 1
    run_ids = {
        source_id: str(uuid5(NAMESPACE_URL, f"{MIGRATION_RUN_TAG}:{source_id}"))
        for source_id in per_source
    }
    stamp = exported_at.isoformat()
    writer.insert(
        "acquisition.source_run",
        [
            {
                "id": run_ids[source_id],
                "source_definition_id": source_id,
                "execution_trigger": "ON_DEMAND",
                "status": "SUCCEEDED",
                "started_at": stamp,
                "finished_at": stamp,
                "items_seen": count,
                "items_persisted": count,
                "correlation_id": MIGRATION_RUN_TAG,
                "complete": False,
            }
            for source_id, count in per_source.items()
        ],
    )
    writer.insert(
        "acquisition.raw_item",
        [
            {**row, "source_run_id": run_ids[row["source_definition_id"]]}
            for row in raw_items
        ],
    )
    writer.insert(
        "acquisition.raw_item_payload",
        tables["acquisition.raw_item_payload"],
        guard=(
            "EXISTS (SELECT 1 FROM acquisition.raw_item r "
            "WHERE r.id = CAST(:raw_item_id AS uuid))"
        ),
    )
    notes["job_days"] = job_days
    return dict(notes)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def run_import(
    *,
    database_url: str,
    export_path: Path,
    owner_sub: str,
    apply: bool,
    all_disabled: bool = False,
) -> dict[str, Any]:
    from opportunity_radar.platform.database import create_database_engine

    meta, tables = read_export(export_path)
    exported_at = datetime.fromisoformat(meta["exported_at"])
    engine = create_database_engine(database_url)
    try:
        with engine.connect() as connection:
            current = connection.execute(
                _text("SELECT version_num FROM public.alembic_version")
            ).scalar_one_or_none()
            head = _head_revision()
            if current != head:
                raise SystemExit(
                    f"target is at {current}, not head {head}: run alembic upgrade head first"
                )
            connection.rollback()  # end the autobegun version read
            transaction = connection.begin()
            try:
                before = {t: _count(connection, t) for t in ALL_TABLES}
                writer = _Writer(connection, owner_sub)
                notes = _import_catalog(
                    connection,
                    writer,
                    tables,
                    all_disabled=all_disabled,
                    job_days=int(meta["job_days"]),
                    exported_at=exported_at,
                )
                after = {t: _count(connection, t) for t in ALL_TABLES}
            except BaseException:
                transaction.rollback()
                raise
            if apply:
                transaction.commit()
            else:
                transaction.rollback()
    finally:
        engine.dispose()
    report_tables = {}
    for table in ALL_TABLES:
        exported = len(tables.get(table, []))
        report_tables[table] = {
            "exported": exported,
            "before": before[table],
            "after": after[table],
            "inserted": after[table] - before[table],
        }
    return {
        "mode": "apply" if apply else "dry-run (rolled back, nothing written)",
        "tables": report_tables,
        "notes": {**notes, "owner_sub_tables": sorted(set(writer.owner_tables))},
    }


# --------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)

    export = commands.add_parser("export", help="read the local catalogue into a private file")
    export.add_argument("--out", type=Path, default=Path(".tmp/catalog-export.jsonl"))
    export.add_argument("--from-container", help="docker container running the source Postgres")
    export.add_argument("--job-days", type=int, default=DEFAULT_JOB_DAYS)

    importer = commands.add_parser("import", help="write an export into DATABASE_URL")
    importer.add_argument("--export", type=Path, required=True, dest="export_path")
    importer.add_argument("--owner-sub-file", type=Path, required=True)
    importer.add_argument("--apply", action="store_true", help="commit (default: dry-run)")
    importer.add_argument(
        "--all-disabled", action="store_true", help="import every source disabled"
    )

    args = parser.parse_args(argv)
    if args.command == "export":
        counts = run_export(
            out=args.out,
            container=args.from_container,
            source_url=os.environ.get("SOURCE_DATABASE_URL"),
            job_days=args.job_days,
        )
        print(json.dumps({"exported": counts, "file": str(args.out)}, indent=2))
        return
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    report = run_import(
        database_url=database_url,
        export_path=args.export_path,
        owner_sub=read_owner_sub(args.owner_sub_file),
        apply=args.apply,
        all_disabled=args.all_disabled,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
