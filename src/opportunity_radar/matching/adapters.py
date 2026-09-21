"""Construction of the semantic-analysis port from runtime configuration.

Lives in the matching context rather than in the HTTP layer because the worker needs the
same adapter and must not depend on the presentation layer to get it.
"""

from __future__ import annotations

from opportunity_radar.matching.analysis import NullAnalysisAdapter, SemanticAnalysisPort
from opportunity_radar.matching.ollama import OllamaAnalysisAdapter
from opportunity_radar.platform.config import Settings


def build_analysis_adapter(settings: Settings) -> SemanticAnalysisPort:
    """Build one adapter per process: its in-memory cache is worthless if rebuilt."""
    if not settings.ollama_analysis_enabled:
        return NullAnalysisAdapter()
    return OllamaAnalysisAdapter(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model_analysis,
        timeout_seconds=settings.ollama_analysis_timeout_seconds,
        connect_timeout_seconds=settings.ollama_analysis_connect_timeout_seconds,
        max_retries=settings.ollama_analysis_max_retries,
        retry_after_seconds=settings.ollama_analysis_retry_after_seconds,
        cache_max_entries=settings.ollama_analysis_cache_entries,
    )
