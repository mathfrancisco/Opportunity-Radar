"""Measure the precision of the content rules (`seniority-v4`, `work-mode-v7`), read-only.

    # precision per rule on the human-labelled gold set (texts read from the database)
    python scripts/measure_content_classification.py --gold <gold.json> --dry-run
    # no database: use the gold's evidence quote as the text (weak proxy, offline)
    python scripts/measure_content_classification.py --evidence-as-text
    # before/after UNKNOWN rate over the collected jobs that have a description
    python scripts/measure_content_classification.py --acervo-limit 5000
    # exit code 1 unless every rule reaches 90 percent (the activation gate)
    python scripts/measure_content_classification.py --check-gate
    # unlabelled sample for the operator to label (the gold set needs >= 200 jobs)
    python scripts/measure_content_classification.py --sample-out sample.json --sample-size 200

Card F48-15. This script never writes to the database: it only runs `SELECT`s, so "dry-run"
is its only mode (`--dry-run` is accepted to make that explicit). The v4/v7 rules only become
active when `CONTENT_CLASSIFICATION_V4_ENABLED=true`, which must not be set before this
report's gate passes on a gold set of at least 200 human-labelled jobs. Labels are never
generated here: `--sample-out` writes entries with `valor_recomendado: null` for a human.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opportunity_radar.opportunities.content_classification import (
    PRECISION_GATE,
    classify_seniority_v4,
    classify_work_mode_v7,
    gate_passes,
)
from opportunity_radar.opportunities.domain import (
    Seniority,
    WorkMode,
    infer_seniority,
)

DEFAULT_GOLD = Path("docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json")
MEASURED_FIELDS = ("seniority", "work_mode")
DEFAULT_SAMPLE_SIZE = 200
#: SPEC 48 decision 7: no activation on a gold set smaller than this many labelled jobs.
MIN_GOLD_JOBS = 200
EXCERPT_CHARS = 1200


@dataclass(frozen=True, slots=True)
class Case:
    opportunity_id: str
    field: str
    expected: str | None  # `None` = the labeller said "keep UNKNOWN"
    title: str | None
    description: str | None
    location_text: str | None


def load_gold(path: Path) -> list[dict[str, Any]]:
    """Read labelled cases for the fields this script measures (role_family is skipped)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "opportunity_id": item["opportunity_id"],
            "field": item["field"],
            "expected": item.get("valor_recomendado"),
            "title": item.get("title"),
            "evidence": item.get("evidencia"),
        }
        for item in data["casos"]
        if item["field"] in MEASURED_FIELDS
    ]


def build_cases(
    gold: Sequence[Mapping[str, Any]],
    texts: Mapping[str, Mapping[str, Any]],
    *,
    evidence_as_text: bool = False,
) -> list[Case]:
    cases: list[Case] = []
    for item in gold:
        text = texts.get(item["opportunity_id"], {})
        description = text.get("description")
        if description is None and evidence_as_text:
            description = item.get("evidence")
        if description is None:
            continue  # no text to classify: cannot be measured
        cases.append(
            Case(
                opportunity_id=item["opportunity_id"],
                field=item["field"],
                expected=item["expected"],
                title=text.get("title") or item.get("title"),
                description=description,
                location_text=text.get("location_text"),
            )
        )
    return cases


def classify(case: Case) -> tuple[str | None, str | None]:
    """Return `(value, rule)` produced by the v4/v7 rule, or `(None, None)` for UNKNOWN."""
    if case.field == "seniority":
        value, reason = classify_seniority_v4(case.title, case.description, {})
        unknown = value is Seniority.UNKNOWN
    else:
        value, reason = classify_work_mode_v7(case.title, case.location_text, {}, case.description)
        unknown = value is WorkMode.UNKNOWN
    if unknown:
        return None, None
    return value.value, str(reason["rule"])


def measure(cases: Sequence[Case], *, min_gold_jobs: int = MIN_GOLD_JOBS) -> dict[str, Any]:
    emitted: dict[str, list[bool]] = defaultdict(list)
    fields: dict[str, dict[str, int]] = {
        name: {"cases": 0, "unknown_before": 0, "unknown_after": 0} for name in MEASURED_FIELDS
    }
    for case in cases:
        stats = fields[case.field]
        stats["cases"] += 1
        stats["unknown_before"] += 1  # the gold set is drawn from UNKNOWN fields
        value, rule = classify(case)
        if value is None:
            stats["unknown_after"] += 1
            continue
        emitted[f"{case.field}:{rule}"].append(value == case.expected)
    rules = {
        rule: {
            "emitted": len(results),
            "correct": sum(results),
            "precision": round(sum(results) / len(results), 4),
        }
        for rule, results in sorted(emitted.items())
    }
    gold_jobs = len({case.opportunity_id for case in cases})
    passes = gold_jobs >= min_gold_jobs and gate_passes(
        {rule: (r["correct"], r["emitted"]) for rule, r in rules.items()}
    )
    return {
        "rules": rules,
        "fields": fields,
        "gate": {
            "threshold": PRECISION_GATE,
            "min_gold_jobs": min_gold_jobs,
            "gold_jobs": gold_jobs,
            "passes": passes,
        },
    }


