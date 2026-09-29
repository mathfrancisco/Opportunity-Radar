"""Cloud AI configuration states derived from runtime settings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import SecretStr

from opportunity_radar.platform.config import Settings


class AIState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    BLOCKED_BY_CONFIGURATION = "blocked_by_configuration"


def ai_status(settings: Settings) -> AIState:
    """Return the supported runtime state without exposing the API key."""
    if not settings.ai_enabled:
        return AIState.DISABLED
    if not settings.groq_api_key.get_secret_value():
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
