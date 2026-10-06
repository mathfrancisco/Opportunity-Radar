"""Measure the title-only seniority classifier over the target areas, read-only.

    # baseline: level counts and the UNKNOWN titles grouped by pattern (reads the database)
    python scripts/measure_seniority_titles.py
    # blind sample for the owner to label: 200 UNKNOWN and 100 classified titles
    python scripts/measure_seniority_titles.py --sample-out sample.json --seed 52
    # no database: precision per level on the labelled sample
    python scripts/measure_seniority_titles.py --sample <sample.json>

Card F52-01. This script never writes to the database: it only runs `SELECT`s. Labels are
never generated here: `--sample-out` writes every entry with `nivel_rotulado: null`, without
the classifier's answer and in shuffled order, so the label is not anchored on it.

A label is a `Seniority` value, `"UNKNOWN"` when the title does not state a level, or a list
of values when the title states a range (`Pl/Sr`). An emitted level counts as correct when it
is one of the labelled values.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from opportunity_radar.opportunities.domain import (
    SENIORITY_MAPPING_VERSION,
    Seniority,
    infer_seniority,
)

DEFAULT_AREAS = ("SOFTWARE_ENGINEERING", "DATA")
UNKNOWN_SAMPLE_SIZE = 200
CLASSIFIED_SAMPLE_SIZE = 100
EXAMPLES_PER_PATTERN = 8
PATTERNS = ("accent", "two_levels", "numeral", "uncovered_word", "no_signal")

# Diagnostic vocabulary, matched on the accent-stripped, case-folded title. It mirrors the
# level words of `infer_seniority` so a title that names two levels can be told apart from
# one that names none; it never classifies anything.
_LEVEL_WORDS: dict[str, str] = {
    "INTERN": (
        r"\b(?:intern(?:ship)?|estagi(?:o|a|ari[oa]s?)|trainee|entry[ -]level"
        r"|new grad(?:uate)?|apprentice|aprendiz)\b"
    ),
    "JUNIOR": r"\b(?:junior|jr|early career)\b",
    "MID": r"\b(?:mid(?:[- ]level)?|middle|pleno|pl)\b",
    "SENIOR": r"\b(?:senior|sr)\b",
    "STAFF": r"\b(?:staff|especialista|principal)\b",
    "LEAD": r"\b(?:lead|lider)\b",
    "MANAGER": r"\b(?:manager|gerente)\b",
    "DIRECTOR": r"\b(?:director|diretor)\b",
}
# A level numeral: `II`/`III`/`IV` anywhere, or `I`/`V`/1-5 right after a role noun
# (`Software Engineer I`, `Analyst 3`). A bare digit elsewhere is usually a requisition id.
_NUMERAL = (
    r"\b(?:ii|iii|iv)\b"
    r"|\b(?:engineer|developer|analyst|scientist|architect|programmer|consultant|sde|swe"
    r"|desenvolvedor(?:a)?|engenheir[oa]|analista)\s+(?:i|v|[1-5])\b"
)
# Words that state a level and that the classifier does not read.
_UNCOVERED_WORDS = (
    r"\b(architect|arquitet[oa]|head of|associate|new college grad|founding|specialist"
    r"|expert|distinguished|fellow|vp|vice president|chief|cto|coordenador(?:a)?"
    r"|supervisor|phd|university|campus|student|analista)\b"
)


def strip_accents(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )


def classify(title: str | None) -> str:
    return infer_seniority(title, None, {}).value


def named_levels(title: str) -> list[str]:
    folded = strip_accents(title).casefold()
    return [level for level, pattern in _LEVEL_WORDS.items() if re.search(pattern, folded)]


def unknown_pattern(title: str) -> tuple[str, str | None]:
    """Why a title is `UNKNOWN`: `(pattern, detail)`, the first pattern that applies."""
    folded = strip_accents(title).casefold()
    if classify(strip_accents(title)) != Seniority.UNKNOWN.value:
        return "accent", None
    levels = named_levels(title)
    if len(levels) >= 2:
        return "two_levels", "+".join(levels)
    if re.search(_NUMERAL, folded):
        return "numeral", None
    word = re.search(_UNCOVERED_WORDS, folded)
    if word:
        return "uncovered_word", word.group(1)
    return "no_signal", None


def baseline(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Level counts, coverage and the `UNKNOWN` titles grouped by pattern."""
    levels: Counter[str] = Counter()
    patterns: Counter[str] = Counter()
    details: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        title = row.get("title") or ""
        level = classify(title)
        levels[level] += 1
        if level != Seniority.UNKNOWN.value:
            continue
        pattern, detail = unknown_pattern(title)
        patterns[pattern] += 1
        if detail is not None:
            details[pattern][detail] += 1
        if len(examples[pattern]) < EXAMPLES_PER_PATTERN:
            examples[pattern].append(title)
    total = len(rows)
    unknown = levels[Seniority.UNKNOWN.value]
    return {
        "mapping_version": SENIORITY_MAPPING_VERSION,
        "titles": total,
        "levels": dict(sorted(levels.items())),
        "coverage": round((total - unknown) / total, 4) if total else 0.0,
        # Coverage if every `UNKNOWN` title that names a level were classified.
        "coverage_ceiling_title_only": (
            round((total - patterns["no_signal"]) / total, 4) if total else 0.0
        ),
        "unknown": unknown,
        "unknown_patterns": {
            name: {
                "titles": patterns[name],
                "share_of_unknown": round(patterns[name] / unknown, 4) if unknown else 0.0,
                "details": dict(details[name].most_common()),
                "examples": examples[name],
            }
            for name in PATTERNS
        },
    }


