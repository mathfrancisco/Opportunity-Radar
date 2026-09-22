from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    log_level: str = "INFO"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model_analysis: str = "llama3.2:3b"
    ollama_health_timeout_seconds: float = 1.0
    ollama_analysis_enabled: bool = True
    ollama_analysis_timeout_seconds: float = 30.0
    ollama_analysis_connect_timeout_seconds: float = 5.0
    ollama_analysis_max_retries: int = 1
    ollama_analysis_retry_after_seconds: float = 0.5
    ollama_analysis_cache_entries: int = 256
    frontend_origin: str = "http://localhost:3000"
    collection_timezone: str = "UTC"
    worker_collect_enabled: bool = True
    worker_normalize_enabled: bool = True
    worker_match_enabled: bool = True
    worker_analyze_enabled: bool = True
    worker_retention_enabled: bool = True
    worker_evaluate_batch_size: int = 50
    # The local model competes with the rest of the machine for CPU, so a pass is capped
    # well below the evaluation batch: analysis falls behind on purpose, never the rules.
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

    @property
    def analysis_eligible_verdicts(self) -> tuple[str, ...]:
        return tuple(
            item.strip().upper()
            for item in self.worker_analyze_verdicts.split(",")
            if item.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Values are loaded from the environment.
