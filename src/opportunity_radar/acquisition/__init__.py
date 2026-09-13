"""Acquisition bounded context public contracts."""

from opportunity_radar.acquisition.collectors import (
    Collector,
    CollectorRegistry,
    ManualCollector,
)
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthcheckContext,
    HealthResult,
    InvalidSourceRunTransitionError,
    ManualInput,
    ManualInputKind,
    SourceRun,
    SourceRunStatus,
)

__all__ = [
    "AcquisitionError",
    "AcquisitionErrorCode",
    "CollectedItem",
    "CollectionMode",
    "CollectionRequest",
    "Collector",
    "CollectorCapabilities",
    "CollectorRegistry",
    "HealthcheckContext",
    "HealthResult",
    "InvalidSourceRunTransitionError",
    "ManualCollector",
    "ManualInput",
    "ManualInputKind",
    "SourceRun",
    "SourceRunStatus",
]
