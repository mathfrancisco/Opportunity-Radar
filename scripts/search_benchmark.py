"""Run a frozen, human-reviewed FTS benchmark; this script never edits ranking or gold."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox  # noqa: E402
from opportunity_radar.dashboard.search_benchmark import (  # noqa: E402
    MIN_COLD_RESTARTS,
    MIN_WARM_REPETITIONS,
    SEARCH_BENCHMARK_VERSION,
    ensure_live_corpus_matches,
    measure_latency_groups,
    paired_report,
    precision_recall_at_k,
    query_category_counts,
    summarize_raw_latencies,
    validate_frozen_manifest,
    validate_restart_project,
)
from opportunity_radar.dashboard.source_baseline import (
    opportunity_search_payload_hash,  # noqa: E402
)
from opportunity_radar.opportunities.models import OpportunityModel  # noqa: E402
from opportunity_radar.platform.database import create_database_engine  # noqa: E402


def _inbox_query(entry: dict[str, object]) -> InboxQuery:
    filters = entry.get("filters", {})
    if not isinstance(filters, dict) or set(filters) - {"allowed_country", "role_families"}:
        raise ValueError("only allowed_country and role_families frozen filters are supported")
    return InboxQuery(
        search=str(entry["query"]),
        allowed_country=filters.get("allowed_country"),
        role_families=tuple(filters.get("role_families", ())),
        limit=20,
        offset=0,
    )


def evaluate(
    session: Session,
    manifest: dict[str, object],
    *,
    warm_repetitions: int = MIN_WARM_REPETITIONS,
    cold_restarts: int = 0,
    restart: Callable[[], None] | None = None,
    restart_method: str | None = None,
    run_cold: Callable[[str], object] | None = None,
    parser_version: str | None = None,
) -> dict[str, Any]:
    hashes = validate_frozen_manifest(manifest)
    live_rows = session.execute(
        select(
            OpportunityModel.id,
            OpportunityModel.canonical_title,
            OpportunityModel.company_name,
            OpportunityModel.search_skills,
            OpportunityModel.role_family,
            OpportunityModel.description,
            OpportunityModel.location_text,
            OpportunityModel.search_document,
        ).order_by(OpportunityModel.id)
    ).all()
    live_corpus = [
        {
            "opportunity_id": str(row.id),
            "payload_hash": opportunity_search_payload_hash(
                {
                    "canonical_title": row.canonical_title,
                    "company_name": row.company_name,
                    "search_skills": row.search_skills,
                    "role_family": row.role_family,
                    "description": row.description,
                    "location_text": row.location_text,
                    "search_document": str(row.search_document)
                    if row.search_document is not None
                    else None,
                }
            ),
        }
        for row in live_rows
    ]
    ensure_live_corpus_matches(manifest["corpus"], live_corpus)  # type: ignore[arg-type]
    gold_by_query: dict[str, set[str]] = {}
    for row in manifest["gold"]:  # type: ignore[index, attr-defined]
        if row.get("eligible") is not True:
            continue
        if row.get("human_label") not in {"relevant", "not_relevant"}:
            raise ValueError("every gold row needs a human relevance label")
        if row.get("eligible") is True and row.get("human_label") == "relevant":
            gold_by_query.setdefault(row["query"], set()).add(str(UUID(row["opportunity_id"])))
    per_query = []
    entries = {str(entry["query"]): entry for entry in manifest["queries"]}  # type: ignore[attr-defined, index]
    for entry in manifest["queries"]:  # type: ignore[index, attr-defined]
        query = _inbox_query(entry)
        page = list_opportunity_inbox(session, query)
        ranked = [str(item.opportunity_id) for item in page.items]
        relevant = gold_by_query.get(entry["query"], set())
        per_query.append(
            {
                "query": entry["query"],
                "category": entry["category"],
                "filters": entry.get("filters", {}),
                "gold_relevant": len(relevant),
                "returned": len(ranked),
                "metrics": {
                    f"at_{k}": precision_recall_at_k(ranked, relevant, k=k) for k in (10, 20)
                },
            }
        )
    # Read before the cold group: a restart ends this transaction.
    database_snapshot = session.execute(text("SELECT txid_current_snapshot()::text")).scalar_one()
    environment: dict[str, object] = {
        "server_version": session.execute(text("SHOW server_version")).scalar_one(),
        "shared_buffers": session.execute(text("SHOW shared_buffers")).scalar_one(),
        "cold_reset": "postgres service restart: shared_buffers emptied, OS page cache kept",
    }
    groups = measure_latency_groups(
        list(entries),
        lambda text_: list_opportunity_inbox(session, _inbox_query(entries[text_])),
        warm_repetitions=warm_repetitions,
        cold_restarts=cold_restarts,
        restart=restart,
        restart_method=restart_method,
        run_cold=run_cold,
        environment=environment,
    )
    for row in per_query:
        row["warm_latency_ms"] = groups["warm"]["raw_ms"][row["query"]]
        row["cold_latency_ms"] = groups["cold"]["raw_ms"][row["query"]]
    pooled_warm = [ms for values in groups["warm"]["raw_ms"].values() for ms in values]
    pooled_cold = [ms for values in groups["cold"]["raw_ms"].values() for ms in values]
    return {
        "version": SEARCH_BENCHMARK_VERSION,
        "collector_version": "search-benchmark-collector-v1",
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "frozen_manifest_captured_at": manifest["captured_at"],
        "snapshot_provenance": {
            "database_snapshot": database_snapshot,
            "isolation": "REPEATABLE READ READ ONLY",
        },
        "index_config": manifest["index_config"],
        "reviewers": manifest["reviewers"],
        "hashes": hashes,
        "category_counts": query_category_counts(manifest["queries"]),  # type: ignore[arg-type]
        "latency": summarize_raw_latencies(
            pooled_warm, pooled_cold, cold_cache_evidence=groups["cold"]["evidence"]
        ),
        "latency_groups": groups,
        "parser_version": parser_version,
        "per_query": per_query,
    }


def compose_restart(project: str, engine: Engine, *, wait_seconds: float = 90.0) -> None:
    """Restart the `postgres` service of a disposable Compose project and wait for it."""
    name = validate_restart_project(project)
    subprocess.run(
        ["docker", "compose", "-p", name, "restart", "postgres"],
        check=True,
        timeout=wait_seconds,
        capture_output=True,
    )
    engine.dispose()  # every pooled connection died with the server
    deadline = monotonic() + wait_seconds
    while True:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except OperationalError:
            engine.dispose()
            if monotonic() > deadline:
                raise
            sleep(1)


def _write_report(report: dict[str, object], output: Path | None) -> None:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n")
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, help="new report path; never overwritten")
    parser.add_argument(
        "--compare",
        nargs=2,
        type=Path,
        metavar=("REPORT_A", "REPORT_B"),
        help="paired A/B comparison of two reports from this script; needs no database",
    )
    parser.add_argument("--parser-version", help="parser/transformation of this snapshot")
    parser.add_argument("--warm-repetitions", type=int, default=MIN_WARM_REPETITIONS)
    parser.add_argument(
        "--restart-postgres-of-compose-project",
        metavar="PROJECT",
        help="opt-in cold group: restart the postgres service of this DISPOSABLE Compose "
        "project before each cold sample (never opportunity-radar-dev, opportunity-radar "
        "or orf51terra); needs the docker CLI",
    )
    parser.add_argument("--cold-restarts", type=int, default=MIN_COLD_RESTARTS)
    args = parser.parse_args()
    if args.compare:
        try:
            reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.compare]
            _write_report(paired_report(*reports), args.output)
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            parser.error(str(exc))
        return 0
    if args.manifest is None:
        parser.error("--manifest is required")
    if args.warm_repetitions < MIN_WARM_REPETITIONS:
        parser.error(f"--warm-repetitions must be at least {MIN_WARM_REPETITIONS}")
    project = args.restart_postgres_of_compose_project
    if project is not None:
        try:
            validate_restart_project(project)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        with args.manifest.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        validate_frozen_manifest(manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    engine = create_database_engine(database_url)
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        options: dict[str, Any] = {}
        if project is not None:
            entries = {str(entry["query"]): entry for entry in manifest["queries"]}

            def restart() -> None:
                session.rollback()  # hand the connection back before the server goes down
                compose_restart(project, engine)

            def run_cold(query_text: str) -> None:
                with Session(engine) as fresh:
                    fresh.execute(
                        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                    )
                    list_opportunity_inbox(fresh, _inbox_query(entries[query_text]))

            options = {
                "cold_restarts": args.cold_restarts,
                "restart": restart,
                "restart_method": f"docker compose -p {project} restart postgres",
                "run_cold": run_cold,
            }
        report = evaluate(
            session,
            manifest,
            warm_repetitions=args.warm_repetitions,
            parser_version=args.parser_version,
            **options,
        )
    _write_report(report, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
