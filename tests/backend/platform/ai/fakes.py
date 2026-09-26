"""Test doubles shared by the AI routing cards (F20-09 onward)."""

from __future__ import annotations

from opportunity_radar.platform.ai.errors import ProviderError
from opportunity_radar.platform.ai.providers.base import (
    LLMRequest,
    LLMResponse,
    RateLimit,
    Usage,
)


def response(model: str, content: str = '{"summary": "ok"}', latency_ms: int = 10) -> LLMResponse:
    return LLMResponse(
        model=model,
        content=content,
        usage=Usage(prompt_tokens=100, completion_tokens=20, prompt_ms=None, completion_ms=None),
        rate_limit=RateLimit(None, None, None, None, None, None),
        latency_ms=latency_ms,
        finish_reason="stop",
    )


class FakeProvider:
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

    def models_called(self) -> list[str]:
        return [request.model for request in self.requests]
