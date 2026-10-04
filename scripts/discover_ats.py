"""Discover the ATS behind a company's careers page, one request per eligible company.

Card F20-27. Off by default: this is a manual `make discover-ats` run (or a low-frequency
job an operator turns on separately), never part of the collection schedule.

F20 concurrency work: companies run concurrently, up to `--concurrency` at once (default
8), while every request to one host — including the 1 request/second pace — stays
serialized behind that host's own lock (`HostSerializer`, shared with `enable_sources.py`
and `collect.py`). Before ever fetching the careers page, each company gets a slug-first
probe against each ATS's own public API (`probe_direct_ats`, from F20-36's
`limited_discovery.py`) — a hit skips the careers-page request entirely. One company's
failure is caught and counted, never sinking the batch.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.concurrency import HostSerializer
from opportunity_radar.acquisition.limited_discovery import (
    default_resolve_ips,
    endpoint_ats_name,
    probe_direct_ats,
)
from opportunity_radar.companies.discovery import (
    DEFAULT_USER_AGENT,
    DiscoveryOutcome,
    discover_one,
    eligible_companies,
    record_ats_identified,
    record_discovery_attempt,
    robots_allows,
)
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

#: How many companies may be in flight at once. Different companies on different hosts
#: run concurrently; same-host work still serializes behind `HostSerializer`.
DEFAULT_CONCURRENCY = 8
#: SPEC 39 §5's 1 request/second pace, enforced per host rather than across the run.
DEFAULT_MIN_INTERVAL_SECONDS = 1.0


def _confirmed_careers_url(company: Company) -> str | None:
    """The same "confirmed careers page" `discover_one` requires; kept local rather than
    importing `companies.discovery`'s private `_careers_url` (same convention
    `discover_sites.py` already uses for its own copy)."""
    for source in company.sources:
        if source.source_type == "careers" and source.verification_status == "careers_confirmed":
            return source.endpoint
    return None


async def _resolve_ips(host: str) -> tuple[str, ...]:
    return await asyncio.to_thread(default_resolve_ips, host)


async def _discover_company(
    company: Company,
    checked_url: str,
    *,
    client: httpx.AsyncClient,
    robots_checker: Callable[[str], bool],
) -> DiscoveryOutcome:
    """The slug-first direct-ATS probe, falling back to the single careers-page GET."""
    endpoint, _requests_made = await probe_direct_ats(
        company.id,
        company.canonical_name,
        checked_url,
        client=client,
        resolve_ips=_resolve_ips,
    )
    if endpoint is not None:
        return DiscoveryOutcome(
            company_id=company.id,
            checked_url=checked_url,
            final_url=endpoint.discovered_url,
            http_status=200,
            ats_found=endpoint_ats_name(endpoint),
            evidence_snippet=endpoint.evidence_excerpt,
            ats_url=endpoint.discovered_url,
        )
    return await discover_one(company, client=client, robots_checker=robots_checker)


async def run_discovery(
    session: Session,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
) -> dict[str, object]:
    counters = {"checked": 0, "no_ats_found": 0, "errors": 0}
    by_ats: dict[str, int] = {}
    companies = eligible_companies(session)
    robots_cache: dict[str, bool] = {}

    def cached_robots_checker(url: str) -> bool:
        host = urlsplit(url).netloc
        if host not in robots_cache:
            robots_cache[host] = robots_allows(url, user_agent=DEFAULT_USER_AGENT)
        return robots_cache[host]

    host_serializer = HostSerializer(min_interval_seconds=min_interval_seconds)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    # The `Session` itself is not safe for concurrent `await`-interleaved use: every
    # touch of it (recording an attempt, recording an identified ATS) holds this lock
    # too, on top of (never instead of) the per-host lock.
    db_lock = asyncio.Lock()
    report_lock = asyncio.Lock()

    async def process(company: Company, client: httpx.AsyncClient) -> None:
        checked_url = _confirmed_careers_url(company)
        if checked_url is None:
            return
        host = urlsplit(checked_url).hostname or ""
        async with semaphore, host_serializer.lock_for(host):
            await host_serializer.wait_turn(host)
            try:
                outcome = await _discover_company(
                    company, checked_url, client=client, robots_checker=cached_robots_checker
                )
            except Exception:  # noqa: BLE001 - one company's failure never sinks the batch
                async with report_lock:
                    counters["errors"] += 1
                return
            async with db_lock:
                record_discovery_attempt(session, outcome)
                async with report_lock:
                    counters["checked"] += 1
                if outcome.ats_found is not None:
                    record_ats_identified(session, outcome)
                    async with report_lock:
                        by_ats[outcome.ats_found] = by_ats.get(outcome.ats_found, 0) + 1
                else:
                    async with report_lock:
                        counters["no_ats_found"] += 1

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(process(company, client) for company in companies))

    return {**counters, "by_ats": by_ats}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Companies in flight at once; same-host work still serializes at 1 "
        f"request/second (default: {DEFAULT_CONCURRENCY}).",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = asyncio.run(run_discovery(session, concurrency=args.concurrency))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
