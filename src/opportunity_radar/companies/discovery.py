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

from opportunity_radar.acquisition.tavily import detect_ats_board
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
    "inhire": (".inhire.app",),
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
    #: The ATS board URL found in the fetched HTML, when it is a supported public board.
    ats_url: str | None = None


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


def _confirmed_ats_url(html: str, ats: str) -> str | None:
    """Return the public board URL which supplied the ATS evidence, without fetching it."""
    for url in _ATTRIBUTE_URL.findall(html):
        parts = urlsplit(url)
        if parts.scheme.casefold() not in {"http", "https"}:
            continue
        detected = detect_ats_board(url)
        if detected is not None and detected[0] == ats:
            return url
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
    ats_url = _confirmed_ats_url(response.text, ats_found) if ats_found else None
    return DiscoveryOutcome(
        company_id=company.id,
        checked_url=checked_url,
        final_url=final_url,
        http_status=response.status_code,
        ats_found=ats_found,
        evidence_snippet=evidence,
        ats_url=ats_url,
    )


def _fetch_robots(robots_url: str, user_agent: str) -> httpx.Response:
    return httpx.get(
        robots_url,
        headers={"User-Agent": user_agent},
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=True,
    )


def robots_allows(url: str, *, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """A synchronous `robots.txt` check, cacheable per host by the caller.

    `robots.txt` is fetched with the product's own User-Agent (many sites answer 403 to
    a library default) and evaluated for that same agent. Per RFC 9309: 2xx is parsed;
    404/410 and other 4xx mean no restrictions; 5xx and network errors mean unreachable,
    hence disallowed. 401/403 stay disallowed, the conservative reading the RFC permits.
    """
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = _fetch_robots(robots_url, user_agent)
    except httpx.HTTPError:
        return False
    status = response.status_code
    if status in {401, 403}:
        return False
    if 400 <= status < 500:
        return True
    if not 200 <= status < 300:
        return False
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
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


def external_key_from_confirmed_ats_url(ats: str, final_url: str) -> str | None:
    """Return a collector identifier only when the confirmed URL proves one.

    The direct ATS probe records public API URLs, whereas page discovery records public
    board URLs.  Convert the former to the latter shape before sharing the existing
    board parser.  A URL for a different ATS (or an unsupported ATS) is deliberately
    ignored: evidence alone must not create a collectable proposal.
    """
    parts = urlsplit(final_url)
    host = (parts.hostname or "").casefold()
    segments = [segment for segment in parts.path.split("/") if segment]
    board_url = final_url
    if ats == "ashby" and host == "api.ashbyhq.com" and segments:
        if segments[:-1] == ["posting-api", "job-board"]:
            board_url = f"https://jobs.ashbyhq.com/{segments[-1]}"
    elif ats == "greenhouse" and host == "boards-api.greenhouse.io":
        if len(segments) >= 3 and segments[:2] == ["v1", "boards"]:
            board_url = f"https://boards.greenhouse.io/{segments[2]}"
    elif ats == "lever" and host == "api.lever.co":
        if len(segments) >= 3 and segments[:2] == ["v0", "postings"]:
            board_url = f"https://jobs.lever.co/{segments[2]}"
    elif ats == "workable" and host == "apply.workable.com":
        if (
            len(segments) >= 5
            and segments[:4] == ["api", "v1", "widget", "accounts"]
        ):
            board_url = f"https://apply.workable.com/{segments[4]}"

    detected = detect_ats_board(board_url)
    if detected is None or detected[0] != ats:
        return None
    return detected[1]


def record_ats_identified(session: Session, outcome: DiscoveryOutcome) -> CompanySource | None:
    """A `CompanySource` for the discovered ATS, `discovery` method, `ats_identified`.

    Written directly (not through `registration.add_source`/`_source_values`, which
    require a collector-supported ATS): several signatures here (Workday, Teamtailor,
    Workable, Factorial, Gupy) have no collector yet, the same reason
    `import_research_catalog.py` writes `CompanySource` rows directly.
    """
    if outcome.ats_found is None:
        return None
    external_key = external_key_from_confirmed_ats_url(
        outcome.ats_found, outcome.ats_url or outcome.final_url
    )
    endpoint = outcome.ats_url or outcome.final_url
    source = session.scalar(
        select(CompanySource)
        .where(
            CompanySource.company_id == outcome.company_id,
            CompanySource.source_type == outcome.ats_found,
            (
                (CompanySource.endpoint == endpoint)
                if external_key is None
                else (
                    (CompanySource.endpoint == endpoint)
                    | (CompanySource.external_key == external_key)
                )
            ),
        )
        .order_by(CompanySource.id)
    )
    if source is None:
        source = CompanySource(
            company_id=outcome.company_id,
            source_type=outcome.ats_found,
            endpoint=endpoint,
            external_key=external_key,
            verification_method="discovery",
            verification_status="ats_identified",
            evidence_note=outcome.evidence_snippet,
            last_verified_at=datetime.now(UTC),
        )
        session.add(source)
    else:
        # A repeated discovery refreshes the auditable evidence without creating another
        # CompanySource row.  Keep an existing endpoint when only the key matched: both
        # URLs are confirmed, and changing it would obscure the original evidence.
        source.external_key = external_key or source.external_key
        source.verification_method = "discovery"
        source.verification_status = "ats_identified"
        source.evidence_note = outcome.evidence_snippet or source.evidence_note
        source.last_verified_at = datetime.now(UTC)
    session.commit()
    session.refresh(source)
    return source
