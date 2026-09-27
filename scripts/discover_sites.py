"""Multi-page limited discovery for a company whose careers page hides its ATS (F20-36).

Card F20-27's `scripts/discover_ats.py` makes one request per eligible company. This
script goes one step further, per company: robots.txt, the site's own sitemap(s), and a
handful of same-allowlist pages, always inside `DiscoveryLimits` (see
`acquisition/limited_discovery.py`). Off by default: a manual `make discover-sites` run,
or a low-frequency job an operator schedules separately — never part of the collection
schedule, and it never creates a `SourceRun`/`RawItem`.

Reuses F20-38's `HostBudgetState` to keep the whole run under one shared request ceiling
per host (some companies' careers pages resolve to the same platform host even without a
known ATS, e.g. a shared marketing CMS), on top of `DiscoveryLimits`' own per-attempt caps
and the required 1 request/second pace.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.limited_discovery import (
    DEFAULT_USER_AGENT,
    DiscoveryLimits,
    endpoint_ats_name,
    record_limited_discovery_attempt,
    run_limited_discovery,
    upsert_ats_identified_source,
)
from opportunity_radar.acquisition.scheduling import DEFAULT_HOST_BUDGET_WINDOW, HostBudgetState
from opportunity_radar.companies.discovery import eligible_companies
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

#: Politeness ceiling for one host across the whole run, independent of `DiscoveryLimits`'
#: own per-attempt request budget (SPEC 39 §5).
DEFAULT_HOST_REQUESTS_PER_RUN = 60


def _confirmed_careers_url(company: Company) -> str | None:
    """The same "confirmed careers page" `companies.discovery` checks (F20-27); kept
    local rather than importing that module's private `_careers_url`."""
    for source in company.sources:
        if source.source_type == "careers" and source.verification_status == "careers_confirmed":
            return source.endpoint
    return None


def _allowlist_for(seed_url: str) -> frozenset[str]:
    host = urlsplit(seed_url).hostname or ""
    # The seed's own host, plus any of its subdomains (an ATS embed often lives one
    # level down, e.g. jobs.acme.com from acme.com/careers).
    bare = host.split(":", 1)[0]
    parts = bare.split(".")
    registrable = ".".join(parts[-2:]) if len(parts) >= 2 else bare
    return frozenset({bare, f".{registrable}"})


async def run_batch(
    session: Session,
    *,
    limit: int | None,
    min_interval_seconds: float,
    limits: DiscoveryLimits,
    dry_run: bool,
) -> dict[str, object]:
    companies = eligible_companies(session)
    if limit is not None:
        companies = companies[:limit]

    report: dict[str, object] = {"checked": 0, "by_ats": {}, "by_stop_reason": {}}
    by_ats: dict[str, int] = {}
    by_stop_reason: dict[str, int] = {}
    host_budgets: dict[str, HostBudgetState] = {}

    async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}) as client:
        for company in companies:
            seed_url = _confirmed_careers_url(company)
            if seed_url is None:
                continue
            host = urlsplit(seed_url).hostname or ""
            now = datetime.now(UTC)
            budget = host_budgets.get(host) or HostBudgetState(
                host=host,
                window_start=now,
                requests_used=0,
                requests_ceiling=DEFAULT_HOST_REQUESTS_PER_RUN,
            )
            budget = budget.rolled_over(now=now, window=DEFAULT_HOST_BUDGET_WINDOW)
            if not budget.has_capacity(now=now):
                by_stop_reason["HOST_BUDGET_EXHAUSTED"] = (
                    by_stop_reason.get("HOST_BUDGET_EXHAUSTED", 0) + 1
                )
                continue

            outcome = await run_limited_discovery(
                seed_url,
                company_id=company.id,
                limits=limits,
                allowlist=_allowlist_for(seed_url),
                client=client,
                min_interval_seconds=min_interval_seconds,
            )
            host_budgets[host] = replace(
                budget, requests_used=budget.requests_used + outcome.http_requests
            )

            report["checked"] = int(report["checked"]) + 1
            by_stop_reason[outcome.stop_reason.value] = (
                by_stop_reason.get(outcome.stop_reason.value, 0) + 1
            )
            if not dry_run:
                record_limited_discovery_attempt(session, outcome, checked_url=seed_url)
            if outcome.endpoints:
                ats = endpoint_ats_name(outcome.endpoints[0])
                if ats is not None:
                    by_ats[ats] = by_ats.get(ats, 0) + 1
                    if not dry_run:
                        upsert_ats_identified_source(session, outcome.endpoints[0])

    report["by_ats"] = by_ats
    report["by_stop_reason"] = by_stop_reason
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=None, help="Cap how many eligible companies to check."
    )
    parser.add_argument(
        "--min-interval-seconds",
        type=float,
        default=1.0,
        help="Minimum delay between requests (SPEC 39 §5 default: 1 request/second).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery and print the report without writing to the database.",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = asyncio.run(
            run_batch(
                session,
                limit=args.limit,
                min_interval_seconds=args.min_interval_seconds,
                limits=DiscoveryLimits(),
                dry_run=args.dry_run,
            )
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
