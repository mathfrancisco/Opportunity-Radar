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

Runs companies concurrently, up to `--concurrency` at once (default 8): different hosts
overlap in flight, but everything that touches one host — including `HostBudgetState` and
the database session — stays serialized behind that host's own lock, so the 1 request/
second pace and `concurrency_per_host=1` are exactly as true as in the sequential version.
A long run (the eligible catalog is normally in the hundreds) should go to the background
and, with `--progress-file`, write its running totals after every company — never left as
a single foreground command for several minutes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
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
#: Shallow-first defaults for this script (F20-36 follow-up): the careers page alone
#: covers most real signatures; sitemap/extra pages are a fallback, not the default cost.
DEFAULT_MAX_HTML_RESPONSES = 5
DEFAULT_MAX_SITEMAP_FILES = 1
#: How many companies may be in flight at once. Different companies on different hosts
#: run concurrently; same-host work still serializes (see module docstring).
DEFAULT_CONCURRENCY = 8


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


def _write_progress(progress_file: str | None, report: dict[str, object]) -> None:
    if progress_file is None:
        return
    tmp_path = f"{progress_file}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, progress_file)


async def run_batch(
    session: Session,
    *,
    limit: int | None,
    min_interval_seconds: float,
    limits: DiscoveryLimits,
    dry_run: bool,
    concurrency: int = DEFAULT_CONCURRENCY,
    progress_file: str | None = None,
) -> dict[str, object]:
    companies = eligible_companies(session)
    if limit is not None:
        companies = companies[:limit]

    report: dict[str, object] = {
        "checked": 0,
        "errors": 0,
        "by_ats": {},
        "by_stop_reason": {},
        "total": len(companies),
    }
    by_ats: dict[str, int] = {}
    by_stop_reason: dict[str, int] = {}
    # Same dict objects as above: a mid-run `_write_progress` sees live totals, not the
    # empty placeholders `report` was initialized with.
    report["by_ats"] = by_ats
    report["by_stop_reason"] = by_stop_reason
    host_budgets: dict[str, HostBudgetState] = {}
    # One lock per host: same-host work (HostBudgetState bookkeeping and the DB writes
    # below) stays fully serialized even though different companies run concurrently.
    host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    # The `Session` itself is not safe for concurrent `await`-interleaved use; every
    # touch of it — recording an attempt, upserting a source — holds this lock too, on
    # top of (never instead of) the per-host lock, so writes never interleave across
    # companies regardless of which host they came from.
    db_lock = asyncio.Lock()
    progress_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def process(company: Company, client: httpx.AsyncClient) -> None:
        seed_url = _confirmed_careers_url(company)
        if seed_url is None:
            return
        host = urlsplit(seed_url).hostname or ""
        async with semaphore, host_locks[host]:
            now = datetime.now(UTC)
            budget = host_budgets.get(host) or HostBudgetState(
                host=host,
                window_start=now,
                requests_used=0,
                requests_ceiling=DEFAULT_HOST_REQUESTS_PER_RUN,
            )
            budget = budget.rolled_over(now=now, window=DEFAULT_HOST_BUDGET_WINDOW)
            if not budget.has_capacity(now=now):
                async with progress_lock:
                    by_stop_reason["HOST_BUDGET_EXHAUSTED"] = (
                        by_stop_reason.get("HOST_BUDGET_EXHAUSTED", 0) + 1
                    )
                return

            try:
                outcome = await run_limited_discovery(
                    seed_url,
                    company_id=company.id,
                    company_name=company.canonical_name,
                    limits=limits,
                    allowlist=_allowlist_for(seed_url),
                    client=client,
                    min_interval_seconds=min_interval_seconds,
                )
            except Exception:  # noqa: BLE001 - one company's failure never sinks the batch
                async with progress_lock:
                    report["errors"] = int(report["errors"]) + 1
                _write_progress(progress_file, report)
                return
            host_budgets[host] = replace(
                budget, requests_used=budget.requests_used + outcome.http_requests
            )

            async with db_lock:
                async with progress_lock:
                    report["checked"] = int(report["checked"]) + 1
                    by_stop_reason[outcome.stop_reason.value] = (
                        by_stop_reason.get(outcome.stop_reason.value, 0) + 1
                    )
                if not dry_run:
                    record_limited_discovery_attempt(session, outcome, checked_url=seed_url)
                if outcome.endpoints:
                    ats = endpoint_ats_name(outcome.endpoints[0])
                    if ats is not None:
                        async with progress_lock:
                            by_ats[ats] = by_ats.get(ats, 0) + 1
                        if not dry_run:
                            upsert_ats_identified_source(session, outcome.endpoints[0])
            _write_progress(progress_file, report)

    async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}) as client:
        await asyncio.gather(*(process(company, client) for company in companies))

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
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Companies in flight at once; same-host work still serializes "
        f"(default: {DEFAULT_CONCURRENCY}).",
    )
    parser.add_argument(
        "--progress-file",
        default=None,
        help="Write the running report to this path after every company. Use this and "
        "run the process in the background for the full catalog — never as a single "
        "foreground command for more than a few minutes.",
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
                limits=DiscoveryLimits(
                    max_html_responses=DEFAULT_MAX_HTML_RESPONSES,
                    max_sitemap_files=DEFAULT_MAX_SITEMAP_FILES,
                ),
                dry_run=args.dry_run,
                concurrency=args.concurrency,
                progress_file=args.progress_file,
            )
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
