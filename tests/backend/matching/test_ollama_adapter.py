import asyncio
import json
from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from opportunity_radar.matching.analysis import (
    AnalysisFailureCode,
    AnalysisPolicy,
    AnalysisRequest,
    AnalysisStatus,
)
from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.ollama import OllamaAnalysisAdapter

_BASE_URL = "http://ollama:11434"
_MODEL = "llama3.2:3b"

_ANALYSIS = {
    "summary": "Strong Python match with unclear compensation.",
    "strengths": ["Python depth"],
    "risks": ["Compensation not disclosed"],
    "inferences": [],
    "unknowns": ["Timezone overlap requirement"],
    "recommended_review": False,
}


def _request(
    *,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    verdict: Verdict = Verdict.RECOMMENDED,
    score: Decimal = Decimal("72.5"),
    content_version: int = 3,
) -> AnalysisRequest:
    return AnalysisRequest(
        opportunity_id=UUID("11111111-1111-1111-1111-111111111111"),
        opportunity_content_version=content_version,
        profile_version_id=UUID("22222222-2222-2222-2222-222222222222"),
        rules_version="matching-v1",
        taxonomy_version="skills-v1",
        eligibility=eligibility,
        verdict=verdict,
        score=score,
        opportunity_snapshot={"work_mode": "REMOTE", "seniority": "SENIOR"},
        profile_snapshot={"skills": ["python"]},
    )


def _envelope(content: object) -> httpx.Response:
    body = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(200, json={"message": {"role": "assistant", "content": body}})


def _adapter(
    handler: httpx.MockTransport | None = None,
    **overrides: object,
) -> OllamaAnalysisAdapter:
    kwargs: dict[str, object] = {
        "base_url": _BASE_URL,
        "model": _MODEL,
        "max_retries": 0,
        "sleeper": _no_sleep,
    }
    kwargs.update(overrides)
    if handler is not None:
        kwargs["client"] = httpx.AsyncClient(transport=handler)
    return OllamaAnalysisAdapter(**kwargs)  # type: ignore[arg-type]


async def _no_sleep(delay: float) -> None:
    del delay


def _transport(handler: object) -> httpx.MockTransport:
    return httpx.MockTransport(handler)  # type: ignore[arg-type]


def test_returns_validated_analysis_and_sends_the_structured_contract() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return _envelope(_ANALYSIS)

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_COMPLETED
    assert outcome.degraded is False
    assert outcome.analysis is not None
    assert outcome.analysis.summary == _ANALYSIS["summary"]
    assert outcome.analysis.model_id == _MODEL
    assert seen["url"] == f"{_BASE_URL}/api/chat"

    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == _MODEL
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["format"]["additionalProperties"] is False


def test_prompt_marks_the_deterministic_result_as_authoritative() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _envelope(_ANALYSIS)

    asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    body = seen["body"]
    assert isinstance(body, dict)
    user_content = json.loads(body["messages"][1]["content"])
    assert user_content["deterministic_result"]["authoritative"] is True
    assert user_content["deterministic_result"]["verdict"] == "RECOMMENDED"
    assert user_content["deterministic_result"]["score"] == "72.5"
    assert "do not decide eligibility" in body["messages"][0]["content"]


def test_timeout_degrades_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.TIMEOUT
    assert outcome.analysis is None


def test_unreachable_ollama_degrades_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.TRANSPORT_ERROR


def test_missing_model_is_classified_and_not_retried() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(404, json={"error": "model not found"})

    adapter = _adapter(_transport(handler), max_retries=2)
    outcome = asyncio.run(adapter.analyze(_request()))

    assert outcome.failure_code is AnalysisFailureCode.MODEL_UNAVAILABLE
    assert calls["count"] == 1


@pytest.mark.parametrize(
    "status, code",
    [
        (429, AnalysisFailureCode.RATE_LIMITED),
        (500, AnalysisFailureCode.SERVER_ERROR),
        (503, AnalysisFailureCode.SERVER_ERROR),
        (418, AnalysisFailureCode.SERVER_ERROR),
    ],
)
def test_classifies_http_errors(status: int, code: AnalysisFailureCode) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "nope"})

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.failure_code is code


