"""Move the source/company catalogue (and recent raw items) between databases (card R55-A2/A3).

Two steps, so the private export can be inspected and kept off the network path:

    # 1. Export from the local development database (one read-only REPEATABLE READ session;
    #    credentials stay in the container environment). The file lives under `.tmp/`
    #    (gitignored), is created exclusively with mode 0600 and is private.
    python scripts/migrate_catalog.py export --from-container opportunity-radar-dev-postgres-1 \
        --out .tmp/catalog-export.jsonl

    # 2. Import into a target at the head revision. Dry-run by default: the whole import runs
    #    in one transaction and is rolled back, so the counts are exact and nothing is kept.
    DATABASE_URL=... python scripts/migrate_catalog.py import --export .tmp/catalog-export.jsonl \
        --owner-sub-file /path/to/owner-sub.txt [--enable-limit N] [--apply]

Scope (owner decision): the catalogue only -- companies, aliases, company sources and their
revisions, startup evidence, source definitions and their probes (the homologation record) --
plus raw items fetched in the last `--job-days` days (default 7), but only those of sources
that this run creates *and* enables. Opportunities, assessments, profile, CRM and AI telemetry
are never migrated: the pipeline rebuilds what is derived.

Rules the import follows:

* Idempotent and additive. Every insert is `ON CONFLICT DO NOTHING` (or `WHERE NOT EXISTS`);
  rows already in the target are never modified, adopted or given children.
* Source identity is the provider endpoint, not the display name: greenhouse `board_token`,
  ashby `board_identifier`, lever `site_identifier`+`api_region`, workable `account_identifier`,
  inhire `tenant_identifier`, workday `tenant_identifier`+`api_region`, teamtailor/factorial
  `company_identifier`, jobposting `page_url`; types without an endpoint key (manual,
  remotive, hacker_news) are identified by (type, name). Per local source:
    - target has the same (type, name) with the same identity -> it already exists, skipped;
    - target has the same (type, name) with a DIFFERENT identity -> `source_conflicts`: the
      local source and everything under it is skipped (never adopted);
    - target has the same identity under another name -> `sources_matched_other_name`, skipped;
    - otherwise it is new.
* Schema drift (local at 0068, target at head) is absorbed by importing only the columns both
  sides have; target-only columns (e.g. `source_run.skipped_stale`) take their defaults.
* New sources arrive DISABLED. `--enable-limit N` (default 0) enables up to N of those that
  were enabled and homologated locally (confirmed evidence, `reviewed_at`, `terms_reviewed`,
  `collector_local_tested`; `manual` exempt), in (priority, type, name) order, so the owner
  can turn sources on gradually. Homologation state and probes are preserved either way.
* `owner_sub`: no catalogue table carries it at head (tenancy migration 0069 only owns the
  personal-data roots). The owner subject is still required, read from a file and never
  printed, and is written to any migrated table that does have the column.
* Raw items belong to a run; one synthetic SUCCEEDED run per *new, enabled* source adopts them
  (deterministic id, `correlation_id = 'r55-catalog-migration'`, timestamps at the newest
  item's `fetched_at`, counters = rows actually inserted).

Output is counts per table only -- no identifiers, no subjects, no connection strings; errors
print only the exception class and SQLSTATE.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

if TYPE_CHECKING:  # the container export needs only the standard library
    from sqlalchemy.engine import Connection, Engine

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_RUN_TAG = "r55-catalog-migration"
DEFAULT_JOB_DAYS = 7
EXPORT_VERSION = 2

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

#: Configuration keys that identify the provider endpoint of a source, per source type.
IDENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "greenhouse": ("board_token",),
    "ashby": ("board_identifier",),
    "lever": ("site_identifier", "api_region"),
    "workable": ("account_identifier",),
    "inhire": ("tenant_identifier",),
    "workday": ("tenant_identifier", "api_region"),
    "teamtailor": ("company_identifier",),
    "factorial": ("company_identifier",),
    "jobposting": ("page_url",),
}

_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def source_identity(source_type: str, name: str, configuration: Any) -> tuple[Any, ...]:
    """Endpoint identity of a source; (type, name) when its type has no endpoint key."""
    keys = IDENTITY_KEYS.get(source_type)
    if not keys:
        return (source_type, "name", str(name).strip().lower())
    config = configuration if isinstance(configuration, dict) else {}
    return (source_type, *(str(config.get(key) or "").strip().lower() for key in keys))


# --------------------------------------------------------------------------- export


def _export_queries(job_days: int) -> list[tuple[str, str]]:
    recent = f"fetched_at >= now() - interval '{int(job_days)} days'"
    queries = [(table, f"FROM {table} t") for table in CATALOG_TABLES]
    queries.append(("acquisition.raw_item", f"FROM acquisition.raw_item t WHERE t.{recent}"))
    queries.append(
        (
            "acquisition.raw_item_payload",
            "FROM acquisition.raw_item_payload t JOIN acquisition.raw_item r "
            f"ON r.id = t.raw_item_id WHERE r.{recent}",
        )
    )
    return queries


def _select(table: str, source: str) -> str:
    return f"SELECT '{table}' || chr(9) || to_jsonb(t)::text {source}"


def _stream_from_container(container: str, job_days: int) -> Iterator[tuple[str, str]]:
    """One psql session, one REPEATABLE READ read-only transaction: a consistent snapshot."""
    if not _CONTAINER_RE.match(container):
        raise SystemExit("invalid container name")
    script = 'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -q -X -v ON_ERROR_STOP=1'
    statements = ["BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;"]
    statements += [f"{_select(t, q)};" for t, q in _export_queries(job_days)]
    statements.append("COMMIT;")
    process = subprocess.Popen(
        ["docker", "exec", "-i", container, "sh", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    )
    try:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write("\n".join(statements) + "\n")
        process.stdin.close()
        known = {t for t, _ in _export_queries(job_days)}
        for line in process.stdout:
            table, _, payload = line.rstrip("\n").partition("\t")
            if table in known and payload:
                yield table, payload
        process.wait()
        if process.returncode != 0:
            raise SystemExit("export query failed; no export file was kept")
    finally:
        if process.poll() is None:
            process.kill()


def _stream_from_url(url: str, job_days: int) -> Iterator[tuple[str, str]]:
    from sqlalchemy import text

    engine = _engine(url)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            for table, source in _export_queries(job_days):
                sql = f"SELECT to_jsonb(t)::text {source}"
                for (value,) in connection.execute(text(sql)):
                    yield table, value
    finally:
        engine.dispose()


def run_export(
    *, out: Path, container: str | None, source_url: str | None, job_days: int
) -> dict[str, int]:
    if (container is None) == (source_url is None):
        raise SystemExit("choose exactly one of --from-container or SOURCE_DATABASE_URL")
    stream = (
        _stream_from_container(container, job_days)
        if container is not None
        else _stream_from_url(str(source_url), job_days)
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    counts = {table: 0 for table, _ in _export_queries(job_days)}
    temporary = out.with_suffix(out.suffix + ".part")
    # Exclusive creation with owner-only permissions: never follow or reuse an existing path.
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            header = {
                "meta": {
                    "version": EXPORT_VERSION,
                    "exported_at": datetime.now(UTC).isoformat(),
                    "job_days": job_days,
                }
            }
            handle.write(json.dumps(header) + "\n")
            for table, payload in stream:
                handle.write(json.dumps({"table": table, "row": json.loads(payload)}) + "\n")
                counts[table] += 1
        temporary.replace(out)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
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


def _engine(url: str) -> Engine:
    from sqlalchemy import create_engine

    # Parameters are hidden so no bound value (including the owner subject) reaches an error.
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)


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


def _bind(value: Any, column_type: str) -> Any:
    """JSON columns take serialized JSON (scalars included); everything else passes through."""
    if column_type in ("jsonb", "json"):
        return None if value is None else json.dumps(value)
    return value


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
        keys = set(rows[0])
        if any(set(row) != keys for row in rows):
            raise SystemExit(f"export rows of {qualified} do not share one set of columns")
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
            bound = {name: _bind(row.get(name), target[name]) for name in columns}
            if has_owner:
                bound["owner_sub"] = self.owner_sub
            parameters.append(bound)
        self.connection.execute(_text(statement), parameters)


def _rows(connection: Connection, sql: str, params: dict[str, Any] | None = None) -> list:
    return list(connection.execute(_text(sql), params or {}).mappings())


def _import_catalog(
    connection: Connection,
    writer: _Writer,
    tables: dict[str, list[dict[str, Any]]],
    *,
    enable_limit: int,
    job_days: int,
) -> dict[str, int]:
    notes: dict[str, int] = defaultdict(int)

    def remap(rows: list[dict[str, Any]], column: str, mapping: dict[Any, Any]) -> list[dict]:
        kept = []
        for row in rows:
            if row[column] in mapping:
                kept.append({**row, column: mapping[row[column]]})
            else:
                notes["children_skipped_without_parent"] += 1
        return kept

    # ---- companies: identity is the normalized name (and the unique domain)
    companies = tables["company_radar.company"]
    existing_names = {
        r["normalized_name"]
        for r in _rows(connection, "SELECT normalized_name FROM company_radar.company")
    }
    writer.insert("company_radar.company", companies)
    company_ids = {
        r["normalized_name"]: r["id"]
        for r in _rows(connection, "SELECT id, normalized_name FROM company_radar.company")
    }
    company_map = {
        row["id"]: company_ids[row["normalized_name"]]
        for row in companies
        if row["normalized_name"] in company_ids
    }
    notes["company_domain_conflicts"] = sum(
        1 for row in companies if row["normalized_name"] not in company_ids
    )
    new_company_ids = {
        row["id"] for row in companies if row["normalized_name"] not in existing_names
    }
    writer.insert(
        "company_radar.company_alias",
        remap(tables["company_radar.company_alias"], "company_id", company_map),
    )
    # Startup evidence is append-only history: only for companies this run created.
    evidence = [
        row
        for row in tables["company_radar.company_startup_evidence"]
        if row["company_id"] in new_company_ids
    ]
    notes["startup_evidence_skipped_preexisting"] = len(
        tables["company_radar.company_startup_evidence"]
    ) - len(evidence)
    writer.insert(
        "company_radar.company_startup_evidence", remap(evidence, "company_id", company_map)
    )

    # ---- company sources
    prior_company_sources = {
        (r["company_id"], r["source_type"], r["endpoint"])
        for r in _rows(
            connection,
            "SELECT company_id, source_type, endpoint FROM company_radar.company_source",
        )
    }
    company_sources = remap(tables["company_radar.company_source"], "company_id", company_map)
    writer.insert("company_radar.company_source", company_sources)
    target_company_sources = {
        (r["company_id"], r["source_type"], r["endpoint"]): r["id"]
        for r in _rows(
            connection,
            "SELECT id, company_id, source_type, endpoint FROM company_radar.company_source",
        )
    }
    company_source_map = {}
    new_company_source_ids = set()
    for row in company_sources:
        key = (row["company_id"], row["source_type"], row["endpoint"])
        if key in target_company_sources:
            company_source_map[row["id"]] = target_company_sources[key]
            if key not in prior_company_sources:
                new_company_source_ids.add(row["id"])
    revisions = [
        row
        for row in tables["company_radar.company_source_revision"]
        if row["company_source_id"] in new_company_source_ids
    ]
    notes["revisions_skipped_preexisting"] = len(
        tables["company_radar.company_source_revision"]
    ) - len(revisions)
    writer.insert(
        "company_radar.company_source_revision",
        remap(revisions, "company_source_id", company_source_map),
    )

    # ---- sources: classify each local source against the target by endpoint identity
    target_sources = _rows(
        connection,
        "SELECT id, source_type, name, configuration FROM acquisition.source_definition",
    )
    by_name = {(r["source_type"], r["name"]): r for r in target_sources}
    by_identity = {
        source_identity(r["source_type"], r["name"], r["configuration"]): r
        for r in target_sources
    }
    new_sources: list[dict[str, Any]] = []
    for row in tables["acquisition.source_definition"]:
        identity = source_identity(row["source_type"], row["name"], row["configuration"])
        same_name = by_name.get((row["source_type"], row["name"]))
        if same_name is not None:
            theirs = source_identity(
                same_name["source_type"], same_name["name"], same_name["configuration"]
            )
            notes["sources_preexisting" if theirs == identity else "source_conflicts"] += 1
        elif identity in by_identity:
            notes["sources_matched_other_name"] += 1
        else:
            new_sources.append(row)
            by_identity[identity] = row  # a second local copy of one endpoint is not new
    candidates = sorted(
        (r for r in new_sources if r["enabled"] and is_homologated(r)),
        key=lambda r: (r["priority"], r["source_type"], r["name"]),
    )
    to_enable = {r["id"] for r in candidates[: max(enable_limit, 0)]}
    new_rows = [
        {
            **row,
            "enabled": row["id"] in to_enable,
            "company_source_id": company_source_map.get(row["company_source_id"]),
        }
        for row in new_sources
    ]
    writer.insert("acquisition.source_definition", new_rows)
    new_ids = [row["id"] for row in new_rows]
    landed = (
        _rows(
            connection,
            "SELECT id, enabled FROM acquisition.source_definition "
            "WHERE id = ANY(CAST(:ids AS uuid[]))",
            {"ids": new_ids},
        )
        if new_ids
        else []
    )
    landed_ids = {str(r["id"]) for r in landed}
    notes["sources_new_enabled"] = sum(1 for r in landed if r["enabled"])
    notes["sources_new_disabled"] = sum(1 for r in landed if not r["enabled"])
    notes["sources_enable_candidates_not_enabled"] = max(
        len(candidates) - notes["sources_new_enabled"], 0
    )
    source_map = {sid: sid for sid in landed_ids}

    probes = remap(tables["acquisition.source_probe"], "source_definition_id", source_map)
    notes["probes_skipped_not_new_source"] = len(tables["acquisition.source_probe"]) - len(probes)
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

    # ---- recent raw items: only for new sources that were enabled
    enabled_new = {str(r["id"]) for r in landed if r["enabled"]}
    raw_items = [
        row
        for row in tables["acquisition.raw_item"]
        if str(row["source_definition_id"]) in enabled_new
    ]
    notes["raw_items_skipped"] = len(tables["acquisition.raw_item"]) - len(raw_items)
    newest: dict[str, str] = {}
    for row in raw_items:
        sid = str(row["source_definition_id"])
        newest[sid] = max(newest.get(sid, ""), row["fetched_at"])
    run_ids = {
        sid: str(uuid5(NAMESPACE_URL, f"{MIGRATION_RUN_TAG}:{sid}")) for sid in newest
    }
    writer.insert(
        "acquisition.source_run",
        [
            {
                "id": run_ids[sid],
                "source_definition_id": sid,
                "execution_trigger": "ON_DEMAND",
                "status": "SUCCEEDED",
                "started_at": stamp,
                "finished_at": stamp,
                "items_seen": 0,
                "items_persisted": 0,
                "correlation_id": MIGRATION_RUN_TAG,
                "complete": False,
            }
            for sid, stamp in newest.items()
        ],
    )
    writer.insert(
        "acquisition.raw_item",
        [{**row, "source_run_id": run_ids[str(row["source_definition_id"])]} for row in raw_items],
    )
    kept_raw_ids = {row["id"] for row in raw_items}
    writer.insert(
        "acquisition.raw_item_payload",
        [r for r in tables["acquisition.raw_item_payload"] if r["raw_item_id"] in kept_raw_ids],
        guard=(
            "EXISTS (SELECT 1 FROM acquisition.raw_item r "
            "WHERE r.id = CAST(:raw_item_id AS uuid))"
        ),
    )
    if run_ids:
        connection.execute(
            _text(
                "UPDATE acquisition.source_run s SET items_seen = c.n, items_persisted = c.n "
                "FROM (SELECT source_run_id, count(*) AS n FROM acquisition.raw_item "
                "WHERE source_run_id = ANY(CAST(:runs AS uuid[])) GROUP BY 1) c "
                "WHERE s.id = c.source_run_id"
            ),
            {"runs": list(run_ids.values())},
        )
    notes["job_days"] = job_days
    return dict(notes)


def run_import(
    *,
    database_url: str,
    export_path: Path,
    owner_sub: str,
    apply: bool,
    enable_limit: int = 0,
) -> dict[str, Any]:
    meta, tables = read_export(export_path)
    engine = _engine(database_url)
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
                    enable_limit=enable_limit,
                    job_days=int(meta["job_days"]),
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
        report_tables[table] = {
            "exported": len(tables.get(table, [])),
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


def _sanitized(error: BaseException) -> str:
    """Class name and SQLSTATE only: DB messages can quote row values (e.g. the owner sub)."""
    original = getattr(error, "orig", None) or error
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    return f"{type(error).__name__}" + (f" (SQLSTATE {sqlstate})" if sqlstate else "")


def main(argv: list[str] | None = None) -> int:
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
        "--enable-limit",
        type=int,
        default=0,
        help="enable up to N new sources that were enabled+homologated locally (default 0: "
        "every new source arrives disabled; the owner enables them gradually)",
    )

    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            counts = run_export(
                out=args.out,
                container=args.from_container,
                source_url=os.environ.get("SOURCE_DATABASE_URL"),
                job_days=args.job_days,
            )
            print(json.dumps({"exported": counts, "file": str(args.out)}, indent=2))
            return 0
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise SystemExit("DATABASE_URL is required")
        report = run_import(
            database_url=database_url,
            export_path=args.export_path,
            owner_sub=read_owner_sub(args.owner_sub_file),
            apply=args.apply,
            enable_limit=args.enable_limit,
        )
        print(json.dumps(report, indent=2))
        return 0
    except SystemExit:
        raise
    except Exception as error:
        print(f"error: {_sanitized(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
