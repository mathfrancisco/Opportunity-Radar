"""Evaluate the Inbox search against the frozen reference set (`search_reference.py`).

    python scripts/eval_search.py --mode fulltext
    python scripts/eval_search.py --mode like
    python scripts/eval_search.py --mode both

Card F17-03. Reports recall@10 and nDCG@10 per query and averaged, for the queries whose
relevant set is non-empty (an empty relevant set has no ceiling to measure against — SPEC
37 §3.1). `--mode both` prints both reports side by side so the gate ("recall@10 do
full-text > recall@10 do LIKE") can be read directly, and this is what the card's PR
attaches. `--mode like` reproduces the pre-F17-03 baseline (title/company `LIKE`, no
ranking) without depending on the removed production code path, purely for the
comparison; it is not live behavior.

Shared with F16-10 (search by meaning), which will add its own `--mode semantic`.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

# `python scripts/eval_search.py` puts this file's own directory on sys.path, not the
# repo root, so `scripts.search_reference` would not resolve without this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox  # noqa: E402
from opportunity_radar.opportunities.models import OpportunityModel  # noqa: E402
from opportunity_radar.platform.database import create_database_engine  # noqa: E402
from scripts.search_reference import DEFAULT_PATH, resolve  # noqa: E402

K = 10


def _like_ranked_ids(session: Session, query: str, limit: int = K) -> list[UUID]:
    """The search behavior F17-03 replaces: `LIKE` on title/company, no ranking."""
    pattern = f"%{query.strip().lower()}%"
    rows = session.execute(
        select(OpportunityModel.id, OpportunityModel.published_at)
        .where(
            func.lower(OpportunityModel.canonical_title).like(pattern)
            | func.lower(func.coalesce(OpportunityModel.company_name, "")).like(pattern)
        )
        .order_by(OpportunityModel.published_at.desc().nulls_last(), OpportunityModel.id)
        .limit(limit)
    ).all()
    return [row[0] for row in rows]


def _fulltext_ranked_ids(session: Session, query: str, limit: int = K) -> list[UUID]:
    page = list_opportunity_inbox(
        session, InboxQuery(search=query, limit=limit, offset=0)
    )
    return [item.opportunity_id for item in page.items]


def _recall_at_k(ranked: list[UUID], relevant: set[UUID]) -> float | None:
    if not relevant:
        return None
    hits = len({item for item in ranked[:K] if item in relevant})
    return hits / len(relevant)


def _ndcg_at_k(ranked: list[UUID], relevant: set[UUID]) -> float | None:
    if not relevant:
        return None
    dcg = sum(
        1.0 / math.log2(position + 2)
        for position, item in enumerate(ranked[:K])
        if item in relevant
    )
    ideal_hits = min(len(relevant), K)
    idcg = sum(1.0 / math.log2(position + 2) for position in range(ideal_hits))
    return dcg / idcg if idcg else None


def evaluate(session: Session, mode: str, path: Path) -> dict[str, object]:
    ranker = _fulltext_ranked_ids if mode == "fulltext" else _like_ranked_ids
    per_query: list[dict[str, object]] = []
    for entry in resolve(session, path):
        query = str(entry["query"])
        relevant = {UUID(item["opportunity_id"]) for item in entry["relevant"]}  # type: ignore[index]
        if not query or not relevant:
            continue
        ranked = ranker(session, query)
        recall = _recall_at_k(ranked, relevant)
        ndcg = _ndcg_at_k(ranked, relevant)
        per_query.append(
            {
                "query": query,
                "relevant_count": len(relevant),
                "recall_at_10": recall,
                "ndcg_at_10": ndcg,
            }
        )
    measured = [row for row in per_query if row["recall_at_10"] is not None]
    average_recall = (
        sum(row["recall_at_10"] for row in measured) / len(measured) if measured else None
    )
    average_ndcg = (
        sum(row["ndcg_at_10"] for row in measured) / len(measured) if measured else None
    )
    return {
        "mode": mode,
        "queries_measured": len(measured),
        "average_recall_at_10": average_recall,
        "average_ndcg_at_10": average_ndcg,
        "per_query": per_query,
    }


def _print_report(report: dict[str, object]) -> None:
    print(f"mode={report['mode']} queries_measured={report['queries_measured']}")
    print(f"  average recall@10 = {report['average_recall_at_10']}")
    print(f"  average nDCG@10    = {report['average_ndcg_at_10']}")
    for row in report["per_query"]:  # type: ignore[union-attr]
        print(
            f"  - {row['query']!r}: relevant={row['relevant_count']} "
            f"recall@10={row['recall_at_10']} nDCG@10={row['ndcg_at_10']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("like", "fulltext", "both"), default="fulltext")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    modes = ["like", "fulltext"] if args.mode == "both" else [args.mode]
    with Session(create_database_engine(database_url)) as session:
        for mode in modes:
            _print_report(evaluate(session, mode, args.path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
