"""Propose ATS boards for catalogue companies that have no source yet (R55-B6).

Dry-run by default: probes the known ATS public APIs and reports what it would propose,
writing nothing. `--apply` writes inert proposals (`enabled=false`, no terms review, no
local test) into the existing homologation queue; this script never enables a source.

Tavily is the fallback for a company no known ATS answers for, and is off unless
`--use-tavily` is given (a dry-run with `--use-tavily` still spends credits). Its spend is
capped by `--max-credits`, default `TAVILY_CREDIT_BUDGET_PER_RUN` (Settings default 100).
Re-running is safe: a company with any source, proposed or not, is skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict

import httpx
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.board_discovery import BoardDiscoveryReport, discover_boards
from opportunity_radar.acquisition.limited_discovery import (
    DEFAULT_USER_AGENT,
    default_resolve_ips,
)
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyCreditBudget
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine


async def _resolve_ips(host: str) -> tuple[str, ...]:
    return await asyncio.to_thread(default_resolve_ips, host)


def _report_json(report: BoardDiscoveryReport) -> dict[str, object]:
    return {
        "companies_considered": report.companies_considered,
        "skipped_with_source": report.skipped_with_source,
        "tavily_queries": report.tavily_queries,
        "tavily_credits_spent": report.tavily_credits_spent,
        "tavily_budget_stopped": report.tavily_budget_stopped,
        "outcomes": [
            {key: str(value) for key, value in asdict(o).items() if value is not None}
            for o in report.outcomes
        ],
    }


async def run(
    session: Session,
    *,
    apply: bool,
    limit: int | None,
    use_tavily: bool,
    max_credits: int,
    min_interval_seconds: float = 1.0,
) -> BoardDiscoveryReport:
    tavily: TavilyClient | None = None
    budget: TavilyCreditBudget | None = None
    if use_tavily:
        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise SystemExit("TAVILY_API_KEY is required with --use-tavily.")
        tavily = TavilyClient(
            api_key=api_key,
            base_url=os.environ.get("TAVILY_BASE_URL", "https://api.tavily.com"),
        )
        budget = TavilyCreditBudget(limit=max_credits)
    service = AcquisitionService(
        session,
        registry=build_collector_registry(
            greenhouse_base_url=os.environ.get(
                "GREENHOUSE_BASE_URL", "https://boards-api.greenhouse.io"
            )
        ),
    )
    try:
        async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}) as http:
            return await discover_boards(
                session,
                service=service,
                client=http,
                resolve_ips=_resolve_ips,
                apply=apply,
                limit=limit,
                tavily=tavily,
                budget=budget,
                min_interval_seconds=min_interval_seconds,
            )
    finally:
        if tavily is not None:
            await tavily.aclose()


def main() -> int:
    default_budget = int(
        os.environ.get(
            "TAVILY_CREDIT_BUDGET_PER_RUN",
            Settings.model_fields["tavily_credit_budget_per_run"].default,
        )
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write inert proposals (default: dry-run)"
    )
    parser.add_argument("--limit", type=int, help="consider at most this many companies")
    parser.add_argument(
        "--use-tavily",
        action="store_true",
        help="search Tavily for companies no known ATS answers for (spends credits)",
    )
    parser.add_argument(
        "--max-credits",
        type=int,
        default=default_budget,
        help=f"Tavily credit ceiling for this run (default: {default_budget})",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = asyncio.run(
            run(
                session,
                apply=args.apply,
                limit=args.limit,
                use_tavily=args.use_tavily,
                max_credits=args.max_credits,
            )
        )
    print(json.dumps(_report_json(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
