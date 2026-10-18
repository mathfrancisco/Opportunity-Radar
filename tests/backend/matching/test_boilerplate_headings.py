"""R55-C2 review: dropping an institutional section never swallows the requirements."""

from __future__ import annotations

import pytest

from opportunity_radar.matching.text import clean_description, fit_description_by_section


@pytest.mark.parametrize(
    ("posting", "kept", "dropped"),
    [
        (
            "Our mission\nWe build tools.\nWhat we're looking for\n5+ years of Python\n"
            "Experience with Postgres",
            ["5+ years of Python", "Experience with Postgres"],
            "We build tools.",
        ),
        ("Company overview\nWe are big.\nSkills\nPython\nAWS", ["Python", "AWS"], "We are big."),
        (
            "Why join us\nGreat team.\nYour profile\n- 3 years of Go",
            ["3 years of Go"],
            "Great team.",
        ),
        ("Life at Acme\nWe have fun.\nMust have\n- Kubernetes", ["Kubernetes"], "We have fun."),
        (
            "Nossa missão\nCrescer juntos.\nRequisitos\n- Java\n- Spring",
            ["Java", "Spring"],
            "Crescer juntos.",
        ),
    ],
)
def test_requirements_after_an_institutional_block_survive(
    posting: str, kept: list[str], dropped: str
) -> None:
    cleaned = clean_description(posting)

    for line in kept:
        assert line in cleaned
    assert dropped not in cleaned


def test_an_institutional_block_without_a_following_heading_is_still_dropped() -> None:
    cleaned = clean_description(
        "Senior engineer.\nRequirements\n- Python\nBenefits\nHealth plan.\nGym pass."
    )

    assert "Python" in cleaned
    assert "Health plan." not in cleaned and "Gym pass." not in cleaned


def test_a_smaller_section_that_fits_is_kept_after_a_cut() -> None:
    big = "Requirements\n" + "Python is required. " * 40
    small = "## Location\nRemote."
    fitted = fit_description_by_section(
        big + "\n\nAbout the role\n" + "Short intro. " + "x" * 300 + "\n\n" + small,
        available_tokens=len(big) + 80,
        tokens_per_char=1.0,
    )

    assert fitted.truncated
    assert "Remote." in fitted.text
