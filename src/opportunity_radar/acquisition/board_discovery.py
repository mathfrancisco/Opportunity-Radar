"""Find ATS boards for catalogue companies that have no source yet (R55-B6).

For each active company with no `SourceDefinition` (enabled, disabled or proposed), in
order of cost:

1. cheap public probes of the known ATS APIs (`probe_direct_ats`, plus the inHire tenant
   route) using slugs derived from the company name and domain: no credits spent;
2. only when no known ATS answers, and only when the caller handed in a Tavily client, one
   Tavily search restricted to the supported ATS domains, charged against the caller's
   `TavilyCreditBudget` (`tavily_credit_budget_per_run`). A search hit is accepted only if
   its board key names the company, and is then confirmed by the ATS's own public API.

A found board becomes an inert proposal through the existing
`AcquisitionService.propose_from_tavily_evidence` path, the same homologation queue the
other discovery routes feed: `enabled=false`, no terms review, no local test. Nothing here
enables a source. Re-running finds those companies already covered and skips them.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionTelemetry,
)
from opportunity_radar.acquisition.limited_discovery import (
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    direct_slug_candidates,
    endpoint_ats_name,
    is_public_destination,
    probe_direct_ats,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.proposals import IDENTIFIER_KEYS
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.startup_discovery import (
    ALLOWED_ATS_DOMAINS,
    _board_url_of,
    board_label,
    company_key,
    is_allowed_ats_url,
    known_boards,
)
from opportunity_radar.acquisition.tavily import (
    TavilyClient,
    TavilyCreditBudget,
    detect_ats_board,
)
from opportunity_radar.companies.models import Company, CompanySource

DISCOVERY_VIA_PROBE = "board_discovery_probe"
DISCOVERY_VIA_TAVILY = "board_discovery_tavily"

_INHIRE_PAGES_URL = "https://api.inhire.app/job-posts/public/pages"
_INHIRE_TENANT = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_VALID_BOARD_KEY = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}", re.IGNORECASE)

#: Labels that sit at the end of a domain and name a registry, not a company: a probe for
#: `empresa.com.br` must never try the slug `com`.
PUBLIC_SUFFIX_LABELS = frozenset(
    {
        "com", "co", "org", "net", "gov", "edu", "mil", "int", "info", "biz", "app", "dev",
        "io", "ai", "br", "pt", "uk", "us", "eu", "de", "fr", "es", "mx", "ar", "cl", "ac",
        "www", "me", "tv", "xyz", "tech", "online", "site",
    }
)  # fmt: skip
MIN_SLUG_LENGTH = 3
#: After this many Tavily failures in a row the run stops searching.
MAX_CONSECUTIVE_TAVILY_ERRORS = 3

ResolveIps = Callable[[str], Awaitable[tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class BoardHit:
    source_type: str
    board_key: str
    board_url: str
    via: str
    evidence: str


@dataclass(frozen=True, slots=True)
class CompanyOutcome:
    company: str
    outcome: str
    source_type: str | None = None
    board_key: str | None = None
    via: str | None = None
    proposal_id: UUID | None = None


@dataclass(slots=True)
class BoardDiscoveryReport:
    outcomes: list[CompanyOutcome] = field(default_factory=list)
    companies_considered: int = 0
    skipped_with_source: int = 0
    tavily_queries: int = 0
    tavily_credits_spent: int = 0
    tavily_budget_stopped: bool = False
    tavily_disabled_after_errors: bool = False
    tavily_consecutive_errors: int = 0
    skipped_recent_attempt: int = 0
    #: Companies no board was found for, with whether the paid search was part of it.
    attempts: list[tuple[Company, bool]] = field(default_factory=list)


def covered_company_ids(session: Session) -> set[UUID]:
    """Companies that already own a `SourceDefinition` in any state.

    A source belongs to a company through its `company_source` link or, for proposals
    born from search evidence, through `configuration.company_name`.
    """
    covered: set[UUID] = set()
    linked = session.scalars(
        select(CompanySource.company_id)
        .join(SourceDefinitionModel, SourceDefinitionModel.company_source_id == CompanySource.id)
        .distinct()
    )
    covered.update(linked)
    names = {
        name
        for name in session.scalars(
            select(SourceDefinitionModel.configuration["company_name"].as_string())
        )
        if name
    }
    if names:
        covered.update(session.scalars(select(Company.id).where(Company.canonical_name.in_(names))))
    return covered


def recently_attempted(
    company: Company, *, retry_days: int, tavily_enabled: bool, now: datetime
) -> bool:
    """True when an earlier run already came up empty for `company` inside the window.

    A probe-only attempt does not shield the company from a run that uses Tavily.
    """
    attempted = company.board_discovery_attempted_at
    if retry_days <= 0 or attempted is None:
        return False
    if attempted.tzinfo is None:
        attempted = attempted.replace(tzinfo=UTC)
    if now - attempted >= timedelta(days=retry_days):
        return False
    return bool(company.board_discovery_used_tavily) or not tavily_enabled


def eligible_companies(session: Session) -> tuple[list[Company], int]:
    """Active companies without any source, plus how many were skipped for having one.

    A company whose catalogue already names a proposable board is left to
    `scripts/discover_sources.py`, which proposes it with no network access.
    """
    covered = covered_company_ids(session)
    with_catalog_board = set(
        session.scalars(
            select(CompanySource.company_id).where(
                CompanySource.source_type.in_(tuple(IDENTIFIER_KEYS)),
                CompanySource.external_key.is_not(None),
            )
        )
    )
    skipped = 0
    eligible: list[Company] = []
    for company in session.scalars(
        select(Company).where(Company.radar_status == "active").order_by(Company.canonical_name)
    ):
        if company.id in covered or company.id in with_catalog_board:
            skipped += 1
            continue
        eligible.append(company)
    return eligible, skipped


async def probe_inhire(
    slugs: Iterable[str],
    *,
    client: httpx.AsyncClient,
    resolve_ips: ResolveIps,
    user_agent: str = DEFAULT_USER_AGENT,
) -> BoardHit | None:
    """The inHire public pages route, one request per tenant guess; a populated
    `jobsPage` is a real board."""
    host = "api.inhire.app"
    if not is_public_destination(host, await resolve_ips(host)):
        return None
    for slug in slugs:
        if not _INHIRE_TENANT.fullmatch(slug):
            continue
        try:
            response = await client.get(
                _INHIRE_PAGES_URL,
                headers={"X-Tenant": slug, "User-Agent": user_agent},
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            payload = response.json() if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            continue
        jobs = payload.get("jobsPage") if isinstance(payload, dict) else None
        if isinstance(jobs, list) and jobs:
            return BoardHit(
                "inhire",
                slug,
                f"https://{slug}.inhire.app",
                DISCOVERY_VIA_PROBE,
                f"direct probe tenant={slug!r}",
            )
    return None


def _hit_from_endpoint(endpoint: Any, via: str) -> BoardHit | None:
    ats = endpoint_ats_name(endpoint)
    detected = detect_ats_board(_board_url_of(ats, endpoint.discovered_url))
    if ats is None or detected is None or detected[0] != ats:
        return None
    source_type, board_key = detected
    board_url = f"https://{board_key}" if source_type == "teamtailor" else None
    return BoardHit(
        source_type,
        board_key,
        board_url or _board_url_of(ats, endpoint.discovered_url),
        via,
        endpoint.evidence_excerpt,
    )


def probe_slugs(company: Company) -> tuple[str, ...]:
    """Slugs worth a request: they must name the company (same `company_key` rule as the
    Tavily route), be at least `MIN_SLUG_LENGTH` long and never a public-suffix label."""
    wanted = company_key(company.canonical_name)
    seed_url = f"https://{company.domain}" if company.domain else ""
    return tuple(
        slug
        for slug in direct_slug_candidates(company.canonical_name, seed_url)
        if len(slug) >= MIN_SLUG_LENGTH
        and slug not in PUBLIC_SUFFIX_LABELS
        and wanted
        and company_key(slug) == wanted
    )


async def probe_known_ats(
    company: Company,
    *,
    client: httpx.AsyncClient,
    resolve_ips: ResolveIps,
    min_interval_seconds: float,
    sleeper: Callable[[float], Awaitable[None]],
) -> BoardHit | None:
    seed_url = f"https://{company.domain}" if company.domain else ""
    slugs = probe_slugs(company)
    if not slugs:
        return None
    wanted = company_key(company.canonical_name)
    endpoint, _requests = await probe_direct_ats(
        company.id,
        company.canonical_name,
        seed_url,
        client=client,
        resolve_ips=resolve_ips,
        min_interval_seconds=min_interval_seconds,
        sleeper=sleeper,
        max_requests=len(slugs) * 5,
        slugs=slugs,
    )
    if endpoint is not None:
        hit = _hit_from_endpoint(endpoint, DISCOVERY_VIA_PROBE)
        if hit is not None and company_key(hit.board_key) == wanted:
            return hit
    return await probe_inhire(slugs, client=client, resolve_ips=resolve_ips)


async def _confirm_board(
    company: Company,
    source_type: str,
    board_key: str,
    *,
    client: httpx.AsyncClient,
    resolve_ips: ResolveIps,
    min_interval_seconds: float,
    sleeper: Callable[[float], Awaitable[None]],
) -> BoardHit | None:
    """The ATS's own public API must answer for exactly the board the search named."""
    if source_type == "inhire":
        return await probe_inhire([board_key], client=client, resolve_ips=resolve_ips)
    endpoint, _requests = await probe_direct_ats(
        company.id,
        company.canonical_name,
        "",
        client=client,
        resolve_ips=resolve_ips,
        min_interval_seconds=min_interval_seconds,
        sleeper=sleeper,
        max_requests=1,
        slugs=(board_label(board_key),),
        only_ats=(source_type,),
    )
    if endpoint is None:
        return None
    hit = _hit_from_endpoint(endpoint, DISCOVERY_VIA_TAVILY)
    if hit is None or (hit.source_type, hit.board_key) != (source_type, board_key):
        return None
    return hit


