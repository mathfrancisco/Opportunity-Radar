"""Groq chat-completion client (SPEC 43, section 4), plain `httpx` like every other
client in the project -- no provider SDK.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx

from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import (
    LLMRequest,
    LLMResponse,
    RateLimit,
    Usage,
)

_CHAT_COMPLETIONS_PATH = "/chat/completions"
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")
_DURATION_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
#: How much of an error body is kept in `summary`, after the API key is stripped out.
_SUMMARY_BODY_CHARS = 200


def parse_duration(value: str | None) -> float | None:
    """Parse a Groq duration such as `2m59.56s`, `7.66s` or `120ms` into seconds.

    A value this cannot fully account for -- unknown unit, trailing text, `None` -- is
    reported as unknown rather than guessed, so a bad header never fails the call.
    """
    if not value:
        return None
    parts = _DURATION_PART.findall(value)
    if not parts or "".join(number + unit for number, unit in parts) != value:
        return None
    return sum(float(number) * _DURATION_SECONDS[unit] for number, unit in parts)


class GroqProvider:
    """`LLMProvider` for the Groq OpenAI-compatible chat completions endpoint."""

    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 25.0,
        connect_timeout_seconds: float = 5.0,
        client_factory: (
            Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None
        ) = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=connect_timeout_seconds,
                    read=timeout_seconds,
                    write=timeout_seconds,
                    pool=connect_timeout_seconds,
                )
            )
        )
        self._clock = clock

    def __repr__(self) -> str:  # never includes the key
        return f"GroqProvider(base_url={self._base_url!r})"

    async def complete(self, request: LLMRequest) -> LLMResponse:
        started = self._clock()
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    f"{self._base_url}{_CHAT_COMPLETIONS_PATH}",
                    headers=self._headers(),
                    json=self._body(request),
                )
        except httpx.TimeoutException as error:
            raise ProviderError(
                ErrorKind.TRANSIENT, "groq request timed out", model=request.model
            ) from error
        except httpx.TransportError as error:
            raise ProviderError(
                ErrorKind.TRANSIENT, "could not connect to groq", model=request.model
            ) from error
        latency_ms = round((self._clock() - started) * 1000)
        rate_limit = self._rate_limit(response.headers)
        self._raise_for_status(response, rate_limit=rate_limit, model=request.model)
        return self._response(response, rate_limit=rate_limit, latency_ms=latency_ms)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _body(self, request: LLMRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": request.schema_name,
                    "strict": request.strict,
                    "schema": dict(request.json_schema),
                },
            },
            "max_completion_tokens": request.max_completion_tokens,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.seed is not None:
            body["seed"] = request.seed
        if request.reasoning_effort is not None:
            body["reasoning_effort"] = request.reasoning_effort
        if request.model.startswith("openai/gpt-oss"):
            body["include_reasoning"] = False
        elif request.model.startswith("qwen/"):
            body["reasoning_format"] = "hidden"
        return body

    def _rate_limit(self, headers: httpx.Headers) -> RateLimit:
        return RateLimit(
            limit_requests=_int_header(headers.get("x-ratelimit-limit-requests")),
            limit_tokens=_int_header(headers.get("x-ratelimit-limit-tokens")),
            remaining_requests=_int_header(headers.get("x-ratelimit-remaining-requests")),
            remaining_tokens=_int_header(headers.get("x-ratelimit-remaining-tokens")),
            reset_requests_seconds=parse_duration(headers.get("x-ratelimit-reset-requests")),
            reset_tokens_seconds=parse_duration(headers.get("x-ratelimit-reset-tokens")),
        )

    def _raise_for_status(
        self, response: httpx.Response, *, rate_limit: RateLimit, model: str
    ) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        summary = self._summary(status, response)
        if status in (400, 413, 422):
            raise ProviderError(ErrorKind.REQUEST, summary, status=status, model=model)
        if status in (401, 403, 404):
            raise ProviderError(
                ErrorKind.CONFIGURATION, summary, status=status, model=model
            )
        if status == 429:
            raise ProviderError(
                ErrorKind.QUOTA,
                summary,
                status=status,
                retry_after_seconds=_float_header(response.headers.get("retry-after")),
                model=model,
            )
        # 5xx and anything else unclassified are treated as transient.
        raise ProviderError(ErrorKind.TRANSIENT, summary, status=status, model=model)

    def _summary(self, status: int, response: httpx.Response) -> str:
        body = response.text[:_SUMMARY_BODY_CHARS].replace(self._api_key, "<redacted>")
        return f"{status}: {body}"

    def _response(
        self, response: httpx.Response, *, rate_limit: RateLimit, latency_ms: int
    ) -> LLMResponse:
        payload = response.json()
        choices = payload.get("choices") or []
        message = choices[0].get("message") if choices else None
        content = message.get("content") if message else None
        if not isinstance(content, str) or not content:
            raise ProviderError(
                ErrorKind.INVALID_OUTPUT,
                "groq response had no message content",
                model=payload.get("model"),
            )
        usage_payload = payload.get("usage") or {}
        usage = Usage(
            prompt_tokens=usage_payload.get("prompt_tokens"),
            completion_tokens=usage_payload.get("completion_tokens"),
            prompt_ms=_ms(usage_payload.get("prompt_time")),
            completion_ms=_ms(usage_payload.get("completion_time")),
        )
        return LLMResponse(
            model=payload.get("model", ""),
            content=content,
            usage=usage,
            rate_limit=rate_limit,
            latency_ms=latency_ms,
            finish_reason=choices[0].get("finish_reason") if choices else None,
        )


def _int_header(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float_header(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _ms(seconds: float | int | None) -> int | None:
    return None if seconds is None else round(seconds * 1000)
