import pathlib

import pytest
from pydantic import ValidationError

from opportunity_radar.platform.ai.config import (
    AISettings,
    AIState,
    ai_status,
    configured_providers,
    excluded_providers,
)
from opportunity_radar.platform.config import Settings

_ENV_EXAMPLE = pathlib.Path(__file__).resolve().parents[4] / ".env.example"


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides)  # type: ignore[call-arg,arg-type]


def test_defaults_keep_cloud_ai_off() -> None:
    settings = _settings()

    assert settings.ai_enabled is False
    assert settings.ai_provider == "groq"
    assert settings.groq_api_key.get_secret_value() == ""
    assert settings.groq_reasoning_model == "openai/gpt-oss-120b"
    assert settings.groq_fast_model == "openai/gpt-oss-20b"
    assert settings.ai_reasoning_effort == "low"
    assert settings.ai_daily_requests_soft_limit == 850


def test_ai_status_in_the_three_states() -> None:
    assert ai_status(_settings()) is AIState.DISABLED
    assert ai_status(_settings(ai_enabled=True)) is AIState.BLOCKED_BY_CONFIGURATION
    assert ai_status(_settings(ai_enabled=True, groq_api_key="k")) is AIState.ENABLED


def test_missing_key_is_blocked_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    assert ai_status(_settings()) == "blocked_by_configuration"


@pytest.mark.parametrize("effort", ["low", "medium", "high"])
def test_accepts_supported_reasoning_effort(effort: str) -> None:
    assert _settings(ai_reasoning_effort=effort).ai_reasoning_effort == effort


def test_unknown_reasoning_effort_fails_at_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_REASONING_EFFORT", "extreme")

    with pytest.raises(ValidationError, match="AI_REASONING_EFFORT"):
        _settings()


def test_per_task_reasoning_effort_defaults_unset() -> None:
    settings = _settings()

    assert settings.ai_reasoning_effort_job_match is None
    assert settings.ai_reasoning_effort_job_classification is None
    assert settings.ai_reasoning_effort_job_extraction is None


@pytest.mark.parametrize(
    "field",
    [
        "ai_reasoning_effort_job_match",
        "ai_reasoning_effort_job_classification",
        "ai_reasoning_effort_job_extraction",
    ],
)
def test_per_task_reasoning_effort_accepts_supported_value(field: str) -> None:
    settings = _settings(**{field: "high"})

    assert getattr(settings, field) == "high"


@pytest.mark.parametrize(
    "field",
    [
        "ai_reasoning_effort_job_match",
        "ai_reasoning_effort_job_classification",
        "ai_reasoning_effort_job_extraction",
    ],
)
def test_per_task_reasoning_effort_unknown_value_fails_at_start(field: str) -> None:
    with pytest.raises(ValidationError, match=field.upper()):
        _settings(**{field: "extreme"})


def test_other_provider_fails_at_start() -> None:
    with pytest.raises(ValidationError, match="AI_PROVIDER"):
        _settings(ai_provider="openai")


@pytest.mark.parametrize(
    "field", ["ai_timeout_seconds", "ai_daily_tokens_soft_limit", "ai_breaker_failures"]
)
def test_non_positive_limit_fails_at_start(field: str) -> None:
    with pytest.raises(ValidationError, match=field.upper()):
        _settings(**{field: 0})


def test_negative_retries_fail_at_start() -> None:
    with pytest.raises(ValidationError, match="AI_MAX_RETRIES"):
        _settings(ai_max_retries=-1)


def test_interactive_reserve_defaults_below_the_daily_limit() -> None:
    settings = _settings()

    assert settings.ai_interactive_reserve_requests == 100
    assert settings.ai_interactive_reserve_requests < settings.ai_daily_requests_soft_limit


def test_interactive_reserve_at_or_above_the_daily_limit_fails_at_start() -> None:
    with pytest.raises(ValidationError, match="AI_INTERACTIVE_RESERVE_REQUESTS"):
        _settings(ai_interactive_reserve_requests=850)


def test_interactive_reserve_cannot_be_negative() -> None:
    with pytest.raises(ValidationError, match="AI_INTERACTIVE_RESERVE_REQUESTS"):
        _settings(ai_interactive_reserve_requests=-1)


def test_aging_sample_ratio_default() -> None:
    assert _settings().worker_analyze_aging_sample_ratio == 0.10


@pytest.mark.parametrize("ratio", [-0.1, 1.1])
def test_aging_sample_ratio_outside_zero_to_one_fails_at_start(ratio: float) -> None:
    with pytest.raises(ValidationError, match="WORKER_ANALYZE_AGING_SAMPLE_RATIO"):
        _settings(worker_analyze_aging_sample_ratio=ratio)


