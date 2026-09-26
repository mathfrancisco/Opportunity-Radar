"""Discover the ATS behind a company's careers page, one request per eligible company.

Card F20-27. Off by default: this is a manual `make discover-ats` run (or a low-frequency
job an operator turns on separately), never part of the collection schedule.
"""

from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlsplit

import httpx
from sqlalchemy.orm import Session

from opportunity_radar.companies.discovery import (
    DEFAULT_USER_AGENT,
    discover_one,
    eligible_companies,
    record_ats_identified,
    record_discovery_attempt,
    robots_allows,
)
from opportunity_radar.platform.database import create_database_engine


async def run_discovery(session: Session) -> dict[str, object]:
    report: dict[str, object] = {"checked": 0, "by_ats": {}, "no_ats_found": 0}
    by_ats: dict[str, int] = {}
    companies = eligible_companies(session)
    robots_cache: dict[str, bool] = {}

    def cached_robots_checker(url: str) -> bool:
        host = urlsplit(url).netloc
        if host not in robots_cache:
            robots_cache[host] = robots_allows(url, user_agent=DEFAULT_USER_AGENT)
        return robots_cache[host]

    async with httpx.AsyncClient() as client:
        for company in companies:
            outcome = await discover_one(
                company, client=client, robots_checker=cached_robots_checker
            )
            record_discovery_attempt(session, outcome)
            report["checked"] = int(report["checked"]) + 1
            if outcome.ats_found is not None:
                record_ats_identified(session, outcome)
                by_ats[outcome.ats_found] = by_ats.get(outcome.ats_found, 0) + 1
            else:
                report["no_ats_found"] = int(report["no_ats_found"]) + 1
            # One request per second across the whole run.
            await asyncio.sleep(1.0)

    report["by_ats"] = by_ats
    return report


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = asyncio.run(run_discovery(session))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
