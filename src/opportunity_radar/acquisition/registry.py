"""The collectors this deployment runs, pointed at the endpoints it is configured for."""

from __future__ import annotations

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.collectors import CollectorRegistry, ManualCollector
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.remotive import RemotiveCollector


def build_collector_registry(*, greenhouse_base_url: str) -> CollectorRegistry:
    """One registry for the worker and the API.

    Built in one place so a run started by a click and a probe of a board read the same
    endpoint the worker's clock does — in CI, the local job board.
    """
    return CollectorRegistry(
        (
            ManualCollector(),
            AshbyCollector(),
            LeverCollector(),
            GreenhouseCollector(base_url=greenhouse_base_url),
            RemotiveCollector(),
        )
    )
