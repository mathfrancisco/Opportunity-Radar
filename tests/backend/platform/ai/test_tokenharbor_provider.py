"""Token Harbor beside Groq: the request it sends, routing by model prefix, the chains."""

import asyncio
import json

import httpx
from pydantic import SecretStr

from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMRequest
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.providers.routed import RoutedProvider, build_provider
from opportunity_radar.platform.ai.providers.tokenharbor import TokenHarborProvider
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.ai.telemetry import records_from_attempts
from opportunity_radar.platform.config import Settings

_KEY = "thk_live_test-key"
_FREE = "tokenharbor:deepseek-v4.1-flash:free"


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def _request(model: str) -> LLMRequest:
    return LLMRequest(
        model=model,
        system="system",
        user="user",
        schema_name="check",
        json_schema={"type": "object"},
        reasoning_effort="low",
    )


def _ok(model: str) -> httpx.Response:
    # The live API answers with the bare model name and no x-ratelimit headers.
    return httpx.Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 49, "completion_tokens": 101, "total_tokens": 150},
        },
    )


def _backend(cls, handler, *, base_url: str, api_key: str):
    return cls(
        api_key=api_key,
        base_url=base_url,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_request_drops_the_prefix_and_the_response_keeps_the_route_name() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _ok("deepseek-v4.1-flash")

    provider = _backend(
        TokenHarborProvider, handler, base_url="https://tokenharbor.ai/v1/", api_key=_KEY
    )
    response = asyncio.run(provider.complete(_request(_FREE)))

    assert str(seen[0].url) == "https://tokenharbor.ai/v1/chat/completions"
    assert seen[0].headers["Authorization"] == f"Bearer {_KEY}"
    body = json.loads(seen[0].content)
    assert body["model"] == "deepseek-v4.1-flash:free"
    assert body["response_format"]["type"] == "json_schema"
    assert "include_reasoning" not in body and "reasoning_format" not in body
    assert response.model == _FREE
    assert response.usage.prompt_tokens == 49 and response.usage.completion_tokens == 101
    assert response.rate_limit.remaining_requests is None


def test_429_is_quota_with_retry_after_and_the_key_stays_out_of_the_summary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"}, text=f"slow down {_KEY}")

    provider = _backend(
        TokenHarborProvider, handler, base_url="https://tokenharbor.ai/v1", api_key=_KEY
    )
    try:
        asyncio.run(provider.complete(_request(_FREE)))
    except ProviderError as error:
        assert error.kind is ErrorKind.QUOTA and error.retry_after_seconds == 12
        assert _KEY not in error.summary and _KEY not in repr(provider)
    else:
        raise AssertionError("expected a ProviderError")


def test_routed_provider_sends_each_model_to_its_backend() -> None:
    hosts: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        hosts.append((request.url.host, model))
        return _ok(model)

    routed = RoutedProvider(
        _backend(GroqProvider, handler, base_url="https://api.groq.com/openai/v1", api_key="g"),
        {
            "tokenharbor:": _backend(
                TokenHarborProvider, handler, base_url="https://tokenharbor.ai/v1", api_key=_KEY
            )
        },
    )
    asyncio.run(routed.complete(_request("openai/gpt-oss-120b")))
    asyncio.run(routed.complete(_request(_FREE)))

    assert hosts == [
        ("api.groq.com", "openai/gpt-oss-120b"),
        ("tokenharbor.ai", "deepseek-v4.1-flash:free"),
    ]
    assert routed.name == "groq+tokenharbor"


def test_without_a_key_nothing_changes() -> None:
    settings = _settings(groq_api_key=SecretStr("g"))

    assert isinstance(build_provider(settings), GroqProvider)
    assert default_routes(settings)[AITask.JOB_MATCH].chain == (
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
    )


def test_with_a_key_the_free_models_close_every_chain() -> None:
    settings = _settings(groq_api_key=SecretStr("g"), tokenharbor_api_key=SecretStr(_KEY))

    assert isinstance(build_provider(settings), RoutedProvider)
    routes = default_routes(settings)
    reserve = (_FREE, "tokenharbor:mimo-v2.6-flash:free")
    assert routes[AITask.JOB_MATCH].chain == ("openai/gpt-oss-120b", "qwen/qwen3.8-27b", *reserve)
    for route in routes.values():
        assert route.chain[-2:] == reserve
    custom = _settings(tokenharbor_api_key=SecretStr(_KEY), tokenharbor_models=" a:free , ,b ")
    assert default_routes(custom)[AITask.JOB_MATCH].chain[-2:] == (
        "tokenharbor:a:free",
        "tokenharbor:b",
    )


def test_router_falls_to_token_harbor_when_groq_is_rate_limited_and_telemetry_names_it() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "api.groq.com":
            return httpx.Response(429, headers={"retry-after": "60"})
        return _ok(json.loads(request.content)["model"])

    settings = _settings(groq_api_key=SecretStr("g"), tokenharbor_api_key=SecretStr(_KEY))
    routed = RoutedProvider(
        _backend(GroqProvider, handler, base_url=settings.groq_base_url, api_key="g"),
        {
            "tokenharbor:": _backend(
                TokenHarborProvider, handler, base_url=settings.tokenharbor_base_url, api_key=_KEY
            )
        },
    )
    router = AIRouter(routed, default_routes(settings), breaker=CircuitBreaker())

    result = asyncio.run(
        router.run(
            AITask.JOB_MATCH,
            system="s",
            user="u",
            schema_name="check",
            json_schema={"type": "object"},
        )
    )

    # Both Groq models answered 429 once each; the first free model then answered.
    assert calls == ["api.groq.com", "api.groq.com", "tokenharbor.ai"]
    assert result.response.model == _FREE and result.fallback_used
    records = records_from_attempts(
        result.attempts, task="job_match", provider="groq", fallback_used=True, prompt_version="v1"
    )
    assert [record.provider for record in records] == ["groq", "groq", "tokenharbor"]
    assert records[-1].model == _FREE and records[-1].success
