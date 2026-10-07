"""Sample the normalization `REVIEW_REQUIRED` queue and resolve its one safe pattern.

    python scripts/resolve_review_queue.py                    # counts per reason and pattern
    python scripts/resolve_review_queue.py --sample 50 --seed 1 --json
    python scripts/resolve_review_queue.py --apply            # resolve the safe pattern

Owner decision of 2026-10-06 (SPEC 52 §5): sample 50 of each reason, resolve in bulk only
"same source, different `external_id` and different location or work mode", and merge
nothing automatically.

The safe pattern applies to `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY`: the normalizer
parked a new opportunity because the same company already had one with the same title. When
every candidate it names sits in the same source under another `external_id`, and differs in
location or work mode, the board lists them as separate postings (one per city or per mode),
so they are separate opportunities. `--apply` marks those rows `SUCCEEDED` / `NEW` and adds a
`REVIEW_RESOLVED_DISTINCT_POSTING` reason; the original reason stays. No opportunity,
occurrence or duplicate link is touched. A side whose location is unknown never counts as a
different location, and `UNKNOWN` never counts as a different work mode.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine

DEFAULT_SAMPLE_SIZE = 50
RESOLVED_CODE = "REVIEW_RESOLVED_DISTINCT_POSTING"
RESOLVED_RULE = "same_source_different_external_id_and_location_or_mode"
SAME_TITLE_CODE = "SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY"
#: Reason codes that describe the row but never park it by themselves.
_INFORMATIONAL = frozenset({"SENIORITY_CLASSIFICATION"})

_ROWS = text(
    """
    SELECT n.id, n.reasons, n.identity_decision, o.id AS opportunity_id,
           o.canonical_title, o.company_name, o.normalized_location, o.work_mode,
           so.source_definition_id, so.external_id, sd.source_type
    FROM opportunities.normalization_result n
    JOIN opportunities.opportunity o ON o.id = n.opportunity_id
    JOIN opportunities.source_occurrence so ON so.id = n.source_occurrence_id
    JOIN acquisition.source_definition sd ON sd.id = so.source_definition_id
    WHERE n.status = 'REVIEW_REQUIRED'
    ORDER BY n.id
    """
)
_CANDIDATES = text(
    """
    SELECT o.id, o.normalized_location, o.work_mode,
           array_agg(so.external_id) FILTER (WHERE so.source_definition_id = :source)
               AS external_ids
    FROM opportunities.opportunity o
    LEFT JOIN opportunities.source_occurrence so ON so.opportunity_id = o.id
    WHERE o.id = ANY(:ids)
    GROUP BY o.id
    """
)
_RESOLVE = text(
    """
    UPDATE opportunities.normalization_result
    SET status = 'SUCCEEDED', identity_decision = 'NEW',
        reasons = reasons || CAST(:reason AS jsonb)
    WHERE id = :id AND status = 'REVIEW_REQUIRED'
    """
)


def review_reason(reasons: list[dict[str, Any]]) -> str:
    """The reason code a row is grouped under: its first one that is not informational."""
    for reason in reasons:
        code = reason.get("code")
        if isinstance(code, str) and code not in _INFORMATIONAL:
            return code
    return "NO_REVIEW_REASON"


def differs(row: dict[str, Any], candidate: dict[str, Any]) -> bool:
    """Known and different location, or known and different work mode."""
    location, other = row["normalized_location"], candidate["normalized_location"]
    if location and other and location != other:
        return True
    mode, other_mode = row["work_mode"], candidate["work_mode"]
    return "UNKNOWN" not in (mode, other_mode) and bool(mode and other_mode) and mode != other_mode


def is_distinct_posting(row: dict[str, Any], candidates: list[dict[str, Any] | None]) -> bool:
    """The safe pattern: every candidate is another posting of the same source that differs."""
    if not candidates:
        return False
    for candidate in candidates:
        if candidate is None:
            return False
        external_ids = candidate["external_ids"] or []
        if not external_ids or row["external_id"] in external_ids:
            return False
        if not differs(row, candidate):
            return False
    return True


def load(session: Session) -> list[dict[str, Any]]:
    rows = [dict(row) for row in session.execute(_ROWS).mappings()]
    for row in rows:
        row["reason"] = review_reason(row["reasons"])
        ids = [
            candidate
            for reason in row["reasons"]
            if reason.get("code") == SAME_TITLE_CODE
            for candidate in reason.get("candidate_opportunity_ids", [])
        ]
        found = {
            str(candidate["id"]): dict(candidate)
            for candidate in session.execute(
                _CANDIDATES, {"ids": ids, "source": row["source_definition_id"]}
            ).mappings()
        } if ids else {}
        row["candidates"] = [found.get(candidate) for candidate in ids]
        row["distinct_posting"] = row["reason"] == SAME_TITLE_CODE and is_distinct_posting(
            row, row["candidates"]
        )
    return rows


def summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = counts.setdefault(row["reason"], {"rows": 0, "distinct_posting": 0})
        entry["rows"] += 1
        entry["distinct_posting"] += row["distinct_posting"]
    return dict(sorted(counts.items()))


def sample(rows: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    """Up to `size` rows of each reason, drawn with a fixed seed over a stable order."""
    by_reason: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_reason.setdefault(row["reason"], []).append(row)
    drawn: list[dict[str, Any]] = []
    for reason in sorted(by_reason):
        group = by_reason[reason]
        picked = random.Random(f"{seed}:{reason}").sample(group, min(size, len(group)))
        drawn.extend(_public(row) for row in picked)
    return drawn


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "normalization_result_id": str(row["id"]),
        "reason": row["reason"],
        "source_type": row["source_type"],
        "opportunity_id": str(row["opportunity_id"]),
        "title": row["canonical_title"],
        "company": row["company_name"],
        "location": row["normalized_location"],
        "work_mode": row["work_mode"],
        "external_id": row["external_id"],
        "candidates": [
            None
            if candidate is None
            else {
                "opportunity_id": str(candidate["id"]),
                "location": candidate["normalized_location"],
                "work_mode": candidate["work_mode"],
                "external_ids_in_same_source": candidate["external_ids"] or [],
            }
            for candidate in row["candidates"]
        ],
        "distinct_posting": row["distinct_posting"],
    }


def apply(session: Session, rows: list[dict[str, Any]], *, now: datetime) -> int:
    reason = json.dumps(
        [{"code": RESOLVED_CODE, "rule": RESOLVED_RULE, "resolved_at": now.isoformat()}]
    )
    resolved = 0
    for row in rows:
        if row["distinct_posting"]:
            resolved += session.execute(_RESOLVE, {"id": row["id"], "reason": reason}).rowcount
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=0, help="rows per reason to print")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--apply", action="store_true", help="resolve the safe pattern")
    arguments = parser.parse_args()

    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        rows = load(session)
        report: dict[str, Any] = {"total": len(rows), "by_reason": summary(rows)}
        if arguments.sample:
            report["sample"] = sample(rows, arguments.sample, arguments.seed)
        if arguments.apply:
            report["resolved"] = apply(session, rows, now=datetime.now(UTC))
            session.commit()
    if arguments.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(f"REVIEW_REQUIRED: {report['total']}")
    for reason, entry in report["by_reason"].items():
        print(f"  {reason}: {entry['rows']} (distinct posting: {entry['distinct_posting']})")
    if "resolved" in report:
        print(f"resolved: {report['resolved']}")


if __name__ == "__main__":
    main()