def test_key_never_appears_in_repr() -> None:
    settings = _settings(ai_enabled=True, groq_api_key="gsk-top-secret")

    assert "gsk-top-secret" not in repr(settings)
    assert "gsk-top-secret" not in repr(AISettings.from_settings(settings))
    assert AISettings.from_settings(settings).api_key.get_secret_value() == "gsk-top-secret"


@pytest.mark.skipif(not _ENV_EXAMPLE.exists(), reason=".env.example is not mounted")
def test_env_example_lists_every_new_variable() -> None:
    names = {
        line.split("=", 1)[0].strip()
        for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    expected = {name.upper() for name in Settings.model_fields if name.startswith(("ai_", "groq_"))}

    assert expected <= names
    assert "GROQ_API_KEY=" in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()


def test_ai_enabled_without_groq_when_a_reserve_has_key() -> None:
    from opportunity_radar.platform.ai.tasks import AITask, default_routes
    from opportunity_radar.platform.health import ai_health

    s = _settings(ai_enabled=True, cerebras_api_key="c")
    assert ai_status(s) is AIState.ENABLED
    assert all(m.startswith("cerebras:") for m in default_routes(s)[AITask.JOB_MATCH].chain)
    assert ai_health(s).status == "healthy"


def test_no_key_at_all_stays_blocked() -> None:
    from opportunity_radar.platform.health import ai_health

    assert ai_status(_settings(ai_enabled=True)) is AIState.BLOCKED_BY_CONFIGURATION
    assert ai_health(_settings(ai_enabled=True)).detail == "no ai provider key"


def test_workersai_without_account_id_is_left_out() -> None:
    from opportunity_radar.platform.ai.config import configured_providers

    s = _settings(workersai_api_key="w")
    assert configured_providers(s) == []
    assert ai_status(_settings(ai_enabled=True, workersai_api_key="w")) is (
        AIState.BLOCKED_BY_CONFIGURATION
    )


def test_workersai_url_gets_the_account_id() -> None:
    from opportunity_radar.platform.ai.config import configured_providers

    s = _settings(workersai_api_key="w", cloudflare_account_id="acc1")
    [(spec, key, url)] = configured_providers(s)
    assert spec.name == "workersai" and key == "w"
    assert url == "https://api.cloudflare.com/client/v4/accounts/acc1/ai/v1"
    assert "//ai" not in url


def test_configured_providers_follow_order_skip_unknown_and_keyless() -> None:
    from opportunity_radar.platform.ai.config import configured_providers

    s = _settings(
        cerebras_api_key="c",
        zen_api_key="z",
        mistral_api_key="m",
        ai_reserve_order="mistral, bogus,zen,cerebras,openrouter",
    )
    assert [spec.name for spec, _, _ in configured_providers(s)] == ["mistral", "zen", "cerebras"]


def test_provider_settings_default_empty_and_off() -> None:
    s = _settings()
    for name in ("cerebras", "zen", "gemini", "openrouter", "mistral", "nim", "workersai"):
        assert getattr(s, f"{name}_api_key").get_secret_value() == ""
    assert s.cloudflare_account_id == ""
    assert s.ai_provider_limits == {}


def test_provider_limits_parse_from_json_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_LIMITS", '{"zen": {"day_requests": 100}}')
    assert _settings().ai_provider_limits == {"zen": {"day_requests": 100}}


def test_keys_never_show_in_settings_repr() -> None:
    assert "secret-c" not in repr(_settings(cerebras_api_key="secret-c"))


def test_a_keyed_provider_missing_from_the_reserve_order_is_excluded_with_a_reason() -> None:
    settings = _settings(
        ai_reserve_order="zen", zen_api_key="z", cerebras_api_key="c", mistral_api_key=""
    )

    assert excluded_providers(settings) == {"cerebras": "fora de AI_RESERVE_ORDER"}
    assert [spec.name for spec, _, _ in configured_providers(settings)] == ["zen"]


@pytest.mark.parametrize("value", [0, -5, "many", 1.5])
def test_provider_limit_values_must_be_positive_integers(value: object) -> None:
    with pytest.raises(ValidationError):
        _settings(ai_provider_limits={"zen": {"day_requests": value}})


def test_unknown_provider_limit_names_and_fields_are_still_ignored() -> None:
    settings = _settings(
        ai_provider_limits={"nope": {"day_requests": 5}, "zen": {"typo": 5, "day_requests": 100}}
    )

    assert settings.ai_provider_limits["zen"]["day_requests"] == 100
