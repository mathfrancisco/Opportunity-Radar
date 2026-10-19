"""R55-E6: the stored description is cleaned and capped; extraction still reads the full text."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from opportunity_radar.matching.text import trim_stored_description
from opportunity_radar.opportunities.domain import NormalizationInput, build_candidate
from opportunity_radar.opportunities.service import (
    _apply_evidence_fields,
    _new_opportunity,
    _stored_description,
)

CAP = 4000
_SEEN = datetime(2026, 10, 1, tzinfo=UTC)
_INSTITUTIONAL = "We are a global company that believes in people and in building things. " * 40
_REQUIREMENTS = (
    "Requirements\n- 5 years of Python and SQL\n- Experience designing REST APIs\n\n"
    "Responsibilities\n- Own the billing service\n- Review code from the team\n"
)
_FILLER = "The team ships weekly and values clear writing, small steps and steady progress. " * 60


def _long_posting() -> str:
    return (
        f"About us\n{_INSTITUTIONAL}\n\n{_REQUIREMENTS}\n"
        f"Our culture\n{_FILLER}\n\nBenefits\n{_INSTITUTIONAL}\n"
    )


def _input(description: str | None) -> NormalizationInput:
    return NormalizationInput(
        raw_item_id=uuid4(),
        source_definition_id=uuid4(),
        source_type="lever",
        external_id="job-1",
        title="Backend Engineer",
        company_name="Acme",
        location_text="Remote - Brazil",
        description=description,
        published_at=_SEEN,
    )


def test_long_description_loses_boilerplate_and_keeps_requirements() -> None:
    text = _long_posting()
    assert len(text) > CAP

    trimmed = trim_stored_description(text, CAP)

    assert trimmed is not None and len(trimmed) <= CAP
    assert "Requirements" in trimmed and "Python and SQL" in trimmed
    assert "Responsibilities" in trimmed and "billing service" in trimmed
    assert "global company" not in trimmed


def test_requirements_after_a_long_opening_survive_the_cap() -> None:
    text = f"Intro\n{_FILLER}\n\n{_REQUIREMENTS}"
    assert len(text) > CAP

    trimmed = trim_stored_description(text, CAP)

    assert trimmed is not None and len(trimmed) <= CAP
    assert "Python and SQL" in trimmed and "billing service" in trimmed


def test_trimming_is_idempotent() -> None:
    once = trim_stored_description(_long_posting(), CAP)
    assert trim_stored_description(once, CAP) == once


def test_short_description_is_unchanged_even_with_a_boilerplate_heading() -> None:
    short = "About us\nSmall team.\n\nRequirements\n- Python"
    assert trim_stored_description(short, CAP) == short
    assert trim_stored_description(None, CAP) is None
    assert trim_stored_description(_long_posting(), 0) == _long_posting()


def test_extraction_runs_on_the_full_text_but_storage_is_trimmed() -> None:
    text = f"{_REQUIREMENTS}\nHow we work:\n{_FILLER}\n\nNice to have\n- Experience with Rust\n"
    # The skill appears only past the cap.
    assert text.index("Rust") > CAP

    candidate = build_candidate(_input(text))

    assert "rust" in {skill.canonical_id for skill in candidate.skills}
    assert candidate.description == text.strip()
    stored = _stored_description(candidate.description)
    assert stored is not None and len(stored) <= CAP and "Rust" not in stored
    assert _new_opportunity(candidate, first_seen_at=_SEEN).description == stored


def test_untrimmed_legacy_row_is_trimmed_without_a_version_bump() -> None:
    text = _long_posting()
    candidate = build_candidate(_input(text))
    opportunity = _new_opportunity(candidate, first_seen_at=_SEEN)
    opportunity.description = text  # a row written before R55-E6

    assert _apply_evidence_fields(opportunity, candidate) is False
    assert opportunity.description == _stored_description(text)
    assert _apply_evidence_fields(opportunity, candidate) is False


def test_a_real_edit_of_the_posting_still_bumps() -> None:
    text = _long_posting()
    opportunity = _new_opportunity(build_candidate(_input(text)), first_seen_at=_SEEN)
    edited = build_candidate(_input(text.replace("billing service", "payments platform")))

    assert _apply_evidence_fields(opportunity, edited) is True
    assert "payments platform" in (opportunity.description or "")
