import pathlib

import pytest
from pydantic import ValidationError

from opportunity_radar.platform.ai.config import AISettings, AIState, ai_status
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
