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
    provider_name_for,
    spec_for_model,
)

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
    assert PROVIDERS == (TOKENHARBOR,)
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
