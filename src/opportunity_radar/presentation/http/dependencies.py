from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunity_radar.matching.analysis import NullAnalysisAdapter, SemanticAnalysisPort
from opportunity_radar.matching.ollama import OllamaAnalysisAdapter
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import open_session


def get_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    yield from open_session(settings.database_url)


@lru_cache
def build_analysis_adapter() -> SemanticAnalysisPort:
    """One adapter per process: its in-memory cache is worthless if rebuilt per request."""
    settings = get_settings()
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


def get_analysis_adapter() -> SemanticAnalysisPort:
    return build_analysis_adapter()
