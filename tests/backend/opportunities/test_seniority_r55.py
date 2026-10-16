"""R55-B4: seniority from titles, measured on a fixture of realistic ATS titles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opportunity_radar.opportunities.domain import Seniority, infer_seniority

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "r55_seniority_titles.json"
_ROWS = json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("row", _ROWS, ids=[row["title"] for row in _ROWS])
def test_title_maps_to_the_expected_level(row: dict[str, str]) -> None:
    assert infer_seniority(row["title"], None, {}) is Seniority(row["expected"])


def test_unknown_rate_on_the_fixture_is_only_titles_that_state_no_level() -> None:
    unknown = sum(infer_seniority(row["title"], None, {}) is Seniority.UNKNOWN for row in _ROWS)

    # 9 of 32 before seniority-v7; the 4 left are titles that state no level.
    assert unknown == sum(row["expected"] == "UNKNOWN" for row in _ROWS) == 4


@pytest.mark.parametrize(
    "title",
    ["Intermediate", "intermediate engineer", "ENGENHEIRO INTERMEDIÁRIO", "Intermediária"],
)
def test_intermediate_words_are_mid(title: str) -> None:
    assert infer_seniority(title, None, {}) is Seniority.MID


@pytest.mark.parametrize("title", ["Senior Intermediate Engineer", "Intermediate Staff Engineer"])
def test_a_higher_level_word_still_wins_over_intermediate(title: str) -> None:
    assert infer_seniority(title, None, {}) in {Seniority.SENIOR, Seniority.STAFF}
