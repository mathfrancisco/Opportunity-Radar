"""The neutral port every LLM provider implements (SPEC 43, section 3.1 and 4.2).

Nothing here knows about Groq: a second provider only needs to satisfy `LLMProvider`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Usage:
    """Token and latency accounting from the provider's own `usage` block."""

    prompt_tokens: int | None
    completion_tokens: int | None
    prompt_ms: int | None
    completion_ms: int | None


@dataclass(frozen=True)
class RateLimit:
    """The six `x-ratelimit-*` headers, read from every response (success or error)."""

    limit_requests: int | None
    limit_tokens: int | None
    remaining_requests: int | None
    remaining_tokens: int | None
    reset_requests_seconds: float | None
    reset_tokens_seconds: float | None


@dataclass(frozen=True)
class LLMRequest:
    """One structured chat completion. Field names track the API, not the domain."""

    model: str
    system: str
    user: str
    schema_name: str
    json_schema: Mapping[str, Any]
    strict: bool = True
    max_completion_tokens: int = 900
    temperature: float | None = None
    seed: int | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """A successful call. The provider never validates `content` against the schema."""

    model: str
    content: str
    usage: Usage
    rate_limit: RateLimit
    latency_ms: int
    finish_reason: str | None


class LLMProvider(Protocol):
    """A chat-completion backend behind a stable, provider-neutral contract."""

    name: str

    async def complete(self, request: LLMRequest) -> LLMResponse: ...
