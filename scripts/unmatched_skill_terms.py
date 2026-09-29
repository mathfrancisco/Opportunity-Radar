"""Rank the technical terms in the acquired descriptions that `SKILL_TAXONOMY`
(`skills-v1`) has no entry for — the taxonomy-gap input for `skills-v2` (card F17-06).

    python scripts/unmatched_skill_terms.py
    python scripts/unmatched_skill_terms.py --top 50 --min-count 3

Measurement on real data (documented here, no numbers checked in): run this against the
reference/production database and paste the top of its output into the F17-06 PR. Each
new taxonomy entry still needs the same manual review as the current 27 — aliases and
disambiguation — this script only ranks candidates, it never adds an entry.
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import SKILL_TAXONOMY
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine

#: A term must look like a technology token to be worth a human's review at all: word
#: characters plus the punctuation real tech names use (`.`, `#`, `+`), at least one
#: letter, 2+ characters. This is a coarse filter, not a classifier — the taxonomy
#: reviewer still judges every candidate.
_TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")

#: Common English/Portuguese words that pass the token pattern but are never a skill.
#: Not exhaustive by design: this script ranks by frequency, so a stray word that
#: slips through still has to out-rank real gaps to reach the reviewer's attention.
_STOPWORDS = frozenset(
    {
        "and", "the", "for", "with", "you", "our", "are", "will", "this", "that",
        "have", "has", "from", "your", "team", "work", "job", "role", "years",
        "experience", "strong", "ability", "including", "such", "about", "who",
        "we", "to", "of", "in", "on", "a", "an", "is", "as", "or", "at", "by",
        "e", "de", "da", "do", "para", "com", "uma", "um", "que", "os", "as",
        "no", "na", "dos", "das", "ser", "voc", "voce", "você", "nossa", "nosso",
        "trabalho", "experi", "experiência", "anos", "conhecimento", "vaga",
    }
)


def _all_known_aliases() -> frozenset[str]:
    return frozenset(
        alias.casefold()
        for entry in SKILL_TAXONOMY
        for alias in entry.aliases
    )


def unmatched_term_counts(descriptions: list[str]) -> Counter[str]:
    """Count taxonomy-unmatched candidate terms across `descriptions`.

    One vaga counts a term at most once, so one verbose posting cannot dominate the
    ranking (recall is about *how many vagas* a new entry would help, not word count).
    """
    known = _all_known_aliases()
    counts: Counter[str] = Counter()
    for description in descriptions:
        seen_in_this_description: set[str] = set()
        for match in _TOKEN_PATTERN.finditer(description):
            term = match.group(0)
            # Trailing sentence punctuation ("work.") is not part of the term; a real
            # tech name never ends in a bare ".", so this never trims one that matters.
            folded = term.casefold().rstrip(".")
            if not folded:
                continue
            if folded in known or folded in _STOPWORDS:
                continue
            if not any(character.isalpha() for character in term):
                continue
            if folded in seen_in_this_description:
                continue
            seen_in_this_description.add(folded)
            counts[folded] += 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--min-count", type=int, default=2)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        descriptions = [
            description
            for description in session.scalars(
                select(OpportunityModel.description).where(
                    OpportunityModel.description.is_not(None)
                )
            )
            if description
        ]

    counts = unmatched_term_counts(descriptions)
    ranked = [
        (term, count) for term, count in counts.most_common() if count >= args.min_count
    ][: args.top]
    print(f"{len(descriptions)} descriptions scanned; {len(ranked)} candidate terms shown.")
    for term, count in ranked:
        print(f"{count}\t{term}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
