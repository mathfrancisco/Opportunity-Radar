"""Startup discovery through Tavily searches restricted to supported ATS domains (F20-53).

Not a new collector: it drives the existing `TavilySearchCollector` (F20-44) with a startup
signal term and an `include_domains` list limited to the ATS domains the radar already
collects (SPEC 45). The board found in the result is validated with `probe_direct_ats`
(F20-27/F20-36) and only then handed to `propose_from_tavily_evidence` (F20-46), tagged
`discovery_via="tavily_startup_search"`. Nothing here talks to Wellfound, Y Combinator or
Work at a Startup, and nothing enables a source: homologation stays with F20-25.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.concurrency import HostSerializer
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionRequest,
    CollectionTelemetry,
)
from opportunity_radar.acquisition.limited_discovery import (
    endpoint_ats_name,
    probe_direct_ats,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.proposals import IDENTIFIER_KEYS
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import (
    TavilyClient,
    TavilyCreditBudget,
    TavilySearchCollector,
    detect_ats_board,
)
from opportunity_radar.companies.domain import (
    AmbiguousCompanyIdentityError,
    CompanyCandidate,
    normalize_name,
)
from opportunity_radar.companies.repository import CompanyRepository
from opportunity_radar.companies.service import CompanyService
from opportunity_radar.companies.startup import derive_startup_evidence, record_startup_evidence

DISCOVERY_VIA = "tavily_startup_search"

#: Search domains grouped per ATS, so one query never lets a single ATS crowd out the rest.
ATS_DOMAIN_GROUPS: dict[str, tuple[str, ...]] = {
    "ashby": ("jobs.ashbyhq.com",),
    "greenhouse": ("boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("jobs.lever.co",),
    "workable": ("apply.workable.com",),
    "teamtailor": ("teamtailor.com",),
}
#: Every domain a startup search may name or accept; nothing outside this list is ever sent
#: to Tavily as `include_domains` or accepted from its results.
ALLOWED_ATS_DOMAINS: frozenset[str] = frozenset(
    domain for group in ATS_DOMAIN_GROUPS.values() for domain in group
)
#: Closed non-viable sources (F20-51, F20-52): refused even if someone adds them above.
FORBIDDEN_DOMAINS: frozenset[str] = frozenset(
    {"wellfound.com", "ycombinator.com", "workatastartup.com"}
)

#: A board key is a plain slug; anything else (encoded, spaced) would be refused by the
#: collectors anyway, so it never becomes a candidate.
_VALID_BOARD_KEY = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}", re.IGNORECASE)

Strength = Literal["forte", "fraco"]
_STRENGTH_ORDER: dict[str, int] = {"forte": 1, "fraco": 0}


@dataclass(frozen=True, slots=True)
class StartupTerm:
    """A startup signal term. `forte` names a brand (YC / "Y Combinator"); `fraco` is a
    stage word alone, which the pilot showed yields false positives (SPEC 45 §2)."""

    text: str
    strength: Strength


DEFAULT_STARTUP_TERMS: tuple[StartupTerm, ...] = (
    StartupTerm('"Y Combinator" startup remote', "forte"),
    StartupTerm('"YC" backed startup hiring remote', "forte"),
    StartupTerm('"seed stage" OR "Series A" startup remote', "fraco"),
)


@dataclass(frozen=True, slots=True)
class StartupBoard:
    source_type: str
    board_key: str
    url: str


@dataclass(frozen=True, slots=True)
class StartupCandidate:
    name: str
    key: str
    boards: tuple[StartupBoard, ...]
    strength: Strength
    terms: tuple[str, ...]
    excerpt: str | None
    score: float | None


@dataclass(slots=True)
class StartupSearchReport:
    candidates: list[StartupCandidate] = field(default_factory=list)
    #: Accepted ATS results, each carrying its signal term and strength in `metadata`.
    items: list[CollectedItem] = field(default_factory=list)
    queries_run: int = 0
    credits_spent: int = 0
    results_seen: int = 0
    dropped_off_domain: int = 0
    dropped_known: int = 0
    dropped_invalid: int = 0
    budget_stopped: bool = False


@dataclass(frozen=True, slots=True)
class ValidatedStartup:
    candidate: StartupCandidate
    board: StartupBoard | None
    http_requests: int


@dataclass(frozen=True, slots=True)
class StartupProposalOutcome:
    name: str
    outcome: str
    board_url: str | None = None
    proposal_id: Any = None


def is_allowed_ats_url(url: str) -> bool:
    """True only for an http(s) URL on a supported ATS domain (or its subdomain)."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").casefold()
    if parts.scheme not in {"http", "https"} or not host:
        return False
    if any(host == d or host.endswith(f".{d}") for d in FORBIDDEN_DOMAINS):
        return False
    return any(host == d or host.endswith(f".{d}") for d in ALLOWED_ATS_DOMAINS)


