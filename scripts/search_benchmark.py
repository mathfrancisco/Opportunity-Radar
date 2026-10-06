"""Run a frozen, human-reviewed FTS benchmark; this script never edits ranking or gold."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox  # noqa: E402
from opportunity_radar.dashboard.search_benchmark import (  # noqa: E402
    SEARCH_BENCHMARK_VERSION,
    ensure_live_corpus_matches,
    precision_recall_at_k,
    query_category_counts,
    summarize_raw_latencies,
    validate_frozen_manifest,
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


def evaluate(session: Session, manifest: dict[str, object]) -> dict[str, object]:
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
    warm_latencies_ms: list[float] = []
    for entry in manifest["queries"]:  # type: ignore[index, attr-defined]
        query = _inbox_query(entry)
        page = list_opportunity_inbox(session, query)
        ranked = [str(item.opportunity_id) for item in page.items]
        relevant = gold_by_query.get(entry["query"], set())
        query_warm_ms: list[float] = []
        for _ in range(10):
            started = perf_counter()
            list_opportunity_inbox(session, query)
            query_warm_ms.append((perf_counter() - started) * 1000)
        warm_latencies_ms.extend(query_warm_ms)
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
                "warm_latency_ms": query_warm_ms,
            }
        )
    return {
        "version": SEARCH_BENCHMARK_VERSION,
        "collector_version": "search-benchmark-collector-v1",
        "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "frozen_manifest_captured_at": manifest["captured_at"],
        "snapshot_provenance": {
            "database_snapshot": session.execute(
                text("SELECT txid_current_snapshot()::text")
            ).scalar_one(),
            "isolation": "REPEATABLE READ READ ONLY",
        },
        "index_config": manifest["index_config"],
        "reviewers": manifest["reviewers"],
        "hashes": hashes,
        "category_counts": query_category_counts(manifest["queries"]),  # type: ignore[arg-type]
        "latency": summarize_raw_latencies(warm_latencies_ms),
        "per_query": per_query,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="new report path; never overwritten")
    args = parser.parse_args()
    try:
        with args.manifest.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        validate_frozen_manifest(manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    with Session(create_database_engine(database_url)) as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        report = evaluate(session, manifest)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
