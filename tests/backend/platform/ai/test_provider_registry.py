"""The provider registry and the generic OpenAI-compatible client it drives."""

import asyncio
from dataclasses import replace
from typing import Any

import httpx
import pytest

from opportunity_radar.platform.ai.errors import ProviderError
from opportunity_radar.platform.ai.providers.base import LLMRequest
from opportunity_radar.platform.ai.providers.openai_compat import OpenAICompatibleProvider
from opportunity_radar.platform.ai.providers.registry import (
    PROVIDERS,
    TOKENHARBOR,
    limits_for_model,
    provider_name_for,
    spec_for_model,
)
from opportunity_radar.platform.ai.quota import QuotaLimits
from opportunity_radar.platform.config import Settings

_KEY = "thk_live_test-key"


def _request(model: str) -> LLMRequest:
    return LLMRequest(
        model=model,
        system="system",
        user="user",
        schema_name="check",
        json_schema={"type": "object"},
        reasoning_effort="low",
    )


def _provider(spec: Any = TOKENHARBOR, **kwargs: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        spec,
        api_key=kwargs.pop("api_key", "k"),
        base_url="https://h/v1",
        timeout_seconds=1,
        connect_timeout_seconds=1,
        **kwargs,
    )


def test_registry_holds_token_harbor() -> None:
    assert TOKENHARBOR in PROVIDERS
    assert TOKENHARBOR.prefix == "tokenharbor:"
    assert TOKENHARBOR.may_retain_prompts is True


def test_spec_for_model_matches_prefix_only() -> None:
    spec = spec_for_model("tokenharbor:deepseek-v4.1-flash:free")
    assert spec is not None and spec.name == "tokenharbor"
    assert spec_for_model("openai/gpt-oss-120b") is None
    assert provider_name_for("tokenharbor:m") == "tokenharbor"
    assert provider_name_for("openai/gpt-oss-120b") == "groq"


def test_body_strips_prefix_and_groq_only_fields() -> None:
    spec = replace(TOKENHARBOR, prefix="x:")
    body = _provider(spec)._body(_request("x:openai/gpt-oss-120b"))
    assert body["model"] == "openai/gpt-oss-120b"
    assert "include_reasoning" not in body and "reasoning_format" not in body
    assert body["response_format"]["type"] == "json_schema"
    qwen = _provider(spec)._body(_request("x:qwen/qwen3-32b"))
    assert "reasoning_format" not in qwen


def test_json_object_spec_sends_plain_json_object() -> None:
    spec = replace(TOKENHARBOR, response_format="json_object", reasoning_effort=False)
    body = _provider(spec)._body(_request("tokenharbor:m"))
    assert body["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in body


def test_error_summary_redacts_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad key {_KEY}")

    provider = _provider(
        api_key=_KEY,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.complete(_request("tokenharbor:m")))
    assert _KEY not in str(caught.value)
    assert _KEY not in repr(provider)


def test_registry_has_the_eight_prefixes() -> None:
    assert [spec.prefix for spec in PROVIDERS] == [
        "tokenharbor:", "cerebras:", "zen:", "gemini:",
        "openrouter:", "mistral:", "nim:", "workersai:",
    ]  # fmt: skip


def test_build_provider_without_groq_key_routes_only_by_prefix() -> None:
    from opportunity_radar.platform.ai.providers.routed import build_provider
    from opportunity_radar.platform.config import Settings

    s = Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql+psycopg://u@h/db",
        cerebras_api_key="c",
        zen_api_key="z",
    )
    provider = build_provider(s)
    assert provider.name == "cerebras+zen"
    assert provider.backend_for("zen:m").name == "zen"  # type: ignore[attr-defined]


def test_build_provider_groq_only_is_plain_groq() -> None:
    from opportunity_radar.platform.ai.providers.groq import GroqProvider
    from opportunity_radar.platform.ai.providers.routed import build_provider
    from opportunity_radar.platform.config import Settings

    s = Settings(_env_file=None, database_url="postgresql+psycopg://u@h/db", groq_api_key="g")  # type: ignore[call-arg]
    assert isinstance(build_provider(s), GroqProvider)


def _limit_settings(**overrides: Any) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides
    )


def _global_limits(settings: Settings) -> QuotaLimits:
    return QuotaLimits(
        settings.ai_minute_requests_soft_limit,
        settings.ai_minute_tokens_soft_limit,
        settings.ai_daily_requests_soft_limit,
        settings.ai_daily_tokens_soft_limit,
    )


def test_groq_and_tokenharbor_use_the_global_soft_limits() -> None:
    settings = _limit_settings()
    limits_for = limits_for_model(settings)

    assert limits_for("openai/gpt-oss-120b") == _global_limits(settings)
    assert limits_for("tokenharbor:m") == _global_limits(settings)


def test_a_provider_uses_its_spec_default_limits() -> None:
    limits_for = limits_for_model(_limit_settings())

    assert limits_for("cerebras:gpt-oss-120b") == QuotaLimits(4, 80_000, 900, 950_000)
    assert limits_for("zen:a").day_requests == 300


def test_override_beats_spec_default_field_by_field() -> None:
    settings = _limit_settings(ai_provider_limits={"cerebras": {"day_requests": 10}})
    limits = limits_for_model(settings)("cerebras:gpt-oss-120b")

    assert limits.day_requests == 10
    assert limits.minute_requests == 4
    assert limits.minute_tokens == 80_000
    assert limits.day_tokens == 950_000


def test_override_on_a_spec_without_defaults_falls_back_to_global_per_field() -> None:
    settings = _limit_settings(ai_provider_limits={"tokenharbor": {"day_requests": 7}})
    limits = limits_for_model(settings)("tokenharbor:m")

    assert limits.day_requests == 7
    assert limits.minute_requests == settings.ai_minute_requests_soft_limit


def test_unknown_override_provider_or_field_is_ignored() -> None:
    settings = _limit_settings(
        ai_provider_limits={"nope": {"day_requests": 1}, "zen": {"bogus": 1, "day_requests": 5}}
    )
    limits_for = limits_for_model(settings)

    assert limits_for("zen:a") == QuotaLimits(20, 60_000, 5, 1_500_000)
    assert limits_for("openai/gpt-oss-120b") == _global_limits(settings)
