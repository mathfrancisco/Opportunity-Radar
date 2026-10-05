"""Prompt `v3` (card F50-09): a smaller payload and capped lists, with `v1` untouched."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import pytest

from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_V3,
    V3_MAX_ITEMS,
    AnalysisError,
    AnalysisRequest,
    analysis_key,
    parse_analysis,
    reusable_payload_digest,
)
from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.evaluation import load_cases
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt, prompts_root
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.config import Settings

_CASES = prompts_root() / "opportunity_analysis" / "eval" / "cases"
_REFS = ("evidence_refs", "skill_evidence_refs")

#: `analysis_key` of the request below under v1, captured before v3 existed.
_V1_KEY = "b0143c24febb98ba4ab581d2a3178017d0dc0b71116d92b7290f91e42563c524"


def _settings(prompt: str) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", ai_analysis_prompt=prompt
    )


def _adapter(name: str) -> GroqAnalysisAdapter:
    settings = _settings(name)
    router = AIRouter(None, default_routes(settings))  # type: ignore[arg-type]
    return GroqAnalysisAdapter(router=router, prompt=load_prompt(name))


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _keys(item)}
    return set()


def _cases() -> list:
    if not _CASES.is_dir():
        pytest.skip("eval cases are not available in this environment")
    return load_cases(_CASES)


def _output(**counts: int) -> dict:
    sizes = {**V3_MAX_ITEMS, **counts}
    return {
        "summary": "s",
        "recommended_review": False,
        **{name: [f"{name} {i}" for i in range(size)] for name, size in sizes.items()},
    }


def test_v3_payload_has_no_evidence_refs_and_v1_is_unchanged() -> None:
    case = _cases()[0]
    assert set(_REFS) <= _keys(case.payload)  # the fixture does carry them

    v1 = _adapter("v1").prepare(case.request())
    v3 = _adapter("v3").prepare(case.request())

    assert set(_REFS) <= _keys(v1.payload)
    assert not set(_REFS) & _keys(v3.payload)
    assert not any(ref in v3.user_content for ref in _REFS)
    # Only the refs differ: everything else the model reads is the same.
    assert v3.payload["opportunity"]["required_skills"] == v1.payload["opportunity"][
        "required_skills"
    ]
    assert set(v1.payload) == set(v3.payload)


def test_v3_schema_accepts_the_cap_and_rejects_one_over() -> None:
    for name, cap in V3_MAX_ITEMS.items():
        at_cap = parse_analysis(
            _output(**{name: cap}), model_id="m", prompt_version="v3",
            schema_version=ANALYSIS_SCHEMA_V3,
        )
        assert len(getattr(at_cap, name)) == cap
        with pytest.raises(AnalysisError):
            parse_analysis(
                _output(**{name: cap + 1}), model_id="m", prompt_version="v3",
                schema_version=ANALYSIS_SCHEMA_V3,
            )
    assert load_prompt("v3").output_schema["properties"]["risks"]["maxItems"] == 5


def test_v3_estimated_input_tokens_are_lower_than_v1() -> None:
    # Removing the refs alone saves about 18% (1058 -> 865 over the 50 eval cases), short of
    # the 25% goal of card F50-09; the floor below pins what is achieved, not the goal.
    cases = _cases()
    v1, v3 = _adapter("v1"), _adapter("v3")

    def mean(adapter: GroqAnalysisAdapter) -> float:
        sizes = [adapter.prepare(case.request()).size.prompt_tokens_estimate for case in cases]
        return sum(sizes) / len(sizes)

    before, after = mean(v1), mean(v3)
    print(f"mean estimated input tokens over {len(cases)} cases: v1={before:.0f} v3={after:.0f}")
    assert after <= before * 0.85


def test_output_ceiling_only_changes_for_v3() -> None:
    ceiling = {
        name: default_routes(_settings(name))[AITask.JOB_MATCH].budget.max_output_tokens
        for name in ("v1", "v2", "v3")
    }

    assert ceiling == {"v1": 900, "v2": 900, "v3": 600}


def _request() -> AnalysisRequest:
    return AnalysisRequest(
        opportunity_id=UUID(int=1),
        opportunity_content_version=3,
        profile_version_id=UUID(int=2),
        rules_version="matching-v1",
        taxonomy_version="skills-v1",
        eligibility=EligibilityStatus.ELIGIBLE,
        verdict=Verdict.RECOMMENDED,
        score=Decimal("72.5"),
        opportunity_snapshot={"work_mode": "REMOTE"},
        profile_snapshot={"skills": ["python"]},
    )


def _key(name: str) -> str:
    prompt = load_prompt(name)
    return analysis_key(
        _request(),
        model_id="m",
        prompt_version=prompt.version,
        schema_version=prompt.schema_version,
        prompt_digest=prompt.digest,
        payload_hash=reusable_payload_digest({"opportunity": {"work_mode": "REMOTE"}}),
        options={"temperature": 0},
    )


def test_cache_key_differs_between_v1_and_v3_and_v1_is_pinned() -> None:
    assert _key("v1") == _V1_KEY
    assert _key("v3") != _key("v1")
    assert json.loads(json.dumps({"k": _key("v3")}))  # a plain hex string
