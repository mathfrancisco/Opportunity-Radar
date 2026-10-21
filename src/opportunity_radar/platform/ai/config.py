"""Cloud AI configuration states derived from runtime settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import SecretStr

from opportunity_radar.platform.ai.providers.registry import PROVIDERS, ProviderSpec
from opportunity_radar.platform.config import Settings


class AIState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    BLOCKED_BY_CONFIGURATION = "blocked_by_configuration"


def provider_models(settings: Settings, spec: ProviderSpec) -> tuple[str, ...]:
    """The unprefixed model names configured for `spec`, blanks dropped."""
    raw: str = getattr(settings, f"{spec.name}_models")
    return tuple(name for name in (part.strip() for part in raw.split(",")) if name)


def excluded_providers(settings: Settings) -> dict[str, str]:
    """Providers that have a key but cannot join a chain, with the reason."""
    out: dict[str, str] = {}
    ordered = {part.strip().lower() for part in settings.ai_reserve_order.split(",")}
    for spec in PROVIDERS:
        if not getattr(settings, f"{spec.name}_api_key").get_secret_value():
            continue
        if spec.name not in ordered:
            out[spec.name] = "fora de AI_RESERVE_ORDER"
            continue
        needs_account = "{account_id}" in getattr(settings, f"{spec.name}_base_url")
        if needs_account and not settings.cloudflare_account_id.strip():
            out[spec.name] = "falta CLOUDFLARE_ACCOUNT_ID"
        elif not provider_models(settings, spec):
            out[spec.name] = f"{spec.name.upper()}_MODELS vazio"
    return out


def configured_providers(settings: Settings) -> list[tuple[ProviderSpec, str, str]]:
    """(spec, api key, base URL) of each usable reserve provider, in `ai_reserve_order`.

    Unknown names in the order are ignored. A provider is usable with a key, at least one
    model and, for Workers AI, the account id its URL needs: no request URL is ever built
    with an empty `{account_id}`.
    """
    by_name = {spec.name: spec for spec in PROVIDERS}
    skipped = excluded_providers(settings)
    result: list[tuple[ProviderSpec, str, str]] = []
    seen: set[str] = set()
    for raw in settings.ai_reserve_order.split(","):
        name = raw.strip().lower()
        spec = by_name.get(name)
        if spec is None or name in seen:
            continue
        seen.add(name)
        key = getattr(settings, f"{name}_api_key").get_secret_value()
        if not key or name in skipped:
            continue
        base_url: str = getattr(settings, f"{name}_base_url").replace(
            "{account_id}", settings.cloudflare_account_id.strip()
        )
        result.append((spec, key, base_url))
    return result


def ai_status(settings: Settings) -> AIState:
    """Return the supported runtime state without exposing any API key."""
    if not settings.ai_enabled:
        return AIState.DISABLED
    if not settings.groq_api_key.get_secret_value() and not configured_providers(settings):
        return AIState.BLOCKED_BY_CONFIGURATION
    return AIState.ENABLED


@dataclass(frozen=True)
class AISettings:
    """Cloud AI settings passed to future provider adapters."""

    provider: str
    api_key: SecretStr  # unwrapped only inside the provider
    base_url: str
    reasoning_model: str
    fast_model: str
    alt_model: str
    timeout_seconds: float
    connect_timeout_seconds: float
    max_retries: int
    fallback_enabled: bool
    reasoning_effort: str
    analysis_prompt: str
    daily_requests_soft_limit: int
    daily_tokens_soft_limit: int
    minute_tokens_soft_limit: int
    minute_requests_soft_limit: int
    breaker_failures: int
    breaker_cooldown_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "AISettings":
        return cls(
            provider=settings.ai_provider,
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            reasoning_model=settings.groq_reasoning_model,
            fast_model=settings.groq_fast_model,
            alt_model=settings.groq_alt_model,
            timeout_seconds=settings.ai_timeout_seconds,
            connect_timeout_seconds=settings.ai_connect_timeout_seconds,
            max_retries=settings.ai_max_retries,
            fallback_enabled=settings.ai_fallback_enabled,
            reasoning_effort=settings.ai_reasoning_effort,
            analysis_prompt=settings.ai_analysis_prompt,
            daily_requests_soft_limit=settings.ai_daily_requests_soft_limit,
            daily_tokens_soft_limit=settings.ai_daily_tokens_soft_limit,
            minute_tokens_soft_limit=settings.ai_minute_tokens_soft_limit,
            minute_requests_soft_limit=settings.ai_minute_requests_soft_limit,
            breaker_failures=settings.ai_breaker_failures,
            breaker_cooldown_seconds=settings.ai_breaker_cooldown_seconds,
        )
