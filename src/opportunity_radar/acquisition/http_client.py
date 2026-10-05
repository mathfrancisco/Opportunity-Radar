"""Default HTTP client shared by the collectors.

Every collector that talks to a third party identifies itself with the same product
`User-Agent`, never the library default and never a browser's. Discovery keeps its own
bot agent (`companies.discovery.DEFAULT_USER_AGENT`): finding boards is not collecting.
"""

from __future__ import annotations

import httpx

COLLECTOR_USER_AGENT = "opportunity-radar (personal job radar)"


def default_collector_client() -> httpx.AsyncClient:
    """The client a collector builds when none is injected."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0),
        headers={"User-Agent": COLLECTOR_USER_AGENT},
    )