def build_label_sample(
    rows: Sequence[Mapping[str, Any]],
    *,
    unknown_size: int = UNKNOWN_SAMPLE_SIZE,
    classified_size: int = CLASSIFIED_SAMPLE_SIZE,
    seed: int | None,
) -> list[dict[str, Any]]:
    """Blind, shuffled entries for a human; one entry per distinct title."""
    rng = random.Random(seed)
    distinct = list({str(row.get("title") or ""): row for row in rows if row.get("title")}.values())
    distinct.sort(key=lambda row: str(row["opportunity_id"]))
    rng.shuffle(distinct)
    unknown = [row for row in distinct if classify(row["title"]) == Seniority.UNKNOWN.value]
    classified = [row for row in distinct if classify(row["title"]) != Seniority.UNKNOWN.value]
    chosen = unknown[:unknown_size] + classified[:classified_size]
    rng.shuffle(chosen)
    return [
        {
            "opportunity_id": str(row["opportunity_id"]),
            "title": row["title"],
            "company": row.get("company"),
            "nivel_rotulado": None,
            "observacao": None,
        }
        for row in chosen
    ]


def _labels(entry: Mapping[str, Any]) -> list[str] | None:
    """The labelled values, or `None` for an entry nobody labelled yet."""
    label = entry.get("nivel_rotulado")
    if label is None:
        return None
    values = [label] if isinstance(label, str) else list(label)
    valid = {member.value for member in Seniority}
    if not values or any(value not in valid for value in values):
        raise ValueError(f"invalid nivel_rotulado for {entry.get('opportunity_id')}: {label!r}")
    return values


def measure_sample(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Precision per emitted level and what the labels say about the `UNKNOWN` titles."""
    by_level: dict[str, list[bool]] = defaultdict(list)
    unknown_labelled: dict[str, Counter[str]] = defaultdict(Counter)
    labelled = 0
    for entry in entries:
        labels = _labels(entry)
        if labels is None:
            continue
        labelled += 1
        title = str(entry.get("title") or "")
        emitted = classify(title)
        if emitted != Seniority.UNKNOWN.value:
            by_level[emitted].append(emitted in labels)
            continue
        pattern, _ = unknown_pattern(title)
        has_level = labels != [Seniority.UNKNOWN.value]
        unknown_labelled[pattern]["has_level" if has_level else "no_level"] += 1
    results = [result for level in by_level.values() for result in level]
    return {
        "mapping_version": SENIORITY_MAPPING_VERSION,
        "entries": len(entries),
        "labelled": labelled,
        # `None` while there is no labelled emission: an empty sample proves nothing.
        "precision": round(sum(results) / len(results), 4) if results else None,
        "precision_by_level": {
            level: {
                "emitted": len(values),
                "correct": sum(values),
                "precision": round(sum(values) / len(values), 4),
            }
            for level, values in sorted(by_level.items())
        },
        "unknown_by_pattern": {
            pattern: dict(counts) for pattern, counts in sorted(unknown_labelled.items())
        },
    }


# ------------------------------------------------------------------ database (SELECT only)


def _fetch_rows(areas: Sequence[str]) -> list[dict[str, Any]]:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from opportunity_radar.opportunities.models import OpportunityModel as M
    from opportunity_radar.platform.database import create_database_engine

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (or use --sample).")
    query = select(M.id, M.canonical_title, M.company_name).where(M.role_family.in_(list(areas)))
    with Session(create_database_engine(database_url)) as session:
        return [
            {"opportunity_id": str(row[0]), "title": row[1], "company": row[2]}
            for row in session.execute(query).all()
        ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--area",
        action="append",
        help=f"role family to read; repeat for several (default: {', '.join(DEFAULT_AREAS)})",
    )
    parser.add_argument("--sample", type=Path, default=None, help="labelled sample; no database")
    parser.add_argument("--sample-out", type=Path, default=None)
    parser.add_argument("--unknown-size", type=int, default=UNKNOWN_SAMPLE_SIZE)
    parser.add_argument("--classified-size", type=int, default=CLASSIFIED_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    if args.sample is not None:
        entries = json.loads(args.sample.read_text(encoding="utf-8"))["casos"]
        print(json.dumps(measure_sample(entries), ensure_ascii=False, indent=2))
        return 0

    rows = _fetch_rows(args.area or DEFAULT_AREAS)
    if args.sample_out is not None:
        sample = build_label_sample(
            rows,
            unknown_size=args.unknown_size,
            classified_size=args.classified_size,
            seed=args.seed,
        )
        args.sample_out.write_text(
            json.dumps({"casos": sample}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{len(sample)} unlabelled entries written to {args.sample_out}", file=sys.stderr)
        return 0
    print(json.dumps(baseline(rows), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
