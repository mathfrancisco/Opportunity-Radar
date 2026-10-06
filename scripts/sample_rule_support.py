"""Draw an unlabelled sample among the jobs where each description rule emits, read-only.

    # database (DATABASE_URL), summary on stderr, sample on --out
    python scripts/sample_rule_support.py --seed 20261006 --out sample.json \
        --exclude-gold docs/50-roadmap-motor-de-busca/rotulagem/f50-01-amostra-para-rotular.json
    # offline: the rows exported with `psql \\copy ... to stdout with csv header`
    python scripts/sample_rule_support.py --seed 20261006 --rows-csv rows.csv --out sample.json

Card F51-11. The F50-01 sample was drawn without looking at the rules, and its 1,200-character
excerpts almost never reach the part of the description where a rule emits, so each rule got
0 to 8 emissions against a gate of 20. This script draws, for each rule the gate covers
(`DESCRIPTION_RULES`), up to `--per-rule` jobs on which that rule emits, at random with the
given seed, skipping jobs already in the `--exclude-gold` files. A rule that emits on fewer jobs
takes all of them, and the count is reported: a rule that cannot reach
`GATED_RULE_MIN_EMISSIONS` emissions cannot pass.

"Emits" is what `scripts/measure_content_classification.py` calls emitting: the same `classify`
over the job's title, location and whole description. Each entry carries the whole description
and no label: `judgment`, `valor_recomendado`, `evidencia` and `revisado_por` are null, so the
gold reader ignores it until a person signs. This script never writes to the database.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

try:  # imported as a package (tests) or run as `python scripts/sample_rule_support.py`
    from scripts.measure_content_classification import MEASURED_FIELDS, Case, classify
except ImportError:  # pragma: no cover - depends on how the script is launched
    from measure_content_classification import MEASURED_FIELDS, Case, classify

from opportunity_radar.opportunities.content_classification import DESCRIPTION_RULES

DEFAULT_PER_RULE = 40
DEFAULT_SEED = 20261006
UNKNOWN_SOURCE_TYPE = "unknown"
_ROW_COLUMNS = (
    "opportunity_id",
    "title",
    "company",
    "description",
    "location_text",
    "seniority",
    "work_mode",
    "allowed_countries",
    "source_type",
)


def find_emissions(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, list[tuple[Mapping[str, Any], str]]]:
    """`rule -> [(row, emitted value)]` for the rules of `DESCRIPTION_RULES` only.

    Rows without a description cannot emit a description rule and are skipped.
    """
    found: dict[str, list[tuple[Mapping[str, Any], str]]] = {rule: [] for rule in DESCRIPTION_RULES}
    for row in rows:
        if not row.get("description"):
            continue
        for field in MEASURED_FIELDS:
            case = Case(
                opportunity_id=str(row["opportunity_id"]),
                field=field,
                expected=None,
                title=row.get("title"),
                description=row["description"],
                location_text=row.get("location_text"),
                source_type=row.get("source_type"),
            )
            value, rule = classify(case)
            key = f"{field}:{rule}"
            if value is not None and key in found:
                found[key].append((row, value))
    return found


def select_per_rule(
    emissions: Mapping[str, Sequence[tuple[Mapping[str, Any], str]]],
    *,
    exclude_ids: Collection[str] = frozenset(),
    per_rule: int = DEFAULT_PER_RULE,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[tuple[Mapping[str, Any], str]]]:
    """Up to `per_rule` emissions per rule, excluding `exclude_ids`, reproducible from `seed`.

    The candidates are ordered by job id before the draw, so the result does not depend on the
    order of the input. Each rule draws from its own generator (`seed` and the rule name), so
    adding or removing a rule does not move the others' draws.
    """
    chosen: dict[str, list[tuple[Mapping[str, Any], str]]] = {}
    for rule in sorted(emissions):
        pool = sorted(
            (item for item in emissions[rule] if str(item[0]["opportunity_id"]) not in exclude_ids),
            key=lambda item: str(item[0]["opportunity_id"]),
        )
        if len(pool) > per_rule:
            pool = random.Random(f"{seed}:{rule}").sample(pool, per_rule)
        chosen[rule] = pool
    return chosen


def build_entries(
    chosen: Mapping[str, Sequence[tuple[Mapping[str, Any], str]]],
) -> list[dict[str, Any]]:
    """One entry per selected job and rule, in the gold schema, with the whole description."""
    entries: list[dict[str, Any]] = []
    for rule in sorted(chosen):
        field, _, short = rule.partition(":")
        for row, value in chosen[rule]:
            entries.append(
                {
                    "opportunity_id": str(row["opportunity_id"]),
                    "field": field,
                    "title": row.get("title"),
                    "company": row.get("company"),
                    "location_text": row.get("location_text"),
                    "source_type": row.get("source_type"),
                    "valor_atual": row.get(field),
                    "trecho_descricao": row["description"],
                    "regra": short,
                    "regra_selecao": rule,
                    "regra_valor": value,
                    "judgment": None,
                    "valor_recomendado": None,
                    "recomendacao": None,
                    "evidencia": None,
                    "revisado_por": None,
                }
            )
    return entries


def summarize(
    emissions: Mapping[str, Sequence[tuple[Mapping[str, Any], str]]],
    chosen: Mapping[str, Sequence[tuple[Mapping[str, Any], str]]],
    *,
    exclude_ids: Collection[str],
    min_support: int,
    catalogue_source_types: Collection[str] = (),
) -> dict[str, Any]:
    """Counts per rule and per source type; source types under `min_support` jobs are listed."""
    per_rule = {}
    for rule in sorted(emissions):
        available = [
            item for item in emissions[rule] if str(item[0]["opportunity_id"]) not in exclude_ids
        ]
        per_rule[rule] = {
            "emissions_in_catalogue": len(emissions[rule]),
            "emissions_in_existing_gold": len(emissions[rule]) - len(available),
            "emissions_available": len(available),
            "sampled": len(chosen.get(rule, ())),
            "can_reach_gate_minimum": len(emissions[rule]) >= min_support,
        }
    jobs: dict[str, str] = {}
    for items in chosen.values():
        for row, _ in items:
            jobs[str(row["opportunity_id"])] = row.get("source_type") or UNKNOWN_SOURCE_TYPE
    by_source = Counter(jobs.values())
    by_rule_source = {
        rule: dict(Counter((row.get("source_type") or UNKNOWN_SOURCE_TYPE) for row, _ in items))
        for rule, items in sorted(chosen.items())
    }
    return {
        "per_rule": per_rule,
        "distinct_jobs": len(jobs),
        "by_source_type": dict(sorted(by_source.items())),
        "by_rule_and_source_type": by_rule_source,
        "source_types_under_minimum": sorted(
            t for t in {*by_source, *catalogue_source_types} if by_source.get(t, 0) < min_support
        ),
        "minimum": min_support,
    }


def load_excluded_ids(paths: Iterable[Path]) -> set[str]:
    """Job ids in the `casos` of gold, sample or proposal files; the files are only read."""
    ids: set[str] = set()
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        ids.update(str(item["opportunity_id"]) for item in data["casos"])
    return ids


def read_rows_csv(path: Path) -> list[dict[str, Any]]:
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)  # header
        return [
            {key: (value or None) for key, value in zip(_ROW_COLUMNS, record, strict=True)}
            for record in reader
        ]


def _database_rows() -> list[dict[str, Any]]:
    import os

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from opportunity_radar.platform.database import create_database_engine

    try:
        from scripts.measure_content_classification import _fetch_rows
    except ImportError:  # pragma: no cover
        from measure_content_classification import _fetch_rows

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (or pass --rows-csv).")
    with Session(create_database_engine(database_url)) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        return _fetch_rows(session, ids=None, limit=None)


def main(argv: Sequence[str] | None = None) -> int:
    from opportunity_radar.opportunities.content_classification import GATED_RULE_MIN_EMISSIONS

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--per-rule", type=int, default=DEFAULT_PER_RULE)
    parser.add_argument("--exclude-gold", type=Path, action="append", default=[])
    parser.add_argument("--rows-csv", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="sample file; omit for a dry count")
    parser.add_argument("--summary-out", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="accepted; the script is read-only")
    args = parser.parse_args(argv)

    rows = read_rows_csv(args.rows_csv) if args.rows_csv else _database_rows()
    exclude = load_excluded_ids(args.exclude_gold)
    emissions = find_emissions(rows)
    chosen = select_per_rule(emissions, exclude_ids=exclude, per_rule=args.per_rule, seed=args.seed)
    summary = summarize(
        emissions,
        chosen,
        exclude_ids=exclude,
        min_support=GATED_RULE_MIN_EMISSIONS,
        catalogue_source_types={r.get("source_type") or UNKNOWN_SOURCE_TYPE for r in rows},
    )
    summary["catalogue_jobs_with_description_by_source_type"] = dict(
        sorted(Counter(r.get("source_type") or UNKNOWN_SOURCE_TYPE for r in rows).items())
    )
    summary |= {"seed": args.seed, "per_rule_cap": args.per_rule, "rows_read": len(rows)}
    report = json.dumps(summary, ensure_ascii=False, indent=2)
    print(report, file=sys.stderr)
    if args.summary_out is not None:
        args.summary_out.write_text(report, encoding="utf-8")
    if args.out is not None:
        entries = build_entries(chosen)
        args.out.write_text(
            json.dumps(
                {
                    "card": "F51-11",
                    "semente": args.seed,
                    "por_regra": args.per_rule,
                    "excluidos_de": [str(path) for path in args.exclude_gold],
                    "aviso": "Amostra sem rotulo: nenhum caso vale ate o dono assinar.",
                    "casos": entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{len(entries)} unlabelled entries written to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