async def search_tavily(
    company: Company,
    *,
    tavily: TavilyClient,
    budget: TavilyCreditBudget,
    report: BoardDiscoveryReport,
    client: httpx.AsyncClient,
    resolve_ips: ResolveIps,
    min_interval_seconds: float,
    sleeper: Callable[[float], Awaitable[None]],
) -> BoardHit | None:
    """One search for the company's board on the supported ATS domains, within `budget`.

    Raises `AcquisitionError(CREDIT_BUDGET_EXCEEDED)` before the call when the ceiling is
    already reached; the caller treats that as a deliberate stop.
    """
    budget.ensure_can_call()
    telemetry = CollectionTelemetry()
    try:
        # `basic` depth costs one credit, which `ensure_can_call` just proved is left.
        response = await tavily.search(
            query=f'"{company.canonical_name}" careers jobs',
            max_results=10,
            search_depth="basic",
            time_range=None,
            include_domains=sorted(ALLOWED_ATS_DOMAINS),
            telemetry=telemetry,
        )
    except Exception:
        # The call may have been billed before it failed: count the minimum, never zero.
        budget.charge(1)
        report.tavily_queries += 1
        report.tavily_credits_spent += 1
        raise
    spent = response.credits_used or telemetry.credits_used or 1
    budget.charge(spent)
    report.tavily_queries += 1
    report.tavily_credits_spent += spent
    wanted = company_key(company.canonical_name)
    seen: set[tuple[str, str]] = set()
    for result in response.results:
        if not is_allowed_ats_url(result.url):
            continue
        detected = detect_ats_board(result.url)
        if detected is None or detected in seen or not _VALID_BOARD_KEY.fullmatch(detected[1]):
            continue
        seen.add(detected)
        # A search result is evidence of a board, not authority over whose it is: the
        # board key has to name the company.
        if not wanted or company_key(detected[1]) != wanted:
            continue
        hit = await _confirm_board(
            company,
            *detected,
            client=client,
            resolve_ips=resolve_ips,
            min_interval_seconds=min_interval_seconds,
            sleeper=sleeper,
        )
        if hit is not None:
            return hit
    return None


