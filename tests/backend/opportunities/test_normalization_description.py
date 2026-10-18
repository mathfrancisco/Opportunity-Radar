"""R55-B3/B4: normalization stores plain text and extracts skills from it."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from opportunity_radar.opportunities.domain import (
    NormalizationInput,
    build_candidate,
    extract_skills,
)

_ESCAPED = (
    "&lt;h3&gt;Requirements&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;Python and SQL&lt;/li&gt;"
    "&lt;li&gt;Experience with GraphQL&lt;/li&gt;&lt;/ul&gt;"
)


def _input(source_type: str, description: str | None) -> NormalizationInput:
    return NormalizationInput(
        raw_item_id=uuid4(),
        source_definition_id=uuid4(),
        source_type=source_type,
        external_id="job-1",
        title="Backend Engineer",
        company_name="Acme",
        location_text="Remote - Brazil",
        description=description,
        published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("source_type", "description"),
    [
        ("greenhouse", _ESCAPED),
        (
            "teamtailor",
            "<h3>Requirements</h3><ul><li>Python and SQL</li><li>Experience with GraphQL</li></ul>",
        ),
        ("workable", "<p>Requirements</p><p>Python and SQL<br>Experience with GraphQL</p>"),
        ("lever", "Requirements\n- Python and SQL\n- Experience with GraphQL"),
    ],
)
def test_candidate_description_is_plain_text_and_skills_are_found(
    source_type: str, description: str
) -> None:
    candidate = build_candidate(_input(source_type, description))

    assert candidate.description is not None
    assert "<" not in candidate.description and "&lt;" not in candidate.description
    assert "Requirements" in candidate.description
    skills = {skill.canonical_id for skill in candidate.skills}
    assert {"python", "sql", "graphql"} <= skills


def test_plain_text_description_is_stored_unchanged() -> None:
    plain = "Requirements\n- Python and SQL\n\nR&D team"
    assert build_candidate(_input("ashby", plain)).description == plain


def test_missing_description_stays_missing() -> None:
    assert build_candidate(_input("greenhouse", None)).description is None


def test_skills_from_escaped_html_match_the_clean_text() -> None:
    found = {skill.canonical_id for skill in extract_skills("Backend Engineer", _ESCAPED, {})}
    assert {"python", "sql", "graphql"} <= found


_ESCAPED_NICE = (
    "&lt;h3&gt;Requirements&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;Python and SQL&lt;/li&gt;"
    "&lt;li&gt;Experience with GraphQL&lt;/li&gt;&lt;/ul&gt;"
    "&lt;h3&gt;Nice to have&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;"
    "&lt;li&gt;Docker&lt;/li&gt;&lt;/ul&gt;"
)


def test_skill_evidence_from_a_greenhouse_description_has_no_markup_and_finds_go() -> None:
    candidate = build_candidate(_input("greenhouse", _ESCAPED_NICE))

    by_id = {skill.canonical_id: skill for skill in candidate.skills}
    # "Go" is an ambiguous alias read from the 80 characters around it: the escaped markup
    # pushed "Experience with" out of that window before the text was cleaned.
    assert {"python", "sql", "go", "docker"} <= set(by_id)
    assert all(
        "&lt;" not in skill.evidence_text and "<" not in skill.evidence_text
        for skill in by_id.values()
    )
