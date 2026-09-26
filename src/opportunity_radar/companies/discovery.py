"""ATS discovery: one request to a careers page, looking for the board hiding behind it
(F20-26 dependency chain successor: F20-27).

Many of the 115+ companies with a confirmed careers page and no known ATS are a plain
shell around an Ashby, Greenhouse, Lever, Gupy or Teamtailor board, embedded by link,
iframe or script. This module makes exactly one polite GET per eligible company, looks
for a known ATS signature in the response, and records what it found — never a
`SourceRun` or a `RawItem`: discovery is research, not collection (SPEC 43).

Out of scope here: a headless browser for JavaScript-rendered pages (SPEC SS16), and
enabling a source — a discovery only produces evidence; the proposal still needs a probe
and homologation.
"""

from __future__ import annotations

import re
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company, CompanySource, DiscoveryAttemptModel

#: Domain (or domain suffix, when it starts with ".") each ATS publishes its boards or
#: embeds under. Matched against `href`, `iframe src` and `script src` values.
ATS_SIGNATURES: dict[str, tuple[str, ...]] = {
    "ashby": ("jobs.ashbyhq.com",),
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "gupy": (".gupy.io",),
    "teamtailor": (".teamtailor.com",),
    "workable": ("apply.workable.com",),
    "workday": (".myworkdayjobs.com",),
    "factorial": (".factorialhr.com",),
}

#: A company already checked within this many days is not checked again (SPEC 43).
DEFAULT_REVISIT_INTERVAL_DAYS = 30

_ATTRIBUTE_URL = re.compile(
    r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)

DEFAULT_USER_AGENT = "OpportunityRadarDiscoveryBot/1.0 (+https://opportunity-radar.invalid)"
DEFAULT_TIMEOUT_SECONDS = 10.0
#: One request per second across the whole run, in the same spirit as
#: `CollectionNetworkPolicy.minimum_interval_seconds` (`acquisition/domain.py:146`).
DEFAULT_MINIMUM_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    company_id: UUID
    checked_url: str
    final_url: str
    http_status: int | None
    ats_found: str | None
    evidence_snippet: str | None


def detect_ats(html: str) -> str | None:
    """Match `ATS_SIGNATURES` against every `href`, `iframe src` and `script src` value.

    Returns the first ATS whose signature is found, or `None`. Order follows
    `ATS_SIGNATURES` insertion order, which is deterministic.
    """
    urls = _ATTRIBUTE_URL.findall(html)
    for ats, signatures in ATS_SIGNATURES.items():
        for signature in signatures:
            for url in urls:
                if signature in url:
                    return ats
    return None


def _evidence_snippet(html: str, ats: str) -> str | None:
    for signature in ATS_SIGNATURES[ats]:
        index = html.find(signature)
        if index == -1:
            continue
        start = max(0, index - 60)
        end = min(len(html), index + len(signature) + 60)
        return html[start:end].strip()
    return None


def eligible_companies(
    session: Session,
    *,
    now: datetime | None = None,
    revisit_interval_days: int = DEFAULT_REVISIT_INTERVAL_DAYS,
) -> list[Company]:
    """Companies with a confirmed careers page, no known ATS, and no recent attempt.

    "Known ATS" means a `CompanySource` whose `source_type` is one of
    `ATS_SIGNATURES`'s keys; a plain `careers` source does not count.
    """
    moment = now or datetime.now(UTC)
    cutoff = moment - timedelta(days=revisit_interval_days)

    companies = session.scalars(
        select(Company).order_by(Company.canonical_name)
    ).all()
    result: list[Company] = []
    for company in companies:
        careers_confirmed = any(
            source.source_type == "careers"
            and source.verification_status == "careers_confirmed"
            for source in company.sources
        )
        if not careers_confirmed:
            continue
        has_known_ats = any(
            source.source_type in ATS_SIGNATURES for source in company.sources
        )
        if has_known_ats:
            continue
        recent_attempt = session.scalar(
            select(DiscoveryAttemptModel.id).where(
                DiscoveryAttemptModel.company_id == company.id,
                DiscoveryAttemptModel.attempted_at >= cutoff,
            )
        )
        if recent_attempt is not None:
            continue
        result.append(company)
    return result


def _careers_url(company: Company) -> str | None:
    for source in company.sources:
        if source.source_type == "careers" and source.verification_status == (
            "careers_confirmed"
        ):
            return source.endpoint
    return None


class RobotsDisallowedError(Exception):
    """`robots.txt` forbids fetching this URL; discovery skips it."""


async def discover_one(
    company: Company,
    *,
    client: httpx.AsyncClient,
    robots_checker: Callable[[str], bool],
    user_agent: str = DEFAULT_USER_AGENT,
) -> DiscoveryOutcome:
    """One GET at the company's careers page. Never follows a link into the site."""
    checked_url = _careers_url(company)
    if checked_url is None:
        raise ValueError(f"company {company.id} has no confirmed careers URL")
    if not robots_checker(checked_url):
        return DiscoveryOutcome(
            company_id=company.id,
            checked_url=checked_url,
            final_url=checked_url,
            http_status=None,
            ats_found=None,
            evidence_snippet=None,
        )
    response = await client.get(
        checked_url,
        headers={"User-Agent": user_agent},
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    final_url = str(response.url)
    ats_found = detect_ats(response.text) if response.status_code < 400 else None
    evidence = _evidence_snippet(response.text, ats_found) if ats_found else None
    return DiscoveryOutcome(
        company_id=company.id,
        checked_url=checked_url,
        final_url=final_url,
        http_status=response.status_code,
        ats_found=ats_found,
        evidence_snippet=evidence,
    )


def robots_allows(url: str, *, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """A synchronous `robots.txt` check, cacheable per host by the caller."""
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except OSError:
        # No reachable robots.txt: proceed, matching the RFC's own guidance that an
        # absent robots.txt means no restriction.
        return True
    return parser.can_fetch(user_agent, url)


def record_discovery_attempt(
    session: Session, outcome: DiscoveryOutcome
) -> DiscoveryAttemptModel:
    attempt = DiscoveryAttemptModel(
        company_id=outcome.company_id,
        checked_url=outcome.checked_url,
        http_status=outcome.http_status,
        ats_found=outcome.ats_found,
        attempted_at=datetime.now(UTC),
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def record_ats_identified(session: Session, outcome: DiscoveryOutcome) -> CompanySource | None:
    """A `CompanySource` for the discovered ATS, `discovery` method, `ats_identified`.

    Written directly (not through `registration.add_source`/`_source_values`, which
    require a collector-supported ATS): several signatures here (Workday, Teamtailor,
    Workable, Factorial, Gupy) have no collector yet, the same reason
    `import_research_catalog.py` writes `CompanySource` rows directly.
    """
    if outcome.ats_found is None:
        return None
    source = CompanySource(
        company_id=outcome.company_id,
        source_type=outcome.ats_found,
        endpoint=outcome.final_url,
        verification_method="discovery",
        verification_status="ats_identified",
        evidence_note=outcome.evidence_snippet,
        last_verified_at=datetime.now(UTC),
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source
