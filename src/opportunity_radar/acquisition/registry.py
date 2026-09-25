"""The collectors this deployment runs, pointed at the endpoints it is configured for."""

from __future__ import annotations

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.collectors import CollectorRegistry, ManualCollector
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.acquisition.tavily import TavilyClient, TavilySearchCollector


def build_collector_registry(
    *,
    greenhouse_base_url: str,
    tavily_api_key: str | None = None,
    tavily_base_url: str = "https://api.tavily.com",
    tavily_search_depth: str = "basic",
) -> CollectorRegistry:
    """One registry for the worker and the API.

    Built in one place so a run started by a click and a probe of a board read the same
    endpoint the worker's clock does — in CI, the local job board.

    `tavily_search` is always registered, same as every other collector: an absent
    `tavily_api_key` is a supported deployment (blocked by configuration, reported by
    `healthcheck()`), not a reason to leave the source type unresolvable.
    """
    return CollectorRegistry(
        (
            ManualCollector(),
            AshbyCollector(),
            LeverCollector(),
            GreenhouseCollector(base_url=greenhouse_base_url),
            RemotiveCollector(),
            TavilySearchCollector(
                client_factory=lambda: TavilyClient(
                    api_key=tavily_api_key,
                    base_url=tavily_base_url,
                    search_depth=tavily_search_depth,
                )
            ),
        )
    )
