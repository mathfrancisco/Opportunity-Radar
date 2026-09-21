from collections.abc import Iterator
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import SemanticAnalysisPort
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.platform.database import open_session


def get_session(settings: Settings = Depends(get_settings)) -> Iterator[Session]:
    yield from open_session(settings.database_url)


@lru_cache
def cached_analysis_adapter() -> SemanticAnalysisPort:
    """One adapter per process: its in-memory cache is worthless if rebuilt per request."""
    return build_analysis_adapter(get_settings())


def get_analysis_adapter() -> SemanticAnalysisPort:
    return cached_analysis_adapter()
