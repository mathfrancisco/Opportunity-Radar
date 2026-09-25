"""Sample opportunity pairs the operator judges as duplicate or not.

    python scripts/sample_duplicates.py                 # Markdown report on stdout
    python scripts/sample_duplicates.py --json           # same pairs, machine-readable
    python scripts/sample_duplicates.py --size 50 --seed 1

Card F17-01: draws pairs from the same company whose titles look alike (trigram-style
similarity over the normalized title), for the operator to judge by hand. The judged
result feeds the duplicate rate in the SPEC's §3 baseline. Read-only; nothing is written
to the database.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine

DEFAULT_SAMPLE_SIZE = 50
#: Below this, two titles from the same company are unlikely to be the same job. Kept
#: low deliberately: a false positive costs one operator judgement, a missed duplicate
#: never enters the sample at all.
SIMILARITY_THRESHOLD = 0.55


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    company_id: UUID
    company_name: str | None
    first_id: UUID
    first_title: str
    second_id: UUID
    second_title: str
    similarity: float

    def as_dict(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "company_name": self.company_name,
            "first_opportunity_id": str(self.first_id),
            "first_title": self.first_title,
            "second_opportunity_id": str(self.second_id),
            "second_title": self.second_title,
            "similarity": round(self.similarity, 3),
        }


def _title_similarity(left: str, right: str) -> float:
    """A cheap, dependency-free stand-in for trigram similarity (no pg_trgm here)."""
    return SequenceMatcher(a=left, b=right).ratio()


def find_candidates(
    session: Session, *, threshold: float = SIMILARITY_THRESHOLD
) -> list[DuplicateCandidate]:
    rows = session.execute(
        select(
            OpportunityModel.id,
            OpportunityModel.canonical_company_id,
            OpportunityModel.company_name,
            OpportunityModel.canonical_title,
            OpportunityModel.normalized_title,
        ).where(OpportunityModel.canonical_company_id.is_not(None))
    ).all()
    by_company: dict[UUID, list[tuple]] = {}
    for row in rows:
        by_company.setdefault(row[1], []).append(row)

    candidates: list[DuplicateCandidate] = []
    for company_id, entries in by_company.items():
        if len(entries) < 2:
            continue
        for left, right in combinations(entries, 2):
            similarity = _title_similarity(left[4], right[4])
            if similarity >= threshold:
                candidates.append(
                    DuplicateCandidate(
                        company_id=company_id,
                        company_name=left[2] or right[2],
                        first_id=left[0],
                        first_title=left[3],
                        second_id=right[0],
                        second_title=right[3],
                        similarity=similarity,
                    )
                )
    return candidates


def sample_duplicates(
    session: Session, *, size: int = DEFAULT_SAMPLE_SIZE, seed: int | None = None
) -> list[DuplicateCandidate]:
    candidates = find_candidates(session)
    rng = random.Random(seed)
    rng.shuffle(candidates)
    return candidates[:size]


def _render_markdown(candidates: list[DuplicateCandidate]) -> str:
    lines = [
        f"# Amostra de possíveis duplicatas ({len(candidates)} pares)",
        "",
        "Julgue cada par: é a mesma vaga em fontes diferentes, ou duas vagas distintas da",
        "mesma empresa? O resultado alimenta a taxa de duplicatas da SPEC (§3).",
        "",
    ]
    for index, item in enumerate(candidates, start=1):
        lines.append(f"## {index}. {item.company_name or item.company_id} "
                      f"(similaridade {item.similarity:.2f})")
        lines.append(f"- A: `{item.first_id}` — {item.first_title}")
        lines.append(f"- B: `{item.second_id}` — {item.second_title}")
        lines.append("- Julgamento: ( ) mesma vaga  ( ) vagas distintas")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        candidates = sample_duplicates(session, size=args.size, seed=args.seed)

    if args.json:
        print(json.dumps([item.as_dict() for item in candidates], ensure_ascii=False, indent=2))
    else:
        print(_render_markdown(candidates))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
