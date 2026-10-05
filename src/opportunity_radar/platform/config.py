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
    # Off by default (card F20-23): the precision of the `job_classification` suggestion
    # must be measured on a labelled sample before this job writes anything, even to its
    # own separate table.
    worker_suggest_enabled: bool = False
    worker_suggest_batch_size: int = 20
    # Off by default (card F48-15): `seniority-v4`, `work-mode-v7` and `allowed-countries-v2`
    # read the description. Turn on only after `scripts/measure_content_classification.py
    # --check-gate` reports >= 90% precision per rule on the human-labelled gold set.
    content_classification_v4_enabled: bool = False
    # F50-02: the same rules one by one, comma separated, named as the measurement script
    # prints them (e.g. `seniority:description_years_min,work_mode:description_phrase`).
    # The boolean above keeps meaning "every rule". Empty and False: none runs.
    content_classification_enabled_rules: str = ""
    worker_evaluate_batch_size: int = 50
    # The local model competes with the rest of the machine for the GPU, so a pass is
    # capped well below the evaluation batch: analysis falls behind on purpose, never the
    # rules.
    worker_analyze_batch_size: int = 10
    # The day's token budget covers about a hundred analyses, so the queue takes only the
    # verdicts worth acting on; any other posting is analysed on demand from its page.
    worker_analyze_verdicts: str = "HIGH_PRIORITY,RECOMMENDED"
    # Fraction of the worker's batch reserved for eligible assessments the value ranking
    # (score, company priority, freshness) would otherwise never reach, to measure funnel
    # losses instead of only ever spending the model on what already ranks highest (SPEC
    # 39 section 9; card F20-24).
    worker_analyze_aging_sample_ratio: float = 0.10
    analysis_retry_cooldown_seconds: int = 3600
    analysis_retry_attempt_window_seconds: int = 86400
    analysis_retry_max_attempts: int = 3
    analysis_claim_lease_seconds: int = 900
    # F50-04: a source whose share of target-area items over its last three complete runs
    # falls below this stops persisting new off-target items. 0 turns the filter off.
    collection_target_area_floor: float = 0.30
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
    # Off by default (card F50-08): it deletes data. Turn on only after
    # `scripts/prune_assessments.py` (dry run) reports what it would delete.
    worker_assessment_retention_enabled: bool = False
    assessment_retention_days: int = 7
    assessment_retention_batch_size: int = 500
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
    # Per-task override of ai_reasoning_effort (card F20-22): unset keeps every task on
    # the global value, so this is a no-op until a benchmark decides a task needs a
    # different effort than the others. See platform/ai/tasks.py default_routes.
    ai_reasoning_effort_job_match: str | None = None
    ai_reasoning_effort_job_classification: str | None = None
    ai_reasoning_effort_job_extraction: str | None = None
    ai_analysis_prompt: str = "v1"
    ai_daily_requests_soft_limit: int = 850
    ai_daily_tokens_soft_limit: int = 170_000
    # Part of the day's Groq request quota the worker's own batch never spends, so
    # analysis requested from the UI always has room even on a day the backlog is deep
    # (SPEC 43; card F20-12's `QuotaGuard.reserve(ceiling_requests=...)`).
    ai_interactive_reserve_requests: int = 100
    ai_minute_tokens_soft_limit: int = 7_000
    ai_minute_requests_soft_limit: int = 25
    ai_breaker_failures: int = 5
    ai_breaker_cooldown_seconds: int = 120
    # SPEC 43 §8.5: per-call telemetry (`platform.ai_call_record`) carries no PII, so it
    # only needs enough retention to explain recent cost and failure, not an audit trail.
    ai_call_record_retention_days: int = 30
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
    # F48-08: source types whose items never go through Tavily `/extract` (comma
    # separated). Workday pages are JS-rendered: every call failed and burned credits.
    extraction_skip_source_types: str = "workday"
    # F48-08: stop extracting for a host after this many consecutive failures (0 = off).
    tavily_extract_host_failure_threshold: int = 5
    # F48-08: request ceiling per source type for a new host budget row, `type=ceiling`
    # comma separated. Types not listed use the scheduler default (200 per hour).
    host_request_ceilings: str = "workday=500,hacker_news=500"

    @property
    def extraction_skip_source_type_set(self) -> frozenset[str]:
        return frozenset(
            item.strip().lower()
            for item in self.extraction_skip_source_types.split(",")
            if item.strip()
        )

    @property
    def host_request_ceiling_map(self) -> dict[str, int]:
        ceilings: dict[str, int] = {}
        for entry in self.host_request_ceilings.split(","):
            if not entry.strip():
                continue
            source_type, _, value = entry.partition("=")
            ceilings[source_type.strip()] = int(value)
        return ceilings

    @property
    def content_classification_rule_set(self) -> frozenset[str]:
        return frozenset(
            item.strip()
            for item in self.content_classification_enabled_rules.split(",")
            if item.strip()
        )

    @property
    def content_rules(self) -> bool | frozenset[str]:
        """What `build_candidate(content_rules=...)` takes: `True` (all) or a rule set."""
        if self.content_classification_v4_enabled:
            return True
        return self.content_classification_rule_set

    @property
    def analysis_eligible_verdicts(self) -> tuple[str, ...]:
        return tuple(
            item.strip().upper()
            for item in self.worker_analyze_verdicts.split(",")
            if item.strip()
        )

    @model_validator(mode="after")
    def _validate_content_classification_rules(self) -> "Settings":
        # Imported here: the opportunities package reads this module at import time.
        from opportunity_radar.opportunities.content_classification import CONTENT_RULE_NAMES

        unknown = sorted(self.content_classification_rule_set - CONTENT_RULE_NAMES)
        if unknown:
            raise ValueError(
                f"CONTENT_CLASSIFICATION_ENABLED_RULES has unknown rule name(s) {unknown}; "
                f"valid names: {sorted(CONTENT_RULE_NAMES)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_ai_settings(self) -> "Settings":
        if self.ai_provider != "groq":
            raise ValueError(f"AI_PROVIDER must be 'groq', got {self.ai_provider!r}")
        if self.ai_reasoning_effort not in _VALID_REASONING_EFFORTS:
            raise ValueError(
                "AI_REASONING_EFFORT must be one of "
                f"{sorted(_VALID_REASONING_EFFORTS)}, got {self.ai_reasoning_effort!r}"
            )
        per_task_efforts = {
            "AI_REASONING_EFFORT_JOB_MATCH": self.ai_reasoning_effort_job_match,
            "AI_REASONING_EFFORT_JOB_CLASSIFICATION": self.ai_reasoning_effort_job_classification,
            "AI_REASONING_EFFORT_JOB_EXTRACTION": self.ai_reasoning_effort_job_extraction,
        }
        for effort_name, effort_value in per_task_efforts.items():
            # An empty string is the same "unset" as None here: a `.env` copied from
            # .env.example carries `VAR=` for every optional field in this codebase, and
            # both mean "fall back to AI_REASONING_EFFORT" (see tasks.py `_effort_for`).
            if effort_value and effort_value not in _VALID_REASONING_EFFORTS:
                raise ValueError(
                    f"{effort_name} must be one of {sorted(_VALID_REASONING_EFFORTS)} or "
                    f"unset, got {effort_value!r}"
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
            "AI_CALL_RECORD_RETENTION_DAYS": self.ai_call_record_retention_days,
            "ASSESSMENT_RETENTION_DAYS": self.assessment_retention_days,
            "ASSESSMENT_RETENTION_BATCH_SIZE": self.assessment_retention_batch_size,
        }
        for name, value in positive_limits.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value!r}")
        if self.ai_max_retries < 0:
            raise ValueError(f"AI_MAX_RETRIES cannot be negative, got {self.ai_max_retries!r}")
        if not 0 <= self.ai_interactive_reserve_requests < self.ai_daily_requests_soft_limit:
            raise ValueError(
                "AI_INTERACTIVE_RESERVE_REQUESTS must be between 0 and "
                f"AI_DAILY_REQUESTS_SOFT_LIMIT ({self.ai_daily_requests_soft_limit}), "
                f"got {self.ai_interactive_reserve_requests!r}"
            )
        if not 0 <= self.worker_analyze_aging_sample_ratio <= 1:
            raise ValueError(
                "WORKER_ANALYZE_AGING_SAMPLE_RATIO must be between 0 and 1, got "
                f"{self.worker_analyze_aging_sample_ratio!r}"
            )
        if not 0 <= self.collection_target_area_floor <= 1:
            raise ValueError(
                "COLLECTION_TARGET_AREA_FLOOR must be between 0 and 1, got "
                f"{self.collection_target_area_floor!r}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Values are loaded from the environment.