def test_invalid_json_content_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _envelope("this is not json")

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.INVALID_JSON


@pytest.mark.parametrize(
    "envelope",
    [
        {"unexpected": "shape"},
        {"message": "not an object"},
        {"message": {"role": "assistant"}},
        {"message": {"role": "assistant", "content": "   "}},
    ],
)
def test_rejects_malformed_envelopes(envelope: dict[str, object]) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=envelope)

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code in {
        AnalysisFailureCode.INVALID_JSON,
        AnalysisFailureCode.EMPTY_RESPONSE,
    }


def test_schema_violation_is_rejected_before_use() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _envelope({**_ANALYSIS, "score": 99})

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.SCHEMA_MISMATCH
    assert outcome.analysis is None


def test_retries_a_retryable_failure_then_succeeds() -> None:
    responses = [
        httpx.Response(503, json={"error": "loading model"}),
        _envelope(_ANALYSIS),
    ]
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    adapter = _adapter(
        _transport(handler),
        max_retries=1,
        retry_after_seconds=0.25,
        sleeper=sleeper,
    )
    outcome = asyncio.run(adapter.analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_COMPLETED
    assert responses == []
    assert delays == [0.25]


def test_stops_after_the_retry_budget() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(500, json={"error": "boom"})

    adapter = _adapter(_transport(handler), max_retries=2)
    outcome = asyncio.run(adapter.analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert calls["count"] == 3


def test_cache_avoids_an_identical_second_call() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _envelope(_ANALYSIS)

    adapter = _adapter(_transport(handler))

    async def run_twice() -> tuple[object, object]:
        return await adapter.analyze(_request()), await adapter.analyze(_request())

    first, second = asyncio.run(run_twice())

    assert calls["count"] == 1
    assert first == second


def test_cache_misses_when_the_opportunity_content_changes() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _envelope(_ANALYSIS)

    adapter = _adapter(_transport(handler))

    async def run_both() -> None:
        await adapter.analyze(_request(content_version=3))
        await adapter.analyze(_request(content_version=4))

    asyncio.run(run_both())

    assert calls["count"] == 2


def test_failures_are_not_cached() -> None:
    responses = [
        httpx.Response(500, json={"error": "boom"}),
        _envelope(_ANALYSIS),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    adapter = _adapter(_transport(handler))

    async def run_both() -> tuple[object, object]:
        return await adapter.analyze(_request()), await adapter.analyze(_request())

    first, second = asyncio.run(run_both())

    assert getattr(first, "status") is AnalysisStatus.AI_FAILED
    assert getattr(second, "status") is AnalysisStatus.AI_COMPLETED


@pytest.mark.parametrize(
    "request_kwargs",
    [
        {"eligibility": EligibilityStatus.INELIGIBLE},
        {"verdict": Verdict.INELIGIBLE},
        {"verdict": Verdict.LOW_MATCH},
    ],
)
def test_policy_skips_the_call_entirely(request_kwargs: dict[str, object]) -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _envelope(_ANALYSIS)

    outcome = asyncio.run(
        _adapter(_transport(handler)).analyze(_request(**request_kwargs))  # type: ignore[arg-type]
    )

    assert calls["count"] == 0
    assert outcome.status is AnalysisStatus.AI_SKIPPED
    assert outcome.degraded is True


def test_policy_threshold_is_configurable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return _envelope(_ANALYSIS)

    adapter = _adapter(
        _transport(handler),
        policy=AnalysisPolicy(minimum_score=Decimal("90")),
    )
    outcome = asyncio.run(adapter.analyze(_request(score=Decimal("72.5"))))

    assert outcome.status is AnalysisStatus.AI_SKIPPED


def test_rejects_conflicting_client_configuration() -> None:
    with pytest.raises(ValueError):
        OllamaAnalysisAdapter(
            base_url=_BASE_URL,
            model=_MODEL,
            client=httpx.AsyncClient(),
            client_factory=lambda: httpx.AsyncClient(),  # type: ignore[arg-type,return-value]
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": -1.0},
        {"max_retries": -1},
        {"retry_after_seconds": -0.5},
    ],
)
def test_rejects_invalid_limits(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        OllamaAnalysisAdapter(base_url=_BASE_URL, model=_MODEL, **overrides)  # type: ignore[arg-type]


def test_sends_the_configured_model_options_and_turns_thinking_off() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _envelope(_ANALYSIS)

    adapter = _adapter(
        _transport(handler),
        num_ctx=8192,
        num_predict=1024,
        seed=42,
        keep_alive="30m",
        think=False,
    )
    asyncio.run(adapter.analyze(_request()))

    body = seen["body"]
    assert isinstance(body, dict)
    assert body["options"] == {
        "temperature": 0,
        "num_ctx": 8192,
        "num_predict": 1024,
        "seed": 42,
    }
    # Top-level fields, not options: that is where the server reads them.
    assert body["keep_alive"] == "30m"
    assert body["think"] is False


def test_leaves_unset_options_to_the_request_defaults() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _envelope(_ANALYSIS)

    asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    body = seen["body"]
    assert isinstance(body, dict)
    assert body["options"] == {"temperature": 0}
    assert "keep_alive" not in body
    assert "think" not in body


def _timed_envelope(content: object) -> httpx.Response:
    body = content if isinstance(content, str) else json.dumps(content)
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": body},
            "total_duration": 4_200_000_000,
            "load_duration": 150_000_000,
            "prompt_eval_count": 1830,
            "prompt_eval_duration": 900_000_000,
            "eval_count": 212,
            "eval_duration": 3_100_000_000,
        },
    )


def test_reports_what_the_call_cost_in_milliseconds() -> None:
    adapter = _adapter(_transport(lambda request: _timed_envelope(_ANALYSIS)))
    outcome = asyncio.run(adapter.analyze(_request()))

    assert outcome.status is AnalysisStatus.AI_COMPLETED
    assert outcome.metrics is not None
    assert outcome.metrics.as_dict() == {
        "total_ms": 4200,
        "load_ms": 150,
        "prompt_tokens": 1830,
        "prompt_eval_ms": 900,
        "output_tokens": 212,
        "eval_ms": 3100,
    }


def test_an_answer_that_fails_validation_still_reports_its_cost() -> None:
    outcome = asyncio.run(
        _adapter(
            _transport(lambda request: _timed_envelope({"summary": "no other fields"})),
            max_retries=0,
        ).analyze(_request())
    )

    assert outcome.status is AnalysisStatus.AI_FAILED
    assert outcome.failure_code is AnalysisFailureCode.SCHEMA_MISMATCH
    assert outcome.metrics is not None
    assert outcome.metrics.total_ms == 4200


def test_absent_or_malformed_durations_stay_absent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": json.dumps(_ANALYSIS)},
                "total_duration": "slow",
                "eval_count": -3,
            },
        )

    outcome = asyncio.run(_adapter(_transport(handler)).analyze(_request()))

    assert outcome.metrics is not None
    assert outcome.metrics.total_ms is None
    assert outcome.metrics.output_tokens is None
    assert outcome.metrics.prompt_tokens is None


def test_a_cached_answer_reports_no_cost() -> None:
    adapter = _adapter(_transport(lambda request: _timed_envelope(_ANALYSIS)))

    asyncio.run(adapter.analyze(_request()))
    cached = asyncio.run(adapter.analyze(_request()))

    assert cached.status is AnalysisStatus.AI_COMPLETED
    assert cached.metrics is None


def test_warm_up_loads_the_model_and_reports_the_load() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"done": True, "load_duration": 2_500_000_000})

    metrics = asyncio.run(_adapter(_transport(handler), keep_alive="30m").warm_up())

    assert seen["url"] == f"{_BASE_URL}/api/generate"
    assert seen["body"] == {"model": _MODEL, "prompt": "", "keep_alive": "30m"}
    assert metrics is not None
    assert metrics.load_ms == 2500


def test_warm_up_never_raises_when_the_server_is_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert asyncio.run(_adapter(_transport(handler)).warm_up()) is None