async def find_boards(
    companies: Iterable[Company],
    *,
    client: httpx.AsyncClient,
    resolve_ips: ResolveIps,
    known: frozenset[tuple[str, str]] = frozenset(),
    tavily: TavilyClient | None = None,
    budget: TavilyCreditBudget | None = None,
    min_interval_seconds: float = 1.0,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    report: BoardDiscoveryReport | None = None,
) -> tuple[list[tuple[Company, BoardHit]], BoardDiscoveryReport]:
    """Resolve each company to a board: known-ATS probes first, Tavily only as the fallback."""
    report = report if report is not None else BoardDiscoveryReport()
    found: list[tuple[Company, BoardHit]] = []
    claimed = set(known)  # boards that already have a source
    for company in companies:
        report.companies_considered += 1
        name = company.canonical_name
        try:
            hit = await probe_known_ats(
                company,
                client=client,
                resolve_ips=resolve_ips,
                min_interval_seconds=min_interval_seconds,
                sleeper=sleeper,
            )
        except Exception:  # noqa: BLE001 - one company's failure never sinks the batch
            report.outcomes.append(CompanyOutcome(name, "probe_error"))
            continue
        used_tavily = False
        if hit is None and tavily is not None and budget is not None:
            if report.tavily_disabled_after_errors:
                report.outcomes.append(CompanyOutcome(name, "no_match_tavily_disabled"))
                report.attempts.append((company, False))
                continue
            if report.tavily_budget_stopped:
                report.outcomes.append(CompanyOutcome(name, "no_match_tavily_budget_exhausted"))
                report.attempts.append((company, False))
                continue
            try:
                hit = await search_tavily(
                    company,
                    tavily=tavily,
                    budget=budget,
                    report=report,
                    client=client,
                    resolve_ips=resolve_ips,
                    min_interval_seconds=min_interval_seconds,
                    sleeper=sleeper,
                )
                report.tavily_consecutive_errors = 0
                used_tavily = True
            except Exception as error:  # noqa: BLE001 - a failed search never sinks the batch
                if (
                    isinstance(error, AcquisitionError)
                    and error.code is AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED
                ):
                    report.tavily_budget_stopped = True
                    report.outcomes.append(CompanyOutcome(name, "no_match_tavily_budget_exhausted"))
                else:
                    report.tavily_consecutive_errors += 1
                    if report.tavily_consecutive_errors >= MAX_CONSECUTIVE_TAVILY_ERRORS:
                        report.tavily_disabled_after_errors = True
                    report.outcomes.append(CompanyOutcome(name, "tavily_error"))
                report.attempts.append((company, False))
                continue
        if hit is None:
            report.outcomes.append(CompanyOutcome(name, "no_match"))
            report.attempts.append((company, used_tavily))
            continue
        if (hit.source_type, hit.board_key) in claimed:
            report.outcomes.append(
                CompanyOutcome(name, "board_already_known", hit.source_type, hit.board_key, hit.via)
            )
            if hit.via == DISCOVERY_VIA_TAVILY:
                report.attempts.append((company, True))  # the credit is spent: do not repeat
            continue
        found.append((company, hit))
    return found, report