def unknown_rates(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """UNKNOWN rate of seniority before (title only, v3) and after (v4), rows with text."""
    counted = [row for row in rows if row.get("description")]
    before = after = 0
    for row in counted:
        if infer_seniority(row.get("title"), None, {}) is Seniority.UNKNOWN:
            before += 1
        value, _ = classify_seniority_v4(row.get("title"), row.get("description"), {})
        if value is Seniority.UNKNOWN:
            after += 1
    total = len(counted)
    return {
        "seniority": {
            "rows": total,
            "unknown_before": before,
            "unknown_after": after,
            "rate_before": round(before / total, 4) if total else 0.0,
            "rate_after": round(after / total, 4) if total else 0.0,
        }
    }


def build_label_sample(
    rows: Sequence[Mapping[str, Any]], *, size: int, seed: int | None
) -> list[dict[str, Any]]:
    """Unlabelled entries for a human: never carries the rule's proposal or any label."""
    pool = [row for row in rows if row.get("description")]
    random.Random(seed).shuffle(pool)
    sample: list[dict[str, Any]] = []
    for row in pool[:size]:
        excerpt = " ".join(str(row["description"]).split())[:EXCERPT_CHARS]
        for field in MEASURED_FIELDS:
            sample.append(
                {
                    "opportunity_id": str(row["opportunity_id"]),
                    "title": row.get("title"),
                    "company": row.get("company"),
                    "location_text": row.get("location_text"),
                    "field": field,
                    "valor_atual": row.get(field),
                    "trecho_descricao": excerpt,
                    "valor_recomendado": None,
                    "recomendacao": None,
                    "evidencia": None,
                }
            )
    return sample


# ------------------------------------------------------------------ database (SELECT only)


def _session() -> Any:
    from sqlalchemy.orm import Session

    from opportunity_radar.platform.database import create_database_engine

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (or use --evidence-as-text).")
    return Session(create_database_engine(database_url))


def _fetch_rows(
    session: Any, *, ids: Sequence[str] | None, limit: int | None
) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from opportunity_radar.opportunities.models import OpportunityModel as M

    query = select(
        M.id,
        M.canonical_title,
        M.company_name,
        M.description,
        M.location_text,
        M.seniority,
        M.work_mode,
    ).where(M.description.is_not(None))
    if ids is not None:
        query = query.where(M.id.in_(list(ids)))
    if limit is not None:
        query = query.limit(limit)
    return [
        {
            "opportunity_id": str(row[0]),
            "title": row[1],
            "company": row[2],
            "description": row[3],
            "location_text": row[4],
            "seniority": row[5],
            "work_mode": row[6],
        }
        for row in session.execute(query).all()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--dry-run", action="store_true", help="accepted; the script is read-only")
    parser.add_argument("--evidence-as-text", action="store_true")
    parser.add_argument("--acervo-limit", type=int, default=None)
    parser.add_argument("--check-gate", action="store_true")
    parser.add_argument("--sample-out", type=Path, default=None)
    parser.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    if args.sample_out is not None:
        with _session() as session:
            rows = _fetch_rows(session, ids=None, limit=None)
        sample = build_label_sample(rows, size=args.sample_size, seed=args.seed)
        args.sample_out.write_text(
            json.dumps({"casos": sample}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{len(sample)} unlabelled entries written to {args.sample_out}", file=sys.stderr)
        return 0

    gold = load_gold(args.gold)
    if args.evidence_as_text:
        texts: dict[str, Mapping[str, Any]] = {}
        mode = "evidence-as-text (proxy, not the real description)"
    else:
        with _session() as session:
            found = _fetch_rows(session, ids=[item["opportunity_id"] for item in gold], limit=None)
        texts = {row["opportunity_id"]: row for row in found}
        mode = "database descriptions"
    report = measure(build_cases(gold, texts, evidence_as_text=args.evidence_as_text))
    report["mode"] = mode
    report["gold_cases"] = len(gold)
    if args.acervo_limit is not None:
        with _session() as session:
            report["acervo"] = unknown_rates(
                _fetch_rows(session, ids=None, limit=args.acervo_limit)
            )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.check_gate and not report["gate"]["passes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
