"""Runs one AI task through its model chain (SPEC 43, section 6 and 7).

Each model is tried, with retry and repair inside the model and fallback across the
chain (F20-10); a circuit breaker skips a model that keeps failing (F20-11); a quota
guard reserves budget before every call and skips a model with no balance (F20-12).
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMProvider, LLMRequest, LLMResponse
from opportunity_radar.platform.ai.quota import QuotaGuard, Reservation
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute

#: `blocked_until` when the whole chain is rate limited and no header gave a better hint.
_DEFAULT_QUOTA_COOLDOWN_SECONDS = 60.0

_REPAIR_SUFFIX = (
    "\n\nA resposta anterior foi rejeitada: {summary}. Responda só com JSON válido no schema."
)


@dataclass(frozen=True)
class Attempt:
    model: str
    attempt: int  # 0 = first attempt on that model
    error_kind: ErrorKind | None
    latency_ms: int | None
    http_status: int | None = None


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
        max_retries: int = 2,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
        validator: Callable[[str], None] | None = None,
        breaker: CircuitBreaker | None = None,
        quota_guard: QuotaGuard | None = None,
    ) -> None:
        self._provider = provider
        self._routes = dict(routes)
        self._fallback_enabled = fallback_enabled
        self._max_retries = max_retries
        self._sleeper = sleeper
        self._jitter = jitter
        self._clock = clock
        self._validator = validator
        self._breaker = breaker if breaker is not None else CircuitBreaker(clock=clock)
        self._quota_guard = quota_guard
        # model -> monotonic clock() value until which the model is skipped (429, or no
        # quota balance). Separate from the breaker: only transient failures open that one.
        self._blocked_until: dict[str, float] = {}

    def route(self, task: AITask) -> ModelRoute:
        return self._routes[task]

    @property
    def breaker(self) -> CircuitBreaker:
        """The live per-model breaker (card F20-20 reads its `snapshot()` for metrics)."""
        return self._breaker

    @property
    def quota_guard(self) -> QuotaGuard | None:
        """`None` only when this router was built without persistent quota tracking."""
        return self._quota_guard

    def _is_blocked(self, model: str) -> bool:
        until = self._blocked_until.get(model)
        return until is not None and until > self._clock()

    async def _wait_before_retry(self, attempt: int) -> None:
        # `attempt` is 1-based here: the wait before retry n is 2**(n-1) * (1 + jitter()/4).
        seconds = (2 ** (attempt - 1)) * (1 + self._jitter() / 4)
        await self._sleeper(seconds)

    async def _reserve(self, model: str, estimated_tokens: int) -> Reservation | None:
        if self._quota_guard is None:
            return None
        return await asyncio.to_thread(self._quota_guard.reserve, model, estimated_tokens)

    async def _settle(
        self, reservation: Reservation | None, response: LLMResponse | None
    ) -> None:
        if self._quota_guard is None or reservation is None:
            return
        actual_tokens = None
        rate_limit = None
        if response is not None:
            usage = response.usage
            if usage.prompt_tokens is not None and usage.completion_tokens is not None:
                actual_tokens = usage.prompt_tokens + usage.completion_tokens
            rate_limit = response.rate_limit
        await asyncio.to_thread(self._quota_guard.settle, reservation, actual_tokens, rate_limit)

    async def _release(self, reservation: Reservation | None) -> None:
        if self._quota_guard is None or reservation is None:
            return
        await asyncio.to_thread(self._quota_guard.release, reservation)

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
        estimated_input_tokens: int | None = None,
    ) -> RouterResult:
        route = self.route(task)
        chain = route.chain if self._fallback_enabled else route.chain[:1]
        estimated_input = (
            estimated_input_tokens
            if estimated_input_tokens is not None
            else len(system + user) // 3
        )
        estimated_total = estimated_input + route.budget.max_output_tokens
        attempts: list[Attempt] = []
        last_error: ProviderError | None = None
        any_model_tried = False
        for model in chain:
            if self._is_blocked(model) or not self._breaker.allow(model):
                continue
            any_model_tried = True
            current_user = user
            repaired_once = False
            attempt_index = 0
            while True:
                reservation = await self._reserve(model, estimated_total)
                if reservation is None and self._quota_guard is not None:
                    self._blocked_until[model] = self._clock_to_deadline(model)
                    last_error = ProviderError(
                        ErrorKind.QUOTA, "no quota balance", model=model
                    )
                    break
                try:
                    request = LLMRequest(
                        model=model,
                        system=system,
                        user=current_user,
                        schema_name=schema_name,
                        json_schema=json_schema,
                        max_completion_tokens=route.budget.max_output_tokens,
                        temperature=temperature,
                        seed=seed,
                        reasoning_effort=route.budget.reasoning_effort,
                    )
                    response = await self._provider.complete(request)
                    if self._validator is not None:
                        self._validator(response.content)
                except ProviderError as error:
                    attempts.append(
                        Attempt(model, attempt_index, error.kind, None, error.status)
                    )
                    last_error = error
                    if error.kind is ErrorKind.CONFIGURATION or error.kind is ErrorKind.REQUEST:
                        await self._release(reservation)
                        error.attempts = tuple(attempts)
                        raise
                    if error.kind is ErrorKind.TRANSIENT:
                        self._breaker.record_failure(model)
                        await self._release(reservation)
                        if attempt_index >= self._max_retries:
                            break
                        attempt_index += 1
                        await self._wait_before_retry(attempt_index)
                        continue
                    if error.kind is ErrorKind.QUOTA:
                        await self._settle(reservation, None)
                        retry_after = error.retry_after_seconds or _DEFAULT_QUOTA_COOLDOWN_SECONDS
                        self._blocked_until[model] = self._clock() + retry_after
                        break
                    if error.kind is ErrorKind.INVALID_OUTPUT:
                        await self._settle(reservation, None)
                        if repaired_once:
                            break
                        repaired_once = True
                        current_user = current_user + _REPAIR_SUFFIX.format(summary=error.summary)
                        attempt_index += 1
                        continue
                    raise
                else:
                    self._breaker.record_success(model)
                    await self._settle(reservation, response)
                    attempts.append(
                        Attempt(model, attempt_index, None, response.latency_ms, 200)
                    )
                    return RouterResult(response, tuple(attempts), model != route.chain[0])
        if not any_model_tried:
            soonest = min(self._blocked_until.values(), default=self._clock())
            no_quota_error = ProviderError(
                ErrorKind.QUOTA,
                "all models rate limited",
                retry_after_seconds=max(0.0, soonest - self._clock()),
            )
            no_quota_error.attempts = tuple(attempts)
            raise no_quota_error
        assert last_error is not None  # a route chain is never empty
        last_error.attempts = tuple(attempts)
        raise last_error

    def _clock_to_deadline(self, model: str) -> float:
        """`blocked_until` (this router's `clock`) for a model with no quota balance.

        `QuotaGuard.next_available_at` answers in wall-clock time (it persists across
        restarts); the router's own `clock` may be a fake monotonic clock in tests. The
        two are bridged through a real-time delta, which is exact under the real clock
        and a documented best effort under a fake one.
        """
        if self._quota_guard is None:
            return self._clock() + _DEFAULT_QUOTA_COOLDOWN_SECONDS
        next_available = self._quota_guard.next_available_at(model)
        delta_seconds = (next_available - datetime.now(UTC)).total_seconds()
        return self._clock() + max(0.0, delta_seconds)
