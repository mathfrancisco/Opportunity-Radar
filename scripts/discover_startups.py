"""Search Tavily for startup boards on supported ATS domains and queue proposals (F20-53).

Off by default: a manual run. Spends Tavily credits against a per-run ceiling
(`--max-credits`, the F20-43 budget), validates every board with the ATS's own public API
(`probe_direct_ats`) and writes only inert proposals (`discovery_via=tavily_startup_search`).
It never enables a source; homologation stays with `enable_sources.py` / the interface.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict

import httpx
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.limited_discovery import (
    DEFAULT_USER_AGENT,
    default_resolve_ips,
)
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.startup_discovery import (
    known_boards,
    propose_startups,
    search_startup_boards,
    validate_candidates,
)
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyCreditBudget
from opportunity_radar.platform.database import create_database_engine


async def _resolve_ips(host: str) -> tuple[str, ...]:
    return await asyncio.to_thread(default_resolve_ips, host)


async def run(
    session: Session, *, max_credits: int, dry_run: bool, save_report: str | None = None
) -> dict[str, object]:
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise SystemExit("TAVILY_API_KEY is required.")
    client = TavilyClient(
        api_key=api_key, base_url=os.environ.get("TAVILY_BASE_URL", "https://api.tavily.com")
    )
    try:
        report = await search_startup_boards(
            client,
            budget=TavilyCreditBudget(limit=max_credits),
            known=known_boards(session),
        )
    finally:
        await client.aclose()
    if save_report:
        # Paid results must survive a later failure: written before anything else runs.
        with open(save_report, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "credits_spent": report.credits_spent,
                    "candidates": [asdict(c) for c in report.candidates],
                    "items": [
                        {"url": i.url, "title": i.title, "metadata": i.metadata}
                        for i in report.items
                    ],
                },
                handle,
                ensure_ascii=False,
                indent=1,
                default=str,
            )
    async with httpx.AsyncClient(headers={"User-Agent": DEFAULT_USER_AGENT}) as http:
        validated = await validate_candidates(
            report.candidates, client=http, resolve_ips=_resolve_ips
        )
    outcomes = []
    if not dry_run:
        outcomes = propose_startups(
            session,
            validated,
            registry=build_collector_registry(
                greenhouse_base_url=os.environ.get(
                    "GREENHOUSE_BASE_URL", "https://boards-api.greenhouse.io"
                )
            ),
        )
        session.commit()
    return {
        "queries_run": report.queries_run,
        "credits_spent": report.credits_spent,
        "results_seen": report.results_seen,
        "dropped_off_domain": report.dropped_off_domain,
        "dropped_known": report.dropped_known,
        "dropped_invalid": report.dropped_invalid,
        "budget_stopped": report.budget_stopped,
        "candidates": len(report.candidates),
        "validated": sum(1 for entry in validated if entry.board is not None),
        "validation": [
            {
                "name": entry.candidate.name,
                "strength": entry.candidate.strength,
                "boards": [board.url for board in entry.candidate.boards],
                "validated_board": entry.board.url if entry.board else None,
                "terms": list(entry.candidate.terms),
            }
            for entry in validated
        ],
        "proposals": [
            {key: str(value) for key, value in asdict(outcome).items()} for outcome in outcomes
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-credits", type=int, default=20)
    parser.add_argument("--save-report", help="write the raw search result here first")
    parser.add_argument("--dry-run", action="store_true", help="search and probe, write nothing")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = asyncio.run(
            run(
                session,
                max_credits=args.max_credits,
                dry_run=args.dry_run,
                save_report=args.save_report,
            )
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
