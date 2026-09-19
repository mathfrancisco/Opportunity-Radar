import asyncio
from decimal import Decimal
from uuid import UUID

import pytest

from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_VERSION,
    OUTPUT_SCHEMA,
    AnalysisError,
    AnalysisFailureCode,
    AnalysisPolicy,
    AnalysisRequest,
    AnalysisStatus,
    NullAnalysisAdapter,
    analysis_cache_key,
    parse_analysis,
)
from opportunity_radar.matching.domain import EligibilityStatus, Verdict

_OPPORTUNITY_ID = UUID("11111111-1111-1111-1111-111111111111")
_PROFILE_VERSION_ID = UUID("22222222-2222-2222-2222-222222222222")


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary": "Strong Python match with unclear compensation.",
        "strengths": ["Python depth", "Remote friendly"],
        "risks": ["Compensation not disclosed"],
        "inferences": ["Team appears backend focused"],
        "unknowns": ["Timezone overlap requirement"],
        "recommended_review": True,
    }
    payload.update(overrides)
    return payload


def _request(
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    verdict: Verdict = Verdict.RECOMMENDED,
    score: Decimal = Decimal("72.5"),
    content_version: int = 3,
    rules_version: str = "matching-v1",
    taxonomy_version: str = "skills-v1",
) -> AnalysisRequest:
    return AnalysisRequest(
        opportunity_id=_OPPORTUNITY_ID,
        opportunity_content_version=content_version,
        profile_version_id=_PROFILE_VERSION_ID,
        rules_version=rules_version,
        taxonomy_version=taxonomy_version,
        eligibility=eligibility,
        verdict=verdict,
        score=score,
        opportunity_snapshot={"work_mode": "REMOTE"},
        profile_snapshot={"skills": ["python"]},
    )


def test_parses_valid_payload_and_stamps_provenance() -> None:
    analysis = parse_analysis(_payload(), model_id="llama3.2:3b", prompt_version="v1")

    assert analysis.summary == "Strong Python match with unclear compensation."
    assert analysis.strengths == ("Python depth", "Remote friendly")
    assert analysis.risks == ("Compensation not disclosed",)
    assert analysis.inferences == ("Team appears backend focused",)
    assert analysis.unknowns == ("Timezone overlap requirement",)
    assert analysis.recommended_review is True
    assert analysis.model_id == "llama3.2:3b"
    assert analysis.prompt_version == "v1"
    assert analysis.schema_version == ANALYSIS_SCHEMA_VERSION


def test_analysis_cannot_carry_a_score_or_eligibility() -> None:
    analysis = parse_analysis(_payload(), model_id="m", prompt_version="v1")

    assert "score" not in analysis.as_dict()
    assert "eligibility" not in analysis.as_dict()
    assert "verdict" not in analysis.as_dict()
    assert not hasattr(analysis, "score")


@pytest.mark.parametrize(
    "smuggled",
    [
        {"score": 99},
        {"eligibility": "ELIGIBLE"},
        {"verdict": "HIGH_PRIORITY"},
        {"disqualifiers": []},
    ],
)
def test_rejects_fields_outside_the_contract(smuggled: dict[str, object]) -> None:
    with pytest.raises(AnalysisError) as error:
        parse_analysis(_payload(**smuggled), model_id="m", prompt_version="v1")

    assert error.value.code is AnalysisFailureCode.SCHEMA_MISMATCH
    assert next(iter(smuggled)) in error.value.summary


@pytest.mark.parametrize(
    "field",
    ["summary", "strengths", "risks", "inferences", "unknowns", "recommended_review"],
)
def test_rejects_missing_required_field(field: str) -> None:
    payload = _payload()
    del payload[field]

    with pytest.raises(AnalysisError) as error:
        parse_analysis(payload, model_id="m", prompt_version="v1")

    assert error.value.code is AnalysisFailureCode.SCHEMA_MISMATCH
    assert field in error.value.summary


@pytest.mark.parametrize(
    "overrides",
    [
        {"summary": 12},
        {"summary": "   "},
        {"recommended_review": "true"},
        {"strengths": "Python"},
        {"risks": [{"text": "nested"}]},
        {"inferences": [None]},
    ],
)
def test_rejects_wrong_types(overrides: dict[str, object]) -> None:
    with pytest.raises(AnalysisError) as error:
        parse_analysis(_payload(**overrides), model_id="m", prompt_version="v1")

    assert error.value.code is AnalysisFailureCode.SCHEMA_MISMATCH
    assert error.value.retryable is True


