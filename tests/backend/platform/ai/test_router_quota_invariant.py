"""F51-09: a quota reservation never outlives the call that made it.

Matrix over the real `AIRouter` and the real `QuotaGuard` (Postgres) with a fake
provider. Invariant, checked after `run` returns or raises, for every model of a
4-model chain: the `requests` and `tokens` left in `platform.ai_quota_usage` are
explained by the `Attempt`s the result or the error carries (one request per attempt
that started transport; its real usage when known, the reservation estimate when not)
-- and nothing else stays reserved.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import (
    LLMRequest,
    LLMResponse,
    RateLimit,
    Usage,
)
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.providers.routed import RoutedProvider
from opportunity_radar.platform.ai.providers.tokenharbor import MODEL_PREFIX, TokenHarborProvider
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits, Reservation
from opportunity_radar.platform.ai.router import AIRouter, Attempt
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute, TaskBudget
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

CHAIN = ("m0", "m1", "m2", "m3")
_ESTIMATED_INPUT = 1000
_MAX_OUTPUT = 300
_ESTIMATE = _ESTIMATED_INPUT + _MAX_OUTPUT
_USAGE_TOKENS = 120 + 30
_NOW = datetime(2026, 10, 6, 12, 30, 0, tzinfo=UTC)
_ROUTE = ModelRoute(AITask.JOB_CLASSIFICATION, CHAIN, TaskBudget(1500, _MAX_OUTPUT, "low"))
_NO_RATE_LIMIT = RateLimit(None, None, None, None, None, None)


def _response(model: str, content: str = "good") -> LLMResponse:
    return LLMResponse(
        model=model,
        content=content,
        usage=Usage(prompt_tokens=120, completion_tokens=30, prompt_ms=None, completion_ms=None),
        rate_limit=_NO_RATE_LIMIT,
        latency_ms=5,
        finish_reason="stop",
    )


def _engine() -> Engine:
    return create_database_engine(os.environ["DATABASE_URL"])


def _limits() -> QuotaLimits:
    return QuotaLimits(
        minute_requests=10_000, minute_tokens=10_000_000,
        day_requests=10_000, day_tokens=10_000_000,
    )


def _counters(engine: Engine) -> dict[tuple[str, str], tuple[int, int]]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT model, window_kind, requests, tokens FROM platform.ai_quota_usage")
        ).all()
    return {(row.model, row.window_kind): (row.requests, row.tokens) for row in rows}


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_quota_usage"))


# --- scripted provider ----------------------------------------------------------------


class Step:
    """What one provider call does. `repeat` steps answer every call to that model."""

    def __init__(
        self,
        kind: str,
        *,
        error_kind: ErrorKind | None = None,
        transport_started: bool = True,
        usage: bool = False,
        content: str = "good",
    ) -> None:
        self.kind = kind
        self.error_kind = error_kind
        self.transport_started = transport_started
        self.usage = usage
        self.content = content

    def __repr__(self) -> str:
        if self.kind == "error":
            return (
                f"error[{self.error_kind}, transport={self.transport_started}, "
                f"usage={self.usage}]"
            )
        if self.kind == "cancel":
            return f"cancel[transport={self.transport_started}]"
        return self.kind


SUCCESS = Step("success")
#: A model that fails the way a rate limited one does, so the chain moves on.
FALL_THROUGH = Step("error", error_kind=ErrorKind.QUOTA, transport_started=True, usage=True)


class MatrixProvider:
    name = "fake"

    def __init__(self, steps: dict[str, list[Step]]) -> None:
        self._steps = {model: list(items) for model, items in steps.items()}
        self.calls: list[str] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request.model)
        items = self._steps[request.model]
        step = items.pop(0) if len(items) > 1 else items[0]  # the last step repeats
        if step.kind == "success":
            return _response(request.model, step.content)
        if step.kind == "cancel":
            cancellation = asyncio.CancelledError()
            cancellation.transport_started = step.transport_started  # type: ignore[attr-defined]
            raise cancellation
        assert step.error_kind is not None
        error = ProviderError(
            step.error_kind, "boom", model=request.model,
            transport_started=step.transport_started,
            status=500 if step.transport_started else None,
            latency_ms=7 if step.transport_started else None,
            prompt_tokens=120 if step.usage else None,
            completion_tokens=30 if step.usage else None,
        )
        raise error


def _validator(content: str) -> None:
    if content == "bad":
        raise ProviderError(ErrorKind.INVALID_OUTPUT, "not json")


async def _no_sleep(_: float) -> None:
    return None


def _router(provider: MatrixProvider, guard: QuotaGuard) -> AIRouter:
    return AIRouter(
        provider, {AITask.JOB_CLASSIFICATION: _ROUTE},
        max_retries=2, sleeper=_no_sleep, validator=_validator, quota_guard=guard,
    )


def _run_router(router: AIRouter, on_attempt_started: Any = None) -> Any:
    """The `RouterResult`, or the exception `run` raised."""

    async def go() -> Any:
        try:
            return await router.run(
                AITask.JOB_CLASSIFICATION, system="s", user="u", schema_name="s",
                json_schema={"type": "object"}, estimated_input_tokens=_ESTIMATED_INPUT,
                on_attempt_started=on_attempt_started,
            )
        except (ProviderError, asyncio.CancelledError) as error:
            return error

    return asyncio.run(go())


def _attempts_of(outcome: Any) -> tuple[Attempt, ...]:
    return tuple(getattr(outcome, "attempts", ()))


def _assert_invariant(
    engine: Engine, attempts: tuple[Attempt, ...], *, chain: tuple[str, ...] = CHAIN
) -> None:
    expected: dict[str, tuple[int, int]] = {}
    for attempt in attempts:
        if not attempt.transport_started:
            continue
        requests, tokens = expected.get(attempt.model, (0, 0))
        known = attempt.prompt_tokens is not None and attempt.completion_tokens is not None
        expected[attempt.model] = (
            requests + 1,
            tokens + (attempt.prompt_tokens + attempt.completion_tokens if known else _ESTIMATE),  # type: ignore[operator]
        )
    stored = _counters(engine)
    for model in chain:
        for window in ("minute", "day"):
            got = stored.get((model, window), (0, 0))
            assert got == expected.get(model, (0, 0)), (
                f"{model}/{window}: requests,tokens={got} but attempts explain "
                f"{expected.get(model, (0, 0))}; "
                f"attempts={[(a.model, a.error_kind) for a in attempts]}"
            )


# --- the matrix -----------------------------------------------------------------------


def _error_steps() -> list[tuple[str, Step]]:
    steps: list[tuple[str, Step]] = [("success", SUCCESS)]
    for kind in ErrorKind:
        for transport_started, usage in ((False, False), (True, False), (True, True)):
            steps.append((
                f"{kind.value}-transport{int(transport_started)}-usage{int(usage)}",
                Step("error", error_kind=kind, transport_started=transport_started, usage=usage),
            ))
    steps.append(("invalid-output-then-repair", Step("success", content="bad")))
    steps.append(("cancel-before-transport", Step("cancel", transport_started=False)))
    steps.append(("cancel-after-transport", Step("cancel", transport_started=True)))
    return steps


def _script(position: int, step: Step) -> dict[str, list[Step]]:
    script: dict[str, list[Step]] = {}
    for index, model in enumerate(CHAIN):
        if index < position:
            script[model] = [FALL_THROUGH]
        elif index == position:
            script[model] = [step]
        else:
            script[model] = [SUCCESS]
    if step.kind == "success" and step.content == "bad":
        script[CHAIN[position]] = [step, SUCCESS]  # the repair turn answers
    return script


@pytest.mark.parametrize("position", range(len(CHAIN)))
@pytest.mark.parametrize(("label", "step"), _error_steps(), ids=lambda value: str(value)[:60])
def test_quota_counters_are_explained_by_attempts(
    position: int, label: str, step: Step
) -> None:
    del label
    engine = _engine()
    _reset(engine)
    guard = QuotaGuard(engine, _limits(), now=lambda: _NOW)
    provider = MatrixProvider(_script(position, step))

    outcome = _run_router(_router(provider, guard))

    _assert_invariant(engine, _attempts_of(outcome))


# --- cancellation while the reservation itself is being made --------------------------


class _GatedGuard(QuotaGuard):
    """Commits the real reservation for `gated_model`, then holds the thread."""

    def __init__(self, *args: Any, gated_model: str, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._gated_model = gated_model
        self.reserved = threading.Event()
        self.gate = threading.Event()

    def reserve(
        self, model: str, estimated_tokens: int, *, ceiling_requests: int | None = None
    ) -> Reservation | None:
        reservation = super().reserve(
            model, estimated_tokens, ceiling_requests=ceiling_requests
        )
        if model == self._gated_model:
            self.reserved.set()
            self.gate.wait(timeout=10)
        return reservation


@pytest.mark.parametrize("position", range(len(CHAIN)))
def test_cancellation_during_reserve_leaves_nothing_reserved(position: int) -> None:
    engine = _engine()
    _reset(engine)
    guard = _GatedGuard(engine, _limits(), now=lambda: _NOW, gated_model=CHAIN[position])
    provider = MatrixProvider(_script(position, SUCCESS))
    router = _router(provider, guard)

    async def go() -> Any:
        task = asyncio.ensure_future(router.run(
            AITask.JOB_CLASSIFICATION, system="s", user="u", schema_name="s",
            json_schema={"type": "object"}, estimated_input_tokens=_ESTIMATED_INPUT,
        ))
        await asyncio.to_thread(guard.reserved.wait, 10)
        task.cancel()
        await asyncio.sleep(0)  # the cancellation reaches the awaiting `run`
        guard.gate.set()
        try:
            await task
        except asyncio.CancelledError as error:
            return error
        return None

    outcome = asyncio.run(go())

    assert isinstance(outcome, asyncio.CancelledError)
    assert CHAIN[position] not in provider.calls
    _assert_invariant(engine, _attempts_of(outcome))



# --- the production providers (Groq + Token Harbor over an in-memory transport) -------

_GOOD_BODY = {
    "model": "x",
    "choices": [{"message": {"content": "good"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 120, "completion_tokens": 30},
}
_USAGE_ONLY = {"usage": {"prompt_tokens": 120, "completion_tokens": 30}}


async def _cancelled_handler(request: httpx.Request) -> httpx.Response:
    raise asyncio.CancelledError


def _raises(error: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    return handler


def _status(
    code: int, body: dict[str, Any] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(code, json=body or {})


_HTTP_BEHAVIOURS: dict[str, Callable[[httpx.Request], Any]] = {
    "200-ok": _status(200, _GOOD_BODY),
    "200-no-content": _status(200, {"choices": [{"message": {"content": ""}}], **_USAGE_ONLY}),
    "200-malformed-choices": _status(200, {"choices": "nope", **_USAGE_ONLY}),
    "400": _status(400),
    "400-usage": _status(400, _USAGE_ONLY),
    "401": _status(401),
    "429": _status(429),
    "429-usage": _status(429, _USAGE_ONLY),
    "500": _status(500),
    "500-usage": _status(500, _USAGE_ONLY),
    "read-timeout": _raises(httpx.ReadTimeout("slow")),
    "connect-error": _raises(httpx.ConnectError("down")),
    "cancelled-mid-request": _cancelled_handler,
}


def _http_provider(behaviours: dict[str, Callable[[httpx.Request], Any]]) -> RoutedProvider:
    def handler(request: httpx.Request) -> Any:
        model = json.loads(request.content)["model"]
        return behaviours[model](request)

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    groq = GroqProvider(api_key="k", base_url="http://groq.test", client_factory=factory)
    harbor = TokenHarborProvider(
        api_key="k", base_url="http://harbor.test", client_factory=factory
    )
    return RoutedProvider(groq, {MODEL_PREFIX: harbor})


_HTTP_CHAIN = ("g0", "g1", MODEL_PREFIX + "t2", MODEL_PREFIX + "t3")


@pytest.mark.parametrize("position", range(len(_HTTP_CHAIN)))
@pytest.mark.parametrize("label", list(_HTTP_BEHAVIOURS))
def test_http_providers_leave_no_reservation_unexplained(position: int, label: str) -> None:
    engine = _engine()
    _reset(engine)
    guard = QuotaGuard(engine, _limits(), now=lambda: _NOW)
    behaviours: dict[str, Callable[[httpx.Request], Any]] = {}
    for index, model in enumerate(_HTTP_CHAIN):
        wire = model.removeprefix(MODEL_PREFIX)
        if index < position:
            behaviours[wire] = _HTTP_BEHAVIOURS["429-usage"]
        elif index == position:
            behaviours[wire] = _HTTP_BEHAVIOURS[label]
        else:
            behaviours[wire] = _HTTP_BEHAVIOURS["200-ok"]
    route = ModelRoute(AITask.JOB_CLASSIFICATION, _HTTP_CHAIN, _ROUTE.budget)
    router = AIRouter(
        _http_provider(behaviours), {AITask.JOB_CLASSIFICATION: route},
        max_retries=2, sleeper=_no_sleep, validator=_validator, quota_guard=guard,
    )
    started: list[tuple[int, str]] = []

    async def on_started(operation_id: Any, ordinal: int, model: str, attempt: int) -> None:
        started.append((ordinal, model))

    outcome = _run_router(router, on_started)

    attempts = _attempts_of(outcome)
    _assert_invariant(engine, attempts, chain=_HTTP_CHAIN)
    # every attempt the router counts opened its call record at the transport boundary
    assert sorted(started) == sorted(
        (attempt.operation_ordinal, attempt.model)
        for attempt in attempts
        if attempt.transport_started
    )


# --- a rejected reservation holds nothing in either window ----------------------------


@pytest.mark.parametrize("exhausted_window", ["minute", "day"])
def test_rejected_reserve_leaves_both_windows_untouched(exhausted_window: str) -> None:
    engine = _engine()
    _reset(engine)
    limits = QuotaLimits(
        minute_requests=1 if exhausted_window == "minute" else 10_000,
        minute_tokens=10_000_000,
        day_requests=1 if exhausted_window == "day" else 10_000,
        day_tokens=10_000_000,
    )
    guard = QuotaGuard(engine, limits, now=lambda: _NOW)
    assert guard.reserve("m0", _ESTIMATE) is not None
    # Free the window that is not under test so only `exhausted_window` rejects.
    other = "day" if exhausted_window == "minute" else "minute"
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE platform.ai_quota_usage SET requests = 0, tokens = 0 "
                "WHERE window_kind = :window"
            ),
            {"window": other},
        )
    before = _counters(engine)

    assert guard.reserve("m0", _ESTIMATE) is None

    assert _counters(engine) == before
