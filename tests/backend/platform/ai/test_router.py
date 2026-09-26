import asyncio

import pytest

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


def _router(provider: FakeProvider, **overrides: object) -> AIRouter:
    settings = _settings(**overrides)
    return AIRouter(
        provider, default_routes(settings), fallback_enabled=settings.ai_fallback_enabled
    )


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


@pytest.mark.parametrize("kind", [ErrorKind.QUOTA, ErrorKind.TRANSIENT, ErrorKind.INVALID_OUTPUT])
def test_quota_moves_to_next_model(kind: ErrorKind) -> None:
    provider = FakeProvider({_REASONING: [ProviderError(kind, "fail")], _ALT: [response(_ALT)]})

    result = _run(_router(provider))

    assert provider.models_called() == [_REASONING, _ALT]
    assert result.fallback_used is True
    assert [a.error_kind for a in result.attempts] == [kind, None]


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
    last = ProviderError(ErrorKind.TRANSIENT, "second")
    provider = FakeProvider({_REASONING: [ProviderError(ErrorKind.QUOTA, "first")], _ALT: [last]})

    with pytest.raises(ProviderError) as raised:
        _run(_router(provider))

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
