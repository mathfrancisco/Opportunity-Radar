import asyncio
from collections.abc import Awaitable, Callable

import pytest

from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.router import AIRouter, RouterResult
from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.config import Settings

from .fakes import FakeProvider, response

_SCHEMA = {"type": "object"}
_REASONING = "openai/gpt-oss-120b"
_FAST = "openai/gpt-oss-20b"
_ALT = "qwen/qwen3.8-27b"


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides)  # type: ignore[call-arg,arg-type]


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def _recording_sleeper() -> tuple[Callable[[float], Awaitable[None]], list[float]]:
    waits: list[float] = []

    async def sleeper(seconds: float) -> None:
        waits.append(seconds)

    return sleeper, waits


def _router(
    provider: FakeProvider,
    *,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
    jitter: Callable[[], float] | None = None,
    clock: Callable[[], float] | None = None,
    breaker: CircuitBreaker | None = None,
    **overrides: object,
) -> AIRouter:
    settings = _settings(**overrides)
    kwargs: dict[str, object] = {
        "fallback_enabled": settings.ai_fallback_enabled,
        "max_retries": settings.ai_max_retries,
    }
    if sleeper is not None:
        kwargs["sleeper"] = sleeper
    if jitter is not None:
        kwargs["jitter"] = jitter
    if clock is not None:
        kwargs["clock"] = clock
    if breaker is not None:
        kwargs["breaker"] = breaker
    return AIRouter(provider, default_routes(settings), **kwargs)  # type: ignore[arg-type]


def _run(router: AIRouter, task: AITask = AITask.JOB_MATCH) -> RouterResult:
    return asyncio.run(
        router.run(task, system="s", user="u", schema_name="analysis_v1", json_schema=_SCHEMA)
    )


def test_first_model_success() -> None:
    provider = FakeProvider({_REASONING: [response(_REASONING)]})

    result = _run(_router(provider))

    assert result.response.model == _REASONING
    assert result.fallback_used is False
    assert [(a.model, a.attempt, a.error_kind, a.latency_ms) for a in result.attempts] == [
        (_REASONING, 0, None, 10)
    ]


def test_reasoning_model_setting_changes_job_match_model() -> None:
    provider = FakeProvider({"custom/model": [response("custom/model")]})

    _run(_router(provider, groq_reasoning_model="custom/model"))

    assert provider.models_called() == ["custom/model"]


def test_429_not_retried_same_model() -> None:
    provider = FakeProvider(
        {_REASONING: [ProviderError(ErrorKind.QUOTA, "429")], _ALT: [response(_ALT)]}
    )

    result = _run(_router(provider))

    assert provider.models_called() == [_REASONING, _ALT]
    assert result.fallback_used is True
    assert [a.error_kind for a in result.attempts] == [ErrorKind.QUOTA, None]


@pytest.mark.parametrize("kind", [ErrorKind.CONFIGURATION, ErrorKind.REQUEST])
def test_configuration_error_stops_chain(kind: ErrorKind) -> None:
    provider = FakeProvider(
        {_REASONING: [ProviderError(kind, "unauthorized", status=401)], _ALT: [response(_ALT)]}
    )

    with pytest.raises(ProviderError) as raised:
        _run(_router(provider))

    assert raised.value.kind is kind
    assert provider.models_called() == [_REASONING]


def test_fallback_disabled_uses_first_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_FALLBACK_ENABLED", "false")
    provider = FakeProvider(
        {_REASONING: [ProviderError(ErrorKind.QUOTA, "429")], _ALT: [response(_ALT)]}
    )

    with pytest.raises(ProviderError):
        _run(_router(provider))

    assert provider.models_called() == [_REASONING]


def test_all_fail_raises_last_error() -> None:
    # max_retries=0 keeps this to one failure per model, same as before F20-10 retries.
    last = ProviderError(ErrorKind.TRANSIENT, "second")
    provider = FakeProvider({_REASONING: [ProviderError(ErrorKind.QUOTA, "first")], _ALT: [last]})

    with pytest.raises(ProviderError) as raised:
        _run(_router(provider, ai_max_retries=0))

    assert raised.value is last


def test_budget_applied_to_request() -> None:
    provider = FakeProvider({_FAST: [response(_FAST)]})

    _run(_router(provider, ai_reasoning_effort="medium"), AITask.JOB_CLASSIFICATION)

    (request,) = provider.requests
    assert request.max_completion_tokens == 300
    assert request.reasoning_effort == "medium"


def test_default_routes_chains_and_budgets() -> None:
    routes = default_routes(_settings())

    assert routes[AITask.JOB_MATCH].chain == (_REASONING, _ALT)
    assert routes[AITask.JOB_CLASSIFICATION].chain == (_FAST, _ALT)
    assert routes[AITask.JOB_EXTRACTION].chain == (_FAST, _REASONING)
    budgets = {
        task: (r.budget.max_input_tokens, r.budget.max_output_tokens) for task, r in routes.items()
    }
    assert budgets == {
        AITask.JOB_MATCH: (5000, 900),
        AITask.JOB_CLASSIFICATION: (1500, 300),
        AITask.JOB_EXTRACTION: (3000, 600),
    }


