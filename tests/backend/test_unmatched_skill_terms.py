"""Unit coverage for the `skills-v2` taxonomy-gap ranking script (card F17-06)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.unmatched_skill_terms import unmatched_term_counts  # noqa: E402


def test_known_taxonomy_aliases_are_excluded() -> None:
    counts = unmatched_term_counts(["Looking for a Python and TypeScript engineer."])
    assert "python" not in counts
    assert "typescript" not in counts


def test_an_unmatched_technical_term_is_counted_once_per_description() -> None:
    counts = unmatched_term_counts(
        [
            "Experience with Snowflake and Snowflake pipelines required.",
            "We use Snowflake for our warehouse.",
        ]
    )
    assert counts["snowflake"] == 2


def test_common_words_are_filtered_out_of_the_ranking() -> None:
    counts = unmatched_term_counts(
        [
            "We are the team with strong ability and experience for this role "
            "including you and your work."
        ]
    )
    assert not counts
