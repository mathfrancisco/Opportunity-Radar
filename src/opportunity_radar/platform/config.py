from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_REASONING_EFFORTS = frozenset({"low", "medium", "high"})


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    log_level: str = "INFO"
    frontend_origin: str = "http://localhost:3000"
    collection_timezone: str = "UTC"
    worker_collect_enabled: bool = True
    worker_normalize_enabled: bool = True
    worker_match_enabled: bool = True
    worker_analyze_enabled: bool = True
    worker_retention_enabled: bool = True
    worker_evaluate_batch_size: int = 50
    # The local model competes with the rest of the machine for the GPU, so a pass is
    # capped well below the evaluation batch: analysis falls behind on purpose, never the
    # rules.
    worker_analyze_batch_size: int = 10
    worker_analyze_verdicts: str = "HIGH_PRIORITY,RECOMMENDED,WATCHLIST,REVIEW_REQUIRED"
    analysis_retry_cooldown_seconds: int = 3600
    analysis_retry_attempt_window_seconds: int = 86400
    analysis_retry_max_attempts: int = 3
    analysis_claim_lease_seconds: int = 900
    collection_backoff_base_seconds: int = 300
    collection_backoff_ceiling_seconds: int = 86400
    greenhouse_base_url: str = "https://boards-api.greenhouse.io"
    # An empty webhook is a supported deployment: incidents are still opened and closed,
    # and the absent channel is reported by the doctor instead of failing collection.
    source_alert_webhook_url: str = ""
    source_alert_failure_threshold: int = 3
    source_alert_timeout_seconds: float = 5.0
    payload_retention_days: int = 365
    payload_retention_batch_size: int = 500
    payload_retention_interval_seconds: int = 21600
    # How late a job may be before the doctor calls it late rather than merely busy.
    doctor_job_grace_seconds: int = 120

    # Cloud AI is deliberately opt-in; the Groq adapter is the only analysis provider.
    ai_enabled: bool = False
    ai_provider: str = "groq"
    groq_api_key: SecretStr = SecretStr("")
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_reasoning_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "openai/gpt-oss-20b"
    groq_alt_model: str = "qwen/qwen3.8-27b"
    ai_timeout_seconds: float = 25.0
    ai_connect_timeout_seconds: float = 5.0
    ai_max_retries: int = 2
    ai_fallback_enabled: bool = True
    ai_reasoning_effort: str = "low"
    ai_analysis_prompt: str = "v1"
    ai_daily_requests_soft_limit: int = 850
    ai_daily_tokens_soft_limit: int = 170_000
    ai_minute_tokens_soft_limit: int = 7_000
    ai_minute_requests_soft_limit: int = 25
    ai_breaker_failures: int = 5
    ai_breaker_cooldown_seconds: int = 120
    # Optional on purpose: presence decides whether the Tavily source participates in
    # runs at all. Absent, it is a supported deployment (bloqueada por configuração),
    # the same treatment source_alert_webhook_url already gets above.
    tavily_api_key: str | None = None
    tavily_base_url: str = "https://api.tavily.com"
    # Cheapest tier of each knob (docs/41-spec-tavily.md, section 3); `advanced` doubles
    # the credit cost and is not enabled without a measurement showing `basic` loses
    # relevant content.
    tavily_search_depth: str = "basic"
    tavily_extract_depth: str = "basic"
    tavily_extract_format: str = "markdown"
    # A URL is extracted once, ever, within this window (F20-45 acceptance criterion:
    # "uma URL nunca gera duas chamadas de extração bem-sucedidas dentro da validade do
    # cache"). 30 days is generous relative to how often a posting's body changes.
    tavily_extract_cache_ttl_seconds: int = 30 * 24 * 60 * 60
    # Conservative on purpose: the free plan is 1,000 credits/month shared by /search and
    # /extract; a single run capped at 100 leaves room for roughly ten runs/day before the
    # monthly ceiling is a concern, until real usage is measured (docs/41-spec-tavily.md,
    # section 9).
    tavily_credit_budget_per_run: int = 100

    @property
    def analysis_eligible_verdicts(self) -> tuple[str, ...]:
        return tuple(
            item.strip().upper()
            for item in self.worker_analyze_verdicts.split(",")
            if item.strip()
        )

    @model_validator(mode="after")
    def _validate_ai_settings(self) -> "Settings":
        if self.ai_provider != "groq":
            raise ValueError(f"AI_PROVIDER must be 'groq', got {self.ai_provider!r}")
        if self.ai_reasoning_effort not in _VALID_REASONING_EFFORTS:
            raise ValueError(
                "AI_REASONING_EFFORT must be one of "
                f"{sorted(_VALID_REASONING_EFFORTS)}, got {self.ai_reasoning_effort!r}"
            )
        positive_limits = {
            "AI_TIMEOUT_SECONDS": self.ai_timeout_seconds,
            "AI_CONNECT_TIMEOUT_SECONDS": self.ai_connect_timeout_seconds,
            "AI_DAILY_REQUESTS_SOFT_LIMIT": self.ai_daily_requests_soft_limit,
            "AI_DAILY_TOKENS_SOFT_LIMIT": self.ai_daily_tokens_soft_limit,
            "AI_MINUTE_TOKENS_SOFT_LIMIT": self.ai_minute_tokens_soft_limit,
            "AI_MINUTE_REQUESTS_SOFT_LIMIT": self.ai_minute_requests_soft_limit,
            "AI_BREAKER_FAILURES": self.ai_breaker_failures,
            "AI_BREAKER_COOLDOWN_SECONDS": self.ai_breaker_cooldown_seconds,
        }
        for name, value in positive_limits.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value!r}")
        if self.ai_max_retries < 0:
            raise ValueError(f"AI_MAX_RETRIES cannot be negative, got {self.ai_max_retries!r}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Values are loaded from the environment.