def test_rejects_non_object_payload() -> None:
    with pytest.raises(AnalysisError) as error:
        parse_analysis(["not", "an", "object"], model_id="m", prompt_version="v1")

    assert error.value.code is AnalysisFailureCode.SCHEMA_MISMATCH


def test_rejects_oversized_summary_and_lists() -> None:
    long_summary = "x" * (OUTPUT_SCHEMA["properties"]["summary"]["maxLength"] + 1)
    with pytest.raises(AnalysisError):
        parse_analysis(_payload(summary=long_summary), model_id="m", prompt_version="v1")

    max_items = OUTPUT_SCHEMA["properties"]["risks"]["maxItems"]
    too_many = [f"item {index}" for index in range(max_items + 1)]
    with pytest.raises(AnalysisError):
        parse_analysis(_payload(risks=too_many), model_id="m", prompt_version="v1")


def test_drops_blank_list_entries_and_trims() -> None:
    analysis = parse_analysis(
        _payload(strengths=["  Python depth  ", "", "   "]),
        model_id="m",
        prompt_version="v1",
    )

    assert analysis.strengths == ("Python depth",)


def test_schema_is_closed_and_matches_the_validator() -> None:
    assert OUTPUT_SCHEMA["additionalProperties"] is False
    assert set(OUTPUT_SCHEMA["required"]) == set(OUTPUT_SCHEMA["properties"])
    assert "score" not in OUTPUT_SCHEMA["properties"]


def test_cache_key_is_stable_for_equivalent_inputs() -> None:
    first = analysis_cache_key(_request(), model_id="m", prompt_version="v1")
    second = analysis_cache_key(_request(), model_id="m", prompt_version="v1")

    assert first == second


@pytest.mark.parametrize(
    "kwargs, key_kwargs",
    [
        ({"content_version": 4}, {}),
        ({"rules_version": "matching-v2"}, {}),
        ({"taxonomy_version": "skills-v2"}, {}),
        ({}, {"model_id": "other-model"}),
        ({}, {"prompt_version": "v2"}),
        ({}, {"schema_version": "analysis-v2"}),
    ],
)
def test_cache_key_changes_when_any_relevant_component_changes(
    kwargs: dict[str, object], key_kwargs: dict[str, str]
) -> None:
    baseline = analysis_cache_key(_request(), model_id="m", prompt_version="v1")
    defaults = {"model_id": "m", "prompt_version": "v1"}
    defaults.update(key_kwargs)

    assert analysis_cache_key(_request(**kwargs), **defaults) != baseline  # type: ignore[arg-type]


def test_cache_key_ignores_the_deterministic_outcome() -> None:
    baseline = analysis_cache_key(_request(), model_id="m", prompt_version="v1")
    other_verdict = _request(verdict=Verdict.HIGH_PRIORITY, score=Decimal("91"))

    assert analysis_cache_key(other_verdict, model_id="m", prompt_version="v1") == baseline


@pytest.mark.parametrize(
    "request_kwargs, expected",
    [
        ({}, True),
        ({"verdict": Verdict.HIGH_PRIORITY}, True),
        ({"verdict": Verdict.REVIEW_REQUIRED}, True),
        ({"verdict": Verdict.LOW_MATCH}, False),
        ({"verdict": Verdict.INELIGIBLE}, False),
        ({"eligibility": EligibilityStatus.INELIGIBLE}, False),
        ({"eligibility": EligibilityStatus.UNKNOWN}, True),
    ],
)
def test_default_policy_skips_the_expensive_layer(
    request_kwargs: dict[str, object], expected: bool
) -> None:
    request = _request(**request_kwargs)  # type: ignore[arg-type]

    assert AnalysisPolicy().should_analyze(request) is expected


def test_policy_minimum_score_is_configurable() -> None:
    policy = AnalysisPolicy(minimum_score=Decimal("80"))

    assert policy.should_analyze(_request(score=Decimal("72.5"))) is False
    assert policy.should_analyze(_request(score=Decimal("80"))) is True


def test_null_adapter_degrades_without_calling_anything() -> None:
    outcome = asyncio.run(NullAnalysisAdapter().analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_SKIPPED
    assert outcome.analysis is None
    assert outcome.degraded is True