def _alnum(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_name(value))


def board_label(board_key: str) -> str:
    """The company-ish part of a board key (a Teamtailor key is a full hostname)."""
    return board_key.removesuffix(".teamtailor.com")


def company_key(board_key: str) -> str:
    """Comparison key for the same company across ATS: `weekday` and `weekday-1` agree."""
    label = board_label(board_key)
    stripped = re.sub(r"[-_]?\d+$", "", label)
    base = stripped if len(_alnum(stripped)) >= 3 else label
    return _alnum(base)


def company_name_from(board_key: str, title: str | None) -> str:
    """A display name: the title's trailing company segment when it matches the board key,
    else the humanized board key. Never guesses beyond the two."""
    key = company_key(board_key)
    if title:
        for segment in reversed(re.split(r"\s+(?:at|@|-|–|—|\|)\s+", title.strip())):
            segment = segment.strip()
            if segment and _alnum(segment) == key:
                return segment
    label = board_label(board_key)
    words = re.split(r"[-_]+", re.sub(r"[-_]?\d+$", "", label))
    return " ".join(word.capitalize() for word in words if word) or label


def _stronger(first: Strength, second: Strength) -> Strength:
    return first if _STRENGTH_ORDER[first] >= _STRENGTH_ORDER[second] else second


def known_boards(session: Session) -> frozenset[tuple[str, str]]:
    """Boards that already have any `SourceDefinition` (proposed, disabled or enabled)."""
    pairs: set[tuple[str, str]] = set()
    for source_type, configuration in session.execute(
        select(SourceDefinitionModel.source_type, SourceDefinitionModel.configuration)
    ):
        key = IDENTIFIER_KEYS.get(source_type)
        value = (configuration or {}).get(key) if key else None
        if isinstance(value, str):
            pairs.add((source_type, value))
    return frozenset(pairs)


async def search_startup_boards(
    client: TavilyClient,
    *,
    terms: Sequence[StartupTerm] = DEFAULT_STARTUP_TERMS,
    ats_groups: dict[str, tuple[str, ...]] | None = None,
    budget: TavilyCreditBudget,
    known: frozenset[tuple[str, str]] = frozenset(),
    max_results: int = 10,
    time_range: str = "year",
) -> StartupSearchReport:
    """One Tavily query per (term, ATS group), sharing the caller's credit `budget`.

    A query that would start past the ceiling stops the cycle (`budget_stopped`), the same
    "deliberate stop, not a failure" treatment F20-43 gives a run.
    """
    groups = ats_groups if ats_groups is not None else ATS_DOMAIN_GROUPS
    for domains in groups.values():
        if not set(domains) <= ALLOWED_ATS_DOMAINS:
            raise ValueError("startup search domains must be supported ATS domains")
    report = StartupSearchReport()
    # key -> accumulated pieces of a candidate
    merged: dict[str, dict[str, Any]] = {}
    for term in terms:
        for domains in groups.values():
            try:
                budget.ensure_can_call()
            except AcquisitionError as error:
                if error.code is not AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED:
                    raise
                report.budget_stopped = True
                return _finish(report, merged)
            collector = TavilySearchCollector(
                client=client,
                time_range=time_range,
                include_domains=domains,
                max_results=max_results,
            )
            telemetry = CollectionTelemetry()
            request = CollectionRequest(
                keywords=(term.text,), telemetry=telemetry, known_ats_boards=known
            )
            items = [item async for item in collector.discover(request)]
            # Tavily always reports usage (`include_usage`); if a reply omitted it, count
            # the cheapest tier (1 credit) rather than let a query go unbudgeted.
            spent = telemetry.credits_used or 1
            budget.charge(spent)
            report.queries_run += 1
            report.credits_spent += spent
            for item in items:
                report.results_seen += 1
                tagged = replace(
                    item,
                    metadata={
                        **item.metadata,
                        "startup_signal_term": term.text,
                        "startup_signal_strength": term.strength,
                    },
                )
                _absorb(report, merged, tagged, term, known)
    return _finish(report, merged)


