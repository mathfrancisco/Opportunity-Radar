"""One `LLMProvider` over several backends, chosen by the model name's prefix.

The router knows a single provider and a chain of model names per task. Routing by name
keeps that contract: a chain may mix Groq and Token Harbor models, and the breaker and the
quota guard, which are already per model, keep each backend's usage apart.
"""

from __future__ import annotations

from collections.abc import Mapping

from opportunity_radar.platform.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.providers.tokenharbor import MODEL_PREFIX, TokenHarborProvider
from opportunity_radar.platform.config import Settings


class RoutedProvider:
    """Sends a request to the backend registered for its model prefix, else the default."""

    def __init__(self, default: LLMProvider, by_prefix: Mapping[str, LLMProvider]) -> None:
        self._default = default
        self._by_prefix = dict(by_prefix)
        self.name = "+".join([default.name, *(backend.name for backend in by_prefix.values())])

    def backend_for(self, model: str) -> LLMProvider:
        for prefix, backend in self._by_prefix.items():
            if model.startswith(prefix):
                return backend
        return self._default

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self.backend_for(request.model).complete(request)



def build_provider(settings: Settings) -> LLMProvider:
    """Groq alone, or Groq plus Token Harbor when `TOKENHARBOR_API_KEY` is set."""
    groq = GroqProvider(
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.groq_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        connect_timeout_seconds=settings.ai_connect_timeout_seconds,
    )
    tokenharbor_key = settings.tokenharbor_api_key.get_secret_value()
    if not tokenharbor_key:
        return groq
    return RoutedProvider(
        groq,
        {
            MODEL_PREFIX: TokenHarborProvider(
                api_key=tokenharbor_key,
                base_url=settings.tokenharbor_base_url,
                timeout_seconds=settings.ai_timeout_seconds,
                connect_timeout_seconds=settings.ai_connect_timeout_seconds,
            )
        },
    )
