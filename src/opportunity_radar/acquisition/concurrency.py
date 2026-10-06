"""Shared cross-host concurrency helper for the operator scripts (F20 concurrency work).

`limited_discovery.py`/`discover_sites.py` already run many companies in parallel while
keeping requests to any one host serialized and paced at a fixed interval, via a per-host
`asyncio.Lock`. `discover_ats.py`, `enable_sources.py` and `collect.py` need the exact same
discipline for companies/sources instead of discovery targets, so this module lifts just
that pattern out — a per-host lock plus a shared pacing clock — rather than each script
hand-rolling its own copy.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any
from urllib.parse import urlsplit


class HostSerializer:
    """One `asyncio.Lock` per host, plus a monotonic last-request clock for pacing.

    A caller holds `lock_for(host)` for the whole unit of work touching that host (so no
    two tasks ever talk to the same host at once) and calls `wait_turn(host)` immediately
    before the network request, so consecutive requests to the same host — even across
    different tasks — are at least `min_interval_seconds` apart.
    """

    def __init__(self, *, min_interval_seconds: float = 1.0) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_request_at: dict[str, float] = {}
        self._min_interval = min_interval_seconds

    def lock_for(self, host: str) -> asyncio.Lock:
        return self._locks[host]

    async def wait_turn(self, host: str) -> None:
        """Sleep, if needed, so this request starts at least `min_interval_seconds`
        after the last one on `host`. Call while holding `lock_for(host)`."""
        if self._min_interval <= 0:
            return
        loop = asyncio.get_running_loop()
        last = self._last_request_at.get(host)
        now = loop.time()
        if last is not None:
            remaining = self._min_interval - (now - last)
            if remaining > 0:
                await asyncio.sleep(remaining)
        self._last_request_at[host] = loop.time()


#: Source types whose provider is one shared physical host, addressed by a path segment
#: or query rather than a per-tenant subdomain — every configured source of that type
#: hits the same host, so keying on `source_type` alone is exact.
_SHARED_HOST_TYPES = frozenset(
    {"ashby", "lever", "greenhouse", "workable", "remotive", "hacker_news", "inhire"}
)
#: Which configuration field(s) identify the tenant-specific host for a source type whose
#: provider host differs per source (a subdomain or tenant path).
_TENANT_CONFIG_KEYS: dict[str, tuple[str, ...]] = {
    "teamtailor": ("company_identifier",),
    "factorial": ("company_identifier",),
    "workday": ("tenant_identifier", "api_region"),
}


def source_host_key(source_type: str, configuration: dict[str, Any] | None) -> str:
    """A best-effort per-provider-host key, for rate-limiting/serialization only.

    Source types with one shared provider host key on `source_type` alone.
    Per-tenant types (teamtailor, factorial, workday) key on their tenant-identifying
    configuration fields. `jobposting` keys on the page's own hostname, since that is the
    company's own site, not a shared API. Never raises: a source with missing
    configuration falls back to `source_type`, which still serializes it against its own
    kind rather than running fully unbounded.
    """
    config = configuration or {}
    if source_type in _SHARED_HOST_TYPES:
        return source_type
    if source_type == "jobposting":
        page_url = str(config.get("page_url") or "")
        host = urlsplit(page_url).hostname
        return f"jobposting:{host or page_url}"
    tenant_keys = _TENANT_CONFIG_KEYS.get(source_type)
    if tenant_keys:
        if source_type == "workday":
            tenant_site = str(config.get("tenant_identifier") or "")
            tenant = tenant_site.split("/", 1)[0]
            pod = str(config.get("api_region") or "")
            if tenant and pod:
                return f"{tenant}.{pod}.myworkdayjobs.com"
        tenant = ":".join(str(config.get(key) or "") for key in tenant_keys)
        return f"{source_type}:{tenant}"
    return source_type