def _absorb(
    report: StartupSearchReport,
    merged: dict[str, dict[str, Any]],
    item: CollectedItem,
    term: StartupTerm,
    known: frozenset[tuple[str, str]],
) -> None:
    url = item.url or ""
    detected = detect_ats_board(url) if is_allowed_ats_url(url) else None
    if detected is None:
        report.dropped_off_domain += 1
        return
    source_type, board_key = detected
    if not _VALID_BOARD_KEY.fullmatch(board_key):
        report.dropped_invalid += 1
        return
    if (source_type, board_key) in known:
        report.dropped_known += 1
        return
    key = company_key(board_key)
    if not key:
        report.dropped_off_domain += 1
        return
    report.items.append(item)
    board = StartupBoard(source_type, board_key, url)
    score = item.metadata.get("score")
    entry = merged.setdefault(
        key,
        {
            "name": company_name_from(board_key, item.title),
            "boards": [],
            "strength": term.strength,
            "terms": [],
            "excerpt": item.description,
            "score": score,
        },
    )
    if all((b.source_type, b.board_key) != (source_type, board_key) for b in entry["boards"]):
        entry["boards"].append(board)
    if term.text not in entry["terms"]:
        entry["terms"].append(term.text)
    if _STRENGTH_ORDER[term.strength] > _STRENGTH_ORDER[entry["strength"]]:
        entry["excerpt"] = item.description or entry["excerpt"]
    entry["strength"] = _stronger(entry["strength"], term.strength)
    if isinstance(score, int | float) and (
        not isinstance(entry["score"], int | float) or score > entry["score"]
    ):
        entry["score"] = score


def _finish(
    report: StartupSearchReport, merged: dict[str, dict[str, Any]]
) -> StartupSearchReport:
    report.candidates = [
        StartupCandidate(
            name=entry["name"],
            key=key,
            boards=tuple(entry["boards"]),
            strength=entry["strength"],
            terms=tuple(entry["terms"]),
            excerpt=entry["excerpt"],
            score=entry["score"] if isinstance(entry["score"], int | float) else None,
        )
        for key, entry in merged.items()
    ]
    return report


async def validate_candidates(
    candidates: Iterable[StartupCandidate],
    *,
    client: httpx.AsyncClient,
    resolve_ips: Callable[[str], Awaitable[tuple[str, ...]]],
    concurrency: int = 4,
    min_interval_seconds: float = 1.0,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_requests: int = 2,
) -> list[ValidatedStartup]:
    """Probe each candidate's boards with `probe_direct_ats`; the first board whose real
    ATS API answers with jobs is the candidate's validated board. A probe hit on a board
    the search did not name is ignored: identity is never guessed from a slug."""
    serializer = HostSerializer(min_interval_seconds=min_interval_seconds)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(candidate: StartupCandidate) -> ValidatedStartup:
        requests = 0
        wanted = {(b.source_type, b.board_key) for b in candidate.boards}
        for board in candidate.boards:
            async with semaphore, serializer.lock_for(board.source_type):
                await serializer.wait_turn(board.source_type)
                endpoint, made = await probe_direct_ats(
                    uuid5(NAMESPACE_URL, f"startup:{candidate.key}"),
                    board.board_key,
                    board.url,
                    client=client,
                    resolve_ips=resolve_ips,
                    min_interval_seconds=min_interval_seconds,
                    sleeper=sleeper,
                    max_requests=max_requests,
                    slugs=(board_label(board.board_key),),
                    only_ats=(board.source_type,),
                )
            requests += made
            if endpoint is None:
                continue
            ats = endpoint_ats_name(endpoint)
            hit = detect_ats_board(_board_url_of(ats, endpoint.discovered_url))
            if ats is not None and hit is not None and hit in wanted:
                matched = next(
                    b for b in candidate.boards if (b.source_type, b.board_key) == hit
                )
                return ValidatedStartup(candidate, matched, requests)
        return ValidatedStartup(candidate, None, requests)

    return list(await asyncio.gather(*(one(candidate) for candidate in candidates)))


