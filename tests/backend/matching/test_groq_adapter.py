"""Tests for `GroqAnalysisAdapter` (cards F20-16, F20-17).

Uses the lightweight `FakeProvider` (scripted per-model outcomes) for policy, fallback,
overflow, quota and error-mapping tests, and a real `GroqProvider` over
`httpx.MockTransport` only where the literal HTTP body matters: the no-PII assertion
(card F20-15's remaining acceptance criterion).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from opportunity_radar.matching.analysis import (
    AnalysisFailureCode,
    AnalysisOutcome,
    AnalysisPolicy,
    AnalysisRequest,
    AnalysisStatus,
    SemanticAnalysis,
)
from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMRequest, LLMResponse, RateLimit, Usage
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import default_routes
from opportunity_radar.platform.config import Settings

_REASONING = "openai/gpt-oss-120b"
_ALT = "qwen/qwen3.8-27b"

_ANALYSIS_JSON = json.dumps(
    {
        "summary": "Strong Python match with unclear compensation.",
        "strengths": ["Python depth"],
        "risks": ["Compensation not disclosed"],
        "inferences": [],
        "unknowns": ["Timezone overlap requirement"],
        "recommended_review": False,
    }
)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides)  # type: ignore[call-arg,arg-type]


def _prompt():
    return load_prompt("v1")


def _request(
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    verdict: Verdict = Verdict.RECOMMENDED,
    score: Decimal = Decimal("72.5"),
    profile_snapshot: dict | None = None,
) -> AnalysisRequest:
    default_profile = {"skills": ["python"]}
    return AnalysisRequest(
        opportunity_id=UUID("11111111-1111-1111-1111-111111111111"),
        opportunity_content_version=3,
        profile_version_id=UUID("22222222-2222-2222-2222-222222222222"),
        rules_version="matching-v1",
        taxonomy_version="skills-v1",
        eligibility=eligibility,
        verdict=verdict,
        score=score,
        opportunity_snapshot={"work_mode": "REMOTE", "seniority": "SENIOR"},
        profile_snapshot=(
            profile_snapshot if profile_snapshot is not None else default_profile
        ),
    )


def _llm_response(
    model: str, content: str = _ANALYSIS_JSON, latency_ms: int = 10
) -> LLMResponse:
    return LLMResponse(
        model=model,
        content=content,
        usage=Usage(prompt_tokens=100, completion_tokens=20, prompt_ms=50, completion_ms=150),
        rate_limit=RateLimit(None, None, None, None, None, None),
        latency_ms=latency_ms,
        finish_reason="stop",
    )


class _FakeProvider:
    """Returns scripted outcomes per model, in order, and records every request."""

    name = "fake"

    def __init__(self, script: dict[str, list[LLMResponse | ProviderError]]) -> None:
        self._script = {model: list(outcomes) for model, outcomes in script.items()}
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        outcome = self._script[request.model].pop(0)
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


class _ExhaustedQuotaGuard:
    """Always out of balance: proves the router never calls the provider (card F20-13)."""

    def reserve(self, model: str, estimated_tokens: int):
        del model, estimated_tokens
        return None

    def settle(self, reservation, actual_tokens, rate_limit) -> None:  # pragma: no cover
        raise AssertionError("settle should never run: reserve always returns None")

    def release(self, reservation) -> None:  # pragma: no cover
        raise AssertionError("release should never run: reserve always returns None")

    def next_available_at(self, model: str) -> datetime:
        del model
        return datetime.now(UTC) + timedelta(minutes=1)


def _router(provider, **overrides: object) -> AIRouter:
    settings = _settings(**overrides)
    return AIRouter(
        provider,
        default_routes(settings),
        fallback_enabled=settings.ai_fallback_enabled,
        max_retries=settings.ai_max_retries,
    )


def _adapter(router: AIRouter, *, policy: AnalysisPolicy | None = None) -> GroqAnalysisAdapter:
    return GroqAnalysisAdapter(router=router, prompt=_prompt(), policy=policy)


def _analyze(adapter: GroqAnalysisAdapter, request: AnalysisRequest) -> AnalysisOutcome:
    return asyncio.run(adapter.analyze(request))


# --- F20-17: completion, fallback, policy, overflow, errors ---------------------------


def test_completed_records_model_tokens_latency() -> None:
    provider = _FakeProvider({_REASONING: [_llm_response(_REASONING)]})
    adapter = _adapter(_router(provider))

    outcome = _analyze(adapter, _request())

    assert outcome.status is AnalysisStatus.AI_COMPLETED
    assert outcome.analysis is not None
    assert outcome.analysis.model_id == _REASONING
    assert outcome.metrics is not None
    assert outcome.metrics.prompt_tokens == 100
    assert outcome.metrics.output_tokens == 20
    assert outcome.metrics.total_ms == 10
    assert outcome.metrics.prompt_tokens_estimate is not None
    assert outcome.metrics.prompt_tokens_estimate > 0


def test_fallback_model_recorded() -> None:
    provider = _FakeProvider(
        {
            _REASONING: [ProviderError(ErrorKind.QUOTA, "429")],
            _ALT: [_llm_response(_ALT)],
        }
    )
    adapter = _adapter(_router(provider))

    outcome = _analyze(adapter, _request())

    assert outcome.status is AnalysisStatus.AI_COMPLETED
    assert outcome.analysis is not None
    assert outcome.analysis.model_id == _ALT


def test_skipped_by_policy() -> None:
    provider = _FakeProvider({})
    adapter = _adapter(_router(provider))

    outcome = _analyze(adapter, _request(verdict=Verdict.LOW_MATCH))

    assert outcome.status is AnalysisStatus.AI_SKIPPED
    assert provider.requests == []


def test_overflow_skipped_without_call() -> None:
    provider = _FakeProvider({})
    adapter = _adapter(_router(provider))
    huge_profile = {"skills": ["python " * 20_000]}

    outcome = _analyze(adapter, _request(profile_snapshot=huge_profile))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.CONTEXT_OVERFLOW
    assert provider.requests == []


def test_quota_exhausted_no_http_call() -> None:
    provider = _FakeProvider({})
    router = AIRouter(
        provider,
        default_routes(_settings(ai_fallback_enabled=False)),
        fallback_enabled=False,
        max_retries=0,
        quota_guard=_ExhaustedQuotaGuard(),
    )
    adapter = _adapter(router)

    outcome = _analyze(adapter, _request())

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.QUOTA_EXHAUSTED
    assert provider.requests == []


@pytest.mark.parametrize(
    ("errors", "expected_code"),
    [
        ([ProviderError(ErrorKind.QUOTA, "429")], AnalysisFailureCode.QUOTA_EXHAUSTED),
        (
            [ProviderError(ErrorKind.CONFIGURATION, "unauthorized", status=401)],
            AnalysisFailureCode.NOT_CONFIGURED,
        ),
        (
            [ProviderError(ErrorKind.REQUEST, "bad request", status=400)],
            AnalysisFailureCode.SERVER_ERROR,
        ),
        (
            [
                ProviderError(ErrorKind.INVALID_OUTPUT, "bad json"),
                ProviderError(ErrorKind.INVALID_OUTPUT, "still bad"),
            ],
            AnalysisFailureCode.SCHEMA_MISMATCH,
        ),
        (
            [ProviderError(ErrorKind.TRANSIENT, "groq request timed out")],
            AnalysisFailureCode.TIMEOUT,
        ),
        (
            [ProviderError(ErrorKind.TRANSIENT, "could not connect to groq")],
            AnalysisFailureCode.TRANSPORT_ERROR,
        ),
        (
            [ProviderError(ErrorKind.TRANSIENT, "500: boom", status=500)],
            AnalysisFailureCode.SERVER_ERROR,
        ),
    ],
)
def test_error_mapping(
    errors: list[ProviderError], expected_code: AnalysisFailureCode
) -> None:
    provider = _FakeProvider({_REASONING: list(errors)})
    router = AIRouter(
        provider,
        default_routes(_settings(ai_fallback_enabled=False)),
        fallback_enabled=False,
        max_retries=0,
    )
    adapter = _adapter(router)

    outcome = _analyze(adapter, _request())

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is expected_code


def test_warm_up_returns_none() -> None:
    adapter = _adapter(_router(_FakeProvider({})))

    assert asyncio.run(adapter.warm_up()) is None
    assert asyncio.run(adapter.warm_up(only_if_idle=True)) is None


def test_describe() -> None:
    adapter = _adapter(_router(_FakeProvider({})))

    described = asyncio.run(adapter.describe())

    assert described == {"provider": "groq", "chain": [_REASONING, _ALT]}


def test_outcome_and_analysis_never_carry_score_or_verdict() -> None:
    """Structural guard: the semantic layer cannot smuggle a deterministic-result field
    back in (SPEC 43, section 3): neither dataclass declares one."""
    outcome_fields = {f.name for f in fields(AnalysisOutcome)}
    analysis_fields = {f.name for f in fields(SemanticAnalysis)}

    assert not outcome_fields & {"score", "verdict", "eligibility"}
    assert not analysis_fields & {"score", "verdict", "eligibility"}


def test_no_pii_in_http_body() -> None:
    """Card F20-15's last acceptance criterion: sanitize_for_llm runs before the request
    leaves the machine, so the wire body a `MockTransport` captures never carries it."""
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(
            200,
            json={
                "model": _REASONING,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": _ANALYSIS_JSON},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    provider = GroqProvider(
        api_key="test-secret-key",
        base_url="https://api.groq.com/openai/v1",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    router = AIRouter(
        provider,
        default_routes(_settings(ai_fallback_enabled=False)),
        fallback_enabled=False,
        max_retries=0,
    )
    adapter = _adapter(router)
    pii_profile = {
        "name": "Maria da Silva",
        "email": "maria.silva@example.com",
        "phone": "+55 11 91234-5678",
        "cpf": "123.456.789-00",
        "linkedin_url": "https://linkedin.com/in/mariasilva",
        "headline": "Senior Python Engineer",
        "bio": "Reach me at maria.silva@example.com or +55 11 91234-5678, CPF 123.456.789-00.",
    }

    outcome = _analyze(adapter, _request(profile_snapshot=pii_profile))

    assert outcome.status is AnalysisStatus.AI_COMPLETED
    assert len(bodies) == 1
    body = bodies[0].decode("utf-8")
    for pii in (
        "Maria da Silva",
        "maria.silva@example.com",
        "91234-5678",
        "123.456.789-00",
        "linkedin.com/in/mariasilva",
        "test-secret-key",
    ):
        assert pii not in body
    # Professional evidence survives the sanitizer (card F20-15).
    assert "Senior Python Engineer" in body


# --- F20-16: cache identity carries the provider and the route ------------------------


def test_key_stable_for_same_inputs() -> None:
    adapter = _adapter(_router(_FakeProvider({})))
    request = _request()

    first = adapter.prepare(request).cache_key
    second = adapter.prepare(request).cache_key

    assert first == second


def test_key_changes_with_chain() -> None:
    request = _request()
    default_adapter = _adapter(_router(_FakeProvider({})))
    changed_router = _router(_FakeProvider({}), groq_alt_model="other/alt-model")
    changed_adapter = _adapter(changed_router)

    default_key = default_adapter.prepare(request).cache_key
    changed_key = changed_adapter.prepare(request).cache_key

    assert default_key != changed_key


def test_key_changes_with_reasoning_effort() -> None:
    request = _request()
    default_adapter = _adapter(_router(_FakeProvider({})))
    changed_adapter = _adapter(_router(_FakeProvider({}), ai_reasoning_effort="medium"))

    default_key = default_adapter.prepare(request).cache_key
    changed_key = changed_adapter.prepare(request).cache_key

    assert default_key != changed_key