def propose_boards(
    session: Session,
    found: Iterable[tuple[Company, BoardHit]],
    *,
    service: AcquisitionService,
    report: BoardDiscoveryReport,
    apply: bool,
) -> None:
    """Hand each found board to the existing proposal queue (inert, `enabled=false`).

    Without `apply` nothing is written and the outcome is `would_propose`.
    """
    claimed: set[tuple[str, str]] = set()
    for company, hit in found:
        name = company.canonical_name
        board = (hit.source_type, hit.board_key)
        if board in claimed:
            report.outcomes.append(
                CompanyOutcome(name, "board_already_known", hit.source_type, hit.board_key, hit.via)
            )
            if apply and hit.via == DISCOVERY_VIA_TAVILY:
                report.attempts.append((company, True))
            continue
        if not apply:
            claimed.add(board)
            report.outcomes.append(
                CompanyOutcome(name, "would_propose", hit.source_type, hit.board_key, hit.via)
            )
            continue
        item = CollectedItem(
            source_type="tavily_search",
            url=hit.board_url,
            company_name=name,
            description=None,
            raw_payload={"url": hit.board_url},
            metadata={"source_proposal_candidate": True, "query": hit.evidence},
        )
        try:
            with session.begin_nested():
                proposal_report = service.propose_from_tavily_evidence(
                    (item,), commit=False, discovery_via=hit.via
                )
        except AcquisitionError as error:
            report.outcomes.append(
                CompanyOutcome(
                    name, f"rejected: {error.summary}", hit.source_type, hit.board_key, hit.via
                )
            )
            if hit.via == DISCOVERY_VIA_TAVILY:
                report.attempts.append((company, True))
            continue
        outcome = proposal_report.outcomes[0]
        if outcome.outcome in {"created", "already_proposed"}:
            claimed.add(board)
        report.outcomes.append(
            CompanyOutcome(
                name,
                outcome.outcome,
                hit.source_type,
                hit.board_key,
                hit.via,
                outcome.proposal_id,
            )
        )
    if apply:
        session.commit()