def _board_url_of(ats: str | None, api_url: str) -> str:
    """Map a probed public API URL back to the board URL `detect_ats_board` understands."""
    parts = urlsplit(api_url)
    segments = [segment for segment in parts.path.split("/") if segment]
    if ats == "ashby" and segments:
        return f"https://jobs.ashbyhq.com/{segments[-1]}"
    if ats == "greenhouse" and "boards" in segments:
        return f"https://boards.greenhouse.io/{segments[segments.index('boards') + 1]}"
    if ats == "lever" and segments:
        return f"https://jobs.lever.co/{segments[-1]}"
    if ats == "workable" and segments:
        return f"https://apply.workable.com/{segments[-1]}"
    if ats == "teamtailor":
        return api_url
    return ""


def _record_evidence(
    session: Session, company_id: UUID, candidate: StartupCandidate, board: StartupBoard
) -> None:
    """Attach the discovery signal to the company (F20-54), whatever the proposal outcome:
    the sighting is about the company, and identical sightings are idempotent."""
    derived = derive_startup_evidence(
        strong_term=candidate.strength == "forte",
        term=candidate.terms[0] if candidate.terms else "",
        excerpt=candidate.excerpt,
    )
    record_startup_evidence(
        session,
        company_id,
        signal=derived.signal,
        strength=derived.strength,
        source_text=derived.source_text,
        source_url=board.url,
        batch=derived.batch,
    )


def propose_startups(
    session: Session,
    validated: Iterable[ValidatedStartup],
    *,
    registry: CollectorRegistry | None = None,
) -> list[StartupProposalOutcome]:
    """Feed validated startups to the F20-25/F20-46 proposal queue, one proposal per
    company: the validated board is the proposal, every board found stays as evidence."""
    company_service = CompanyService(CompanyRepository(session))
    acquisition = AcquisitionService(session, registry=registry)
    outcomes: list[StartupProposalOutcome] = []
    items: list[CollectedItem] = []
    # Evidence attaches to the company, which exists once `reconcile` returned it, so the
    # wiring point is here (not in `search_startup_boards`, which has no company yet).
    pending: list[tuple[UUID, StartupCandidate, StartupBoard]] = []
    for entry in validated:
        candidate, board = entry.candidate, entry.board
        if board is None:
            outcomes.append(StartupProposalOutcome(candidate.name, "probe_failed"))
            continue
        try:
            result = company_service.reconcile(CompanyCandidate(name=candidate.name))
        except AmbiguousCompanyIdentityError:
            outcomes.append(StartupProposalOutcome(candidate.name, "company_ambiguous"))
            continue
        if result.company is None:
            outcomes.append(StartupProposalOutcome(candidate.name, "invalid_name"))
            continue
        pending.append((result.company.id, candidate, board))
        items.append(
            CollectedItem(
                source_type="tavily_search",
                url=board.url,
                company_name=result.company.canonical_name,
                description=candidate.excerpt,
                raw_payload={"url": board.url},
                metadata={
                    "source_proposal_candidate": True,
                    "query": " | ".join(candidate.terms),
                    "score": candidate.score,
                    "startup_signal_strength": candidate.strength,
                    "startup_signal_terms": list(candidate.terms),
                    "startup_boards": [b.url for b in candidate.boards],
                },
            )
        )
    for item, (company_id, candidate, board) in zip(items, pending, strict=True):
        try:
            with session.begin_nested():
                report = acquisition.propose_from_tavily_evidence(
                    (item,), commit=False, discovery_via=DISCOVERY_VIA
                )
        except AcquisitionError as error:
            rejected = f"rejected: {error.summary}"
            outcomes.append(StartupProposalOutcome(item.company_name or "", rejected, item.url))
            continue
        outcome = report.outcomes[0]
        _record_evidence(session, company_id, candidate, board)
        outcomes.append(
            StartupProposalOutcome(
                item.company_name or "", outcome.outcome, item.url, outcome.proposal_id
            )
        )
    return outcomes
