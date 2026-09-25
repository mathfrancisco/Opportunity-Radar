from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.alerts import (
    SourceAlertNotifier,
    SourceAlertService,
)
from opportunity_radar.acquisition.alerts import (
    build_source_alert_notifier as _build_notifier,
)
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import SemanticAnalysisPort
from opportunity_radar.opportunities.embeddings import (
    OllamaEmbeddingAdapter,
    build_embedding_adapter,
)
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import open_session


def get_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    yield from open_session(settings.database_url)


@lru_cache
def cached_alert_notifier() -> SourceAlertNotifier | None:
    settings = get_settings()
    return _build_notifier(
        settings.source_alert_webhook_url,
        timeout_seconds=settings.source_alert_timeout_seconds,
    )


def get_alert_service(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SourceAlertService:
    """A run started from the API is watched exactly like one started by the clock."""
    return SourceAlertService(
        session,
        notifier=cached_alert_notifier(),
        threshold=settings.source_alert_failure_threshold,
    )


@lru_cache
def cached_collector_registry() -> CollectorRegistry:
    settings = get_settings()
    return build_collector_registry(greenhouse_base_url=settings.greenhouse_base_url)


def get_collector_registry() -> CollectorRegistry:
    """The worker's collectors, so a click and the clock read the same endpoints."""
    return cached_collector_registry()


@lru_cache
def cached_analysis_adapter() -> SemanticAnalysisPort:
    """One adapter per process: its in-memory cache is worthless if rebuilt per request."""
    return build_analysis_adapter(get_settings())


def get_analysis_adapter() -> SemanticAnalysisPort:
    return cached_analysis_adapter()


@lru_cache
def cached_embedding_adapter() -> OllamaEmbeddingAdapter | None:
    """One adapter per process, so queries reuse its connection to Ollama."""
    return build_embedding_adapter(get_settings())


def get_embedding_adapter() -> OllamaEmbeddingAdapter | None:
    """`None` when embedding is switched off; the route turns that into a 503."""
    return cached_embedding_adapter()