def test_unknown_task_raises_keyerror() -> None:
    router = AIRouter(FakeProvider({}), {})

    with pytest.raises(KeyError):
        router.route(AITask.JOB_MATCH)


# --- F20-10: retry with jitter, fallback, blocked_until, invalid-output repair --------


def test_transient_retried_then_success() -> None:
    sleeper, waits = _recording_sleeper()
    provider = FakeProvider(
        {
            _REASONING: [
                ProviderError(ErrorKind.TRANSIENT, "timeout"),
                ProviderError(ErrorKind.TRANSIENT, "timeout"),
                response(_REASONING),
            ]
        }
    )

    result = _run(_router(provider, sleeper=sleeper, jitter=lambda: 0.0, ai_max_retries=2))

    assert provider.models_called() == [_REASONING, _REASONING, _REASONING]
    assert result.fallback_used is False
    assert [a.error_kind for a in result.attempts] == [
        ErrorKind.TRANSIENT,
        ErrorKind.TRANSIENT,
        None,
    ]
    assert waits == [1.0, 2.0]  # jitter=0 => 2**(n-1) * 1


def test_backoff_sequence_with_jitter() -> None:
    sleeper, waits = _recording_sleeper()
    provider = FakeProvider(
        {
            _REASONING: [
                ProviderError(ErrorKind.TRANSIENT, "timeout"),
                ProviderError(ErrorKind.TRANSIENT, "timeout"),
                ProviderError(ErrorKind.TRANSIENT, "timeout"),
            ],
            _ALT: [response(_ALT)],
        }
    )

    _run(_router(provider, sleeper=sleeper, jitter=lambda: 0.4, ai_max_retries=2))

    factor = 1 + 0.4 / 4
    assert waits == [1 * factor, 2 * factor]


def test_call_ceiling() -> None:
    # len(chain) * (1 + max_retries) = 2 * 3 = 6, all transient.
    sleeper, _ = _recording_sleeper()
    provider = FakeProvider(
        {
            _REASONING: [ProviderError(ErrorKind.TRANSIENT, "x") for _ in range(3)],
            _ALT: [ProviderError(ErrorKind.TRANSIENT, "x") for _ in range(3)],
        }
    )

    with pytest.raises(ProviderError):
        _run(_router(provider, sleeper=sleeper, jitter=lambda: 0.0, ai_max_retries=2))

    assert len(provider.requests) == 6


def test_blocked_model_skipped_until_retry_after() -> None:
    clock = _FakeClock()
    provider = FakeProvider(
        {
            _REASONING: [
                ProviderError(ErrorKind.QUOTA, "429", retry_after_seconds=30),
                response(_REASONING),
            ],
            _ALT: [response(_ALT), response(_ALT)],
        }
    )
    router = _router(provider, clock=clock)

    first = _run(router)
    assert first.response.model == _ALT  # REASONING 429'd, fell back

    clock.now = 10.0
    second = _run(router)
    assert second.response.model == _ALT  # still inside the 30s cooldown, skipped

    clock.now = 31.0
    third = _run(router)
    assert third.response.model == _REASONING  # cooldown elapsed, tried again


def test_invalid_output_repaired_once() -> None:
    provider = FakeProvider(
        {_REASONING: [ProviderError(ErrorKind.INVALID_OUTPUT, "bad json"), response(_REASONING)]}
    )

    result = _run(_router(provider))

    assert result.fallback_used is False
    assert provider.models_called() == [_REASONING, _REASONING]
    (first_request, second_request) = provider.requests
    assert "A resposta anterior foi rejeitada" in second_request.user
    assert "bad json" in second_request.user
    assert first_request.user == "u"


def test_invalid_output_twice_moves_on() -> None:
    provider = FakeProvider(
        {
            _REASONING: [
                ProviderError(ErrorKind.INVALID_OUTPUT, "bad json"),
                ProviderError(ErrorKind.INVALID_OUTPUT, "still bad"),
            ],
            _ALT: [response(_ALT)],
        }
    )

    result = _run(_router(provider))

    assert result.response.model == _ALT
    assert provider.models_called() == [_REASONING, _REASONING, _ALT]


def test_all_models_blocked_raises_quota() -> None:
    clock = _FakeClock()
    provider = FakeProvider(
        {
            _REASONING: [ProviderError(ErrorKind.QUOTA, "429", retry_after_seconds=20)],
            _ALT: [ProviderError(ErrorKind.QUOTA, "429", retry_after_seconds=5)],
        }
    )
    router = _router(provider, clock=clock)
    with pytest.raises(ProviderError):
        _run(router)  # populates blocked_until for both models

    with pytest.raises(ProviderError) as raised:
        _run(router)

    assert raised.value.kind is ErrorKind.QUOTA
    assert "rate limited" in raised.value.summary
    assert provider.models_called() == [_REASONING, _ALT]  # no third/fourth call this time


# --- F20-11: circuit breaker per model -------------------------------------------------


def test_router_skips_open_model() -> None:
    breaker = CircuitBreaker(failures=1, cooldown_seconds=120)
    breaker.record_failure(_REASONING)  # already open before the router ever calls it
    provider = FakeProvider({_ALT: [response(_ALT)]})

    result = _run(_router(provider, breaker=breaker, ai_max_retries=0))

    assert result.response.model == _ALT
    assert provider.models_called() == [_ALT]