async def discover_boards(
    session: Session,
    *,
    service: AcquisitionService,
    client: httpx.AsyncClient,
    resolve_ips: ResolveIps,
    apply: bool = False,
    limit: int | None = None,
    companies: Sequence[Company] | None = None,
    tavily: TavilyClient | None = None,
    budget: TavilyCreditBudget | None = None,
    min_interval_seconds: float = 1.0,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retry_days: int = 14,
    now: datetime | None = None,
) -> BoardDiscoveryReport:
    """`companies` narrows the run to those given (still only if eligible).

    A company an earlier `apply` run found nothing for within `retry_days` is skipped
    (`retry_days=0` disables the window).
    """
    eligible, skipped = eligible_companies(session)
    if companies is not None:
        wanted = {company.id for company in companies}
        eligible = [company for company in eligible if company.id in wanted]
    moment = now or datetime.now(UTC)
    fresh = [
        company
        for company in eligible
        if not recently_attempted(
            company,
            retry_days=retry_days,
            tavily_enabled=tavily is not None and budget is not None,
            now=moment,
        )
    ]
    companies = fresh
    if limit is not None:
        companies = companies[: max(0, limit)]
    report = BoardDiscoveryReport(
        skipped_with_source=skipped, skipped_recent_attempt=len(eligible) - len(fresh)
    )
    found, report = await find_boards(
        companies,
        client=client,
        resolve_ips=resolve_ips,
        known=known_boards(session),
        tavily=tavily,
        budget=budget,
        min_interval_seconds=min_interval_seconds,
        sleeper=sleeper,
        report=report,
    )
    propose_boards(session, found, service=service, report=report, apply=apply)
    if apply:
        for company, used_tavily in report.attempts:
            company.board_discovery_attempted_at = moment
            company.board_discovery_used_tavily = used_tavily
        session.commit()
    return report
