"""Construction of the semantic-analysis port from runtime configuration.

Lives in the matching context rather than in the HTTP layer because the worker needs the
same adapter and must not depend on the presentation layer to get it.
"""

from __future__ import annotations

from functools import partial

from sqlalchemy.engine import Engine

from opportunity_radar.matching.analysis import (
    AnalysisPolicy,
    NullAnalysisAdapter,
    SemanticAnalysisPort,
    parse_analysis,
)
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt
from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.config import AIState, ai_status
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.schema import make_validator
from opportunity_radar.platform.ai.tasks import default_routes
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.logging import get_logger

logger = get_logger("opportunity_radar.matching.adapters")
_missing_key_warned = False


def build_analysis_adapter(
    settings: Settings, engine: Engine, *, policy: AnalysisPolicy | None = None
) -> SemanticAnalysisPort:
    """Build one adapter per process (SPEC 43; cards F20-10 to F20-17).

    `engine` backs the persistent Quota Guard (card F20-12): it is shared with the rest
    of the process, never a connection this function opens on its own. The prompt version
    comes from configuration (`AI_ANALYSIS_PROMPT`); an unknown one fails here, at
    startup, rather than on the first analysis. `policy` is an override for callers that
    are not the production worker, such as `scripts/eval_analysis.py`, which must reach
    the model for every case regardless of what the default policy would skip.
    """
    state = ai_status(settings)
    if state is AIState.DISABLED:
        return NullAnalysisAdapter()
    if state is AIState.BLOCKED_BY_CONFIGURATION:
        global _missing_key_warned
        if not _missing_key_warned:
            logger.warning("groq api key missing")
            _missing_key_warned = True
        return NullAnalysisAdapter()

    prompt = load_prompt(settings.ai_analysis_prompt)
    provider = GroqProvider(
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.groq_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        connect_timeout_seconds=settings.ai_connect_timeout_seconds,
    )
    quota_guard = QuotaGuard(
        engine,
        QuotaLimits(
            minute_requests=settings.ai_minute_requests_soft_limit,
            minute_tokens=settings.ai_minute_tokens_soft_limit,
            day_requests=settings.ai_daily_requests_soft_limit,
            day_tokens=settings.ai_daily_tokens_soft_limit,
        ),
    )
    breaker = CircuitBreaker(
        failures=settings.ai_breaker_failures,
        cooldown_seconds=settings.ai_breaker_cooldown_seconds,
    )
    # Loose validator only: it exists so the router can ask a model to repair its own
    # malformed JSON (card F20-14) before giving up on that attempt. The authoritative,
    # evidence-checked parse happens in `GroqAnalysisAdapter.analyze` with the real
    # `PreparedAnalysis.evidence_sources` for this request.
    validator = make_validator(
        partial(
            parse_analysis,
            model_id="router-validation",
            prompt_version=prompt.version,
            schema_version=prompt.schema_version,
        )
    )
    router = AIRouter(
        provider,
        default_routes(settings),
        fallback_enabled=settings.ai_fallback_enabled,
        max_retries=settings.ai_max_retries,
        validator=validator,
        breaker=breaker,
        quota_guard=quota_guard,
    )
    return GroqAnalysisAdapter(router=router, prompt=prompt, policy=policy, engine=engine)
