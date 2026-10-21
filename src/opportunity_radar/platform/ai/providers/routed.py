"""One `LLMProvider` over several backends, chosen by the model name's prefix.

The router knows a single provider and a chain of model names per task. Routing by name
keeps that contract: a chain may mix Groq and reserve-provider models, and the breaker and
the quota guard, which are already per model, keep each backend's usage apart.
"""

from __future__ import annotations

from collections.abc import Mapping

from opportunity_radar.platform.ai.config import configured_providers
from opportunity_radar.platform.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.providers.openai_compat import OpenAICompatibleProvider
from opportunity_radar.platform.config import Settings


class RoutedProvider:
    """Sends a request to the backend registered for its model prefix, else the default."""

    def __init__(self, default: LLMProvider, by_prefix: Mapping[str, LLMProvider]) -> None:
        self._default = default
        self._by_prefix = dict(by_prefix)
        names = [default.name, *(backend.name for backend in by_prefix.values())]
        self.name = "+".join(dict.fromkeys(names))

    def backend_for(self, model: str) -> LLMProvider:
        for prefix, backend in self._by_prefix.items():
            if model.startswith(prefix):
                return backend
        return self._default

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await self.backend_for(request.model).complete(request)


def build_provider(settings: Settings) -> LLMProvider:
    """Groq plus every configured reserve provider, each behind its model-name prefix.

    Without a Groq key the first reserve is the default backend; no chain reaches it by an
    unprefixed name, because `default_routes` leaves the Groq models out in that case.
    """
    backends: dict[str, LLMProvider] = {
        spec.prefix: OpenAICompatibleProvider(
            spec,
            api_key=key,
            base_url=base_url,
            timeout_seconds=settings.ai_timeout_seconds,
            connect_timeout_seconds=settings.ai_connect_timeout_seconds,
        )
        for spec, key, base_url in configured_providers(settings)
    }
    groq_key = settings.groq_api_key.get_secret_value()
    if not groq_key and backends:
        default = next(iter(backends.values()))
        return RoutedProvider(default, backends)
    groq = GroqProvider(
        api_key=groq_key,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        connect_timeout_seconds=settings.ai_connect_timeout_seconds,
    )
    return RoutedProvider(groq, backends) if backends else groq
