"""Card R55-C2: the prompt carries clean text cut by section, not company boilerplate."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from opportunity_radar.matching.analysis import AnalysisRequest
from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt
from opportunity_radar.matching.text import (
    clean_description,
    fit_description,
    fit_description_by_section,
    split_sections,
)
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import default_routes
from opportunity_radar.platform.config import Settings

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "r55_c2_postings.json"
_POSTINGS = json.loads(_FIXTURE.read_text(encoding="utf-8"))

#: Prompt tokens (estimate) the pilot measured for one analysis before this card.
_PILOT_PROMPT_TOKENS = 1099


def _adapter() -> GroqAnalysisAdapter:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", ai_analysis_prompt="v2"
    )
    router = AIRouter(provider=None, routes=default_routes(settings))  # type: ignore[arg-type]
    return GroqAnalysisAdapter(router=router, prompt=load_prompt("v2"))


def _request(index: int) -> AnalysisRequest:
    return AnalysisRequest(
        opportunity_id=UUID(int=index + 1),
        opportunity_content_version=1,
        profile_version_id=UUID(int=99),
        rules_version="matching-v1",
        taxonomy_version="skills-v1",
        eligibility=EligibilityStatus.ELIGIBLE,
        verdict=Verdict.RECOMMENDED,
        score=Decimal("70"),
        opportunity_snapshot={"work_mode": "REMOTE", "seniority": "MID"},
        profile_snapshot={"skills": ["python", "sql"]},
        posting=_POSTINGS[index],
    )


def test_repeated_company_blocks_are_dropped_from_the_clean_text() -> None:
    cleaned = clean_description(_POSTINGS[0]["description"])

    assert "Our Mission" not in cleaned and "Why join us" not in cleaned
    assert "Perk number" not in cleaned
    assert "3+ years with Python and PostgreSQL" in cleaned


def test_a_pay_fact_inside_a_dropped_block_survives() -> None:
    text = "Why join us\nSalary range is USD 90k.\nFree snacks.\n\nRequirements\nPython."
    cleaned = clean_description(text)

    assert "Salary range is USD 90k." in cleaned
    assert "Free snacks" not in cleaned


def test_a_description_that_fits_is_returned_untouched() -> None:
    text = "Intro line.\n\nRequirements\nPython.\n\nPerks we like\nCoffee."

    fitted = fit_description_by_section(text, available_tokens=1_000, tokens_per_char=0.35)

    assert (fitted.text, fitted.truncated) == (text, False)


def test_a_cut_keeps_requirements_and_responsibilities_before_the_rest() -> None:
    intro = "Context sentence about the team. " * 40
    text = f"About the team\n{intro}\n\nResponsibilities\nOwn the API.\n\nRequirements\nPython."

    plain = fit_description(text, available_tokens=40, tokens_per_char=0.35)
    by_section = fit_description_by_section(text, available_tokens=40, tokens_per_char=0.35)

    assert "Python." not in plain.text  # the old cut lost the requirements
    assert by_section.truncated
    assert "Requirements\nPython." in by_section.text
    assert "Own the API." in by_section.text
    assert by_section.text.index("Responsibilities") < by_section.text.index("Requirements")


def test_without_a_priority_heading_the_cut_is_the_plain_one() -> None:
    text = "Some sentence about the work. " * 50

    assert fit_description_by_section(
        text, available_tokens=30, tokens_per_char=0.35
    ) == fit_description(text, available_tokens=30, tokens_per_char=0.35)


def test_split_sections_marks_only_the_priority_headings() -> None:
    text = "Intro\n\nRequirements\nPython.\n\nOur stack:\nVale.\n\nQualifications\nSQL."
    sections = split_sections(text)

    assert [flag for flag, _ in sections] == [False, True, False, True]


@pytest.mark.parametrize("index", [0, 1])
def test_prompt_tokens_fall_on_fixture_postings_without_losing_fields(index: int) -> None:
    prepared = _adapter().prepare(_request(index))

    assert prepared.size.prompt_tokens_estimate is not None
    assert prepared.size.prompt_tokens_estimate <= _PILOT_PROMPT_TOKENS
    assert set(prepared.payload) == {
        "schema_version", "deterministic_result", "opportunity", "posting", "profile",
        "profile_history",
    }
    sent = json.dumps(prepared.payload, ensure_ascii=False)
    assert "Our Mission" not in sent and "Why join us" not in sent
    assert "3+ years" in sent or "SQL at scale" in sent
    assert prepared.inference["cut"]["description_truncated"] is False


def test_a_long_posting_keeps_its_requirements_under_the_token_ceiling() -> None:
    prepared = _adapter().prepare(_request(2))
    sent = json.dumps(prepared.payload, ensure_ascii=False)

    assert prepared.inference["cut"]["description_truncated"] is True
    assert "5+ years operating Kubernetes in production" in sent
    assert not prepared.overflow
