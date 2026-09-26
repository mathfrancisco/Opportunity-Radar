import asyncio
import json
import logging

import httpx
import pytest

from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMRequest
from opportunity_radar.platform.ai.providers.groq import GroqProvider, parse_duration

_JSON_SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}}


def _provider(handler, *, api_key: str = "secret-key") -> GroqProvider:
    return GroqProvider(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        clock=iter([0.0, 0.25]).__next__,
    )


def _request(model: str = "openai/gpt-oss-120b") -> LLMRequest:
    return LLMRequest(
        model=model,
        system="system prompt",
        user="user payload",
        schema_name="analysis_v1",
        json_schema=_JSON_SCHEMA,
    )


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "openai/gpt-oss-120b",
            "choices": [
                {
                    "message": {"role": "assistant", "content": '{"summary": "ok"}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 2100,
                "completion_tokens": 422,
                "prompt_time": 0.12,
                "completion_time": 0.81,
            },
        },
        headers={
            "x-ratelimit-limit-requests": "30",
            "x-ratelimit-limit-tokens": "8000",
            "x-ratelimit-remaining-requests": "29",
            "x-ratelimit-remaining-tokens": "7500",
            "x-ratelimit-reset-requests": "2m59.56s",
            "x-ratelimit-reset-tokens": "7.66s",
        },
    )


def test_success_parses_content_usage_and_headers() -> None:
    provider = _provider(lambda request: _success_response())

    response = asyncio.run(provider.complete(_request()))

    assert response.content == '{"summary": "ok"}'
    assert response.model == "openai/gpt-oss-120b"
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 2100
    assert response.usage.completion_tokens == 422
    assert response.usage.prompt_ms == 120
    assert response.usage.completion_ms == 810
    assert response.rate_limit.limit_requests == 30
    assert response.rate_limit.remaining_tokens == 7500
    assert response.rate_limit.reset_requests_seconds == pytest.approx(179.56)
    assert response.rate_limit.reset_tokens_seconds == pytest.approx(7.66)
    assert response.latency_ms == 250


def test_body_for_gpt_oss_sends_include_reasoning_false() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return _success_response()

    provider = _provider(handler)
    asyncio.run(provider.complete(_request(model="openai/gpt-oss-120b")))

    body = json.loads(bodies[0])
    assert body["include_reasoning"] is False
    assert "reasoning_format" not in body


def test_body_for_qwen_sends_reasoning_format_hidden() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return _success_response()

    provider = _provider(handler)
    asyncio.run(provider.complete(_request(model="qwen/qwen3.8-27b")))

    body = json.loads(bodies[0])
    assert body["reasoning_format"] == "hidden"
    assert "include_reasoning" not in body


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, ErrorKind.REQUEST),
        (401, ErrorKind.CONFIGURATION),
        (403, ErrorKind.CONFIGURATION),
        (404, ErrorKind.CONFIGURATION),
        (413, ErrorKind.REQUEST),
        (422, ErrorKind.REQUEST),
        (429, ErrorKind.QUOTA),
        (500, ErrorKind.TRANSIENT),
        (503, ErrorKind.TRANSIENT),
    ],
)
def test_status_mapping(status: int, kind: ErrorKind) -> None:
    provider = _provider(lambda request: httpx.Response(status, text="boom"))

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(provider.complete(_request()))

    assert excinfo.value.kind is kind
    assert excinfo.value.status == status


def test_429_reads_retry_after() -> None:
    provider = _provider(
        lambda request: httpx.Response(429, text="slow down", headers={"retry-after": "12"})
    )

    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(provider.complete(_request()))

    assert excinfo.value.kind is ErrorKind.QUOTA
    assert excinfo.value.retry_after_seconds == 12.0


def test_timeout_and_transport_error_are_transient() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    provider = _provider(timeout_handler)
    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(provider.complete(_request()))
    assert excinfo.value.kind is ErrorKind.TRANSIENT

    def transport_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = _provider(transport_handler)
    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(provider.complete(_request()))
    assert excinfo.value.kind is ErrorKind.TRANSIENT


def test_empty_content_is_invalid_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-120b",
                "choices": [{"message": {"role": "assistant", "content": ""}}],
                "usage": {},
            },
        )

    provider = _provider(handler)
    with pytest.raises(ProviderError) as excinfo:
        asyncio.run(provider.complete(_request()))
    assert excinfo.value.kind is ErrorKind.INVALID_OUTPUT


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2m59.56s", 179.56),
        ("7.66s", 7.66),
        ("120ms", 0.12),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_duration(value: str | None, expected: float | None) -> None:
    result = parse_duration(value)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_api_key_never_in_repr_summary_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    provider = _provider(
        lambda request: httpx.Response(401, text="key secret-key is invalid"),
        api_key="secret-key",
    )

    assert "secret-key" not in repr(provider)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderError) as excinfo:
            asyncio.run(provider.complete(_request()))

    assert "secret-key" not in excinfo.value.summary
    assert all("secret-key" not in record.getMessage() for record in caplog.records)
