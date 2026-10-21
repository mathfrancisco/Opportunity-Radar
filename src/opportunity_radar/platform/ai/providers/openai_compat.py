"""Generic client for an OpenAI-compatible `/chat/completions` backend, driven by a spec.

The request and the response are the ones `GroqProvider` already builds and reads; the
`ProviderSpec` says what differs. The model prefix is stripped before the call and the
response is labelled with the prefixed name (see `registry`). The Groq-only reasoning
switches (`include_reasoning`, `reasoning_format`) are never sent.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from typing import Any

import httpx

from opportunity_radar.platform.ai.providers.base import LLMRequest, LLMResponse
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.providers.registry import ProviderSpec


class OpenAICompatibleProvider(GroqProvider):
    """`LLMProvider` for the backend a `ProviderSpec` describes."""

    def __init__(
        self,
        spec: ProviderSpec,
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
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            connect_timeout_seconds=connect_timeout_seconds,
            client_factory=client_factory,
            clock=clock,
        )
        self._spec = spec
        self.name = spec.name

    async def complete(self, request: LLMRequest) -> LLMResponse:
        response = await super().complete(request)
        return replace(response, model=request.model)

    def _body(self, request: LLMRequest) -> dict[str, Any]:
        body = super()._body(replace(request, model=request.model.removeprefix(self._spec.prefix)))
        body.pop("include_reasoning", None)
        body.pop("reasoning_format", None)
        if not self._spec.reasoning_effort:
            body.pop("reasoning_effort", None)
        if self._spec.response_format == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body
