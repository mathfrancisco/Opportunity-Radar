"""Runs one AI task through its model chain (SPEC 43, section 6).

Each model is tried once; retry, circuit breaker and quota arrive in F20-10 to F20-12.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute

#: Failures another model may not share; the others would fail the same way everywhere.
_FALLBACK_KINDS = frozenset({ErrorKind.QUOTA, ErrorKind.TRANSIENT, ErrorKind.INVALID_OUTPUT})


@dataclass(frozen=True)
class Attempt:
    model: str
    attempt: int  # 0 = first attempt on that model
    error_kind: ErrorKind | None
    latency_ms: int | None


@dataclass(frozen=True)
class RouterResult:
    response: LLMResponse
    attempts: tuple[Attempt, ...]
    fallback_used: bool  # True when the answering model is not chain[0]


class AIRouter:
    def __init__(
        self,
        provider: LLMProvider,
        routes: Mapping[AITask, ModelRoute],
        *,
        fallback_enabled: bool = True,
    ) -> None:
        self._provider = provider
        self._routes = dict(routes)
        self._fallback_enabled = fallback_enabled

    def route(self, task: AITask) -> ModelRoute:
        return self._routes[task]

    async def run(
        self,
        task: AITask,
        *,
        system: str,
        user: str,
        schema_name: str,
        json_schema: Mapping[str, Any],
        temperature: float | None = None,
        seed: int | None = None,
    ) -> RouterResult:
        route = self.route(task)
        chain = route.chain if self._fallback_enabled else route.chain[:1]
        attempts: list[Attempt] = []
        last_error: ProviderError | None = None
        for model in chain:
            request = LLMRequest(
                model=model,
                system=system,
                user=user,
                schema_name=schema_name,
                json_schema=json_schema,
                max_completion_tokens=route.budget.max_output_tokens,
                temperature=temperature,
                seed=seed,
                reasoning_effort=route.budget.reasoning_effort,
            )
            try:
                response = await self._provider.complete(request)
            except ProviderError as error:
                attempts.append(Attempt(model, 0, error.kind, None))
                if error.kind not in _FALLBACK_KINDS:
                    raise
                last_error = error
                continue
            attempts.append(Attempt(model, 0, None, response.latency_ms))
            return RouterResult(response, tuple(attempts), model != route.chain[0])
        assert last_error is not None  # a route chain is never empty
        raise last_error
