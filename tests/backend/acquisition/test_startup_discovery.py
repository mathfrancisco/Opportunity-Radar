"""F20-53: startup discovery over supported ATS domains, no network."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.startup_discovery import (
    ALLOWED_ATS_DOMAINS,
    ATS_DOMAIN_GROUPS,
    DEFAULT_STARTUP_TERMS,
    DISCOVERY_VIA,
    FORBIDDEN_DOMAINS,
    StartupBoard,
    StartupCandidate,
    StartupTerm,
    ValidatedStartup,
    company_key,
    company_name_from,
    is_allowed_ats_url,
    known_boards,
    propose_startups,
    search_startup_boards,
    validate_candidates,
)
from opportunity_radar.acquisition.tavily import (
    TavilyClient,
    TavilyCreditBudget,
    detect_ats_board,
)
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

PUBLIC_IP = "93.184.216.34"


def _tavily(
    handler: Callable[[dict[str, Any]], dict[str, Any]], seen: list[httpx.Request] | None = None
) -> TavilyClient:
    def transport(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, json=handler(json.loads(request.content)))

    return TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(transport)),
    )


def _payload(*urls: str, credits: int = 1, title: str = "Engineer") -> dict[str, Any]:
    return {
        "results": [
            {"url": url, "title": title, "content": "YC-backed startup", "score": 0.7}
            for url in urls
        ],
        "usage": {"credits": credits},
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _resolve(_host: str) -> tuple[str, ...]:
    return (PUBLIC_IP,)


async def _no_sleep(_seconds: float) -> None:
    return None


# --- query / domain allowlist -------------------------------------------------------------


def test_query_combines_term_with_supported_ats_domains_only() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(body: dict[str, Any]) -> dict[str, Any]:
        bodies.append(body)
        return _payload()

    _run(
        search_startup_boards(
            _tavily(handler), budget=TavilyCreditBudget(limit=50), terms=DEFAULT_STARTUP_TERMS
        )
    )

    assert len(bodies) == len(DEFAULT_STARTUP_TERMS) * len(ATS_DOMAIN_GROUPS)
    for body in bodies:
        assert body["include_domains"]
        assert set(body["include_domains"]) <= ALLOWED_ATS_DOMAINS
        assert not set(body["include_domains"]) & FORBIDDEN_DOMAINS
    assert {body["query"] for body in bodies} == {term.text for term in DEFAULT_STARTUP_TERMS}


def test_domain_group_outside_supported_ats_is_refused() -> None:
    with pytest.raises(ValueError):
        _run(
            search_startup_boards(
                _tavily(lambda _b: _payload()),
                budget=TavilyCreditBudget(limit=5),
                ats_groups={"waas": ("workatastartup.com",)},
            )
        )


def test_results_outside_supported_ats_domains_are_dropped_even_if_tavily_returns_them() -> None:
    urls = (
        "https://www.workatastartup.com/companies/acme",
        "https://wellfound.com/company/acme/jobs",
        "https://www.ycombinator.com/companies/acme",
        "https://acme.example/careers",
        "https://evil.com/jobs.ashbyhq.com/acme",
        "https://jobs.ashbyhq.com.evil.com/acme",
        "https://jobs.ashbyhq.com/goodco/123",
    )
    report = _run(
        search_startup_boards(
            _tavily(lambda _b: _payload(*urls)),
            terms=(StartupTerm('"Y Combinator"', "forte"),),
            ats_groups={"ashby": ("jobs.ashbyhq.com",)},
            budget=TavilyCreditBudget(limit=5),
        )
    )

    assert [c.name for c in report.candidates] == ["Goodco"]
    assert report.dropped_off_domain == len(urls) - 1
    assert all(is_allowed_ats_url(item.url or "") for item in report.items)


def test_no_request_of_the_routine_reaches_forbidden_hosts() -> None:
    hosts: list[str] = []

    def tavily_handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(
            200,
            json=_payload(
                "https://www.workatastartup.com/companies/acme",
                "https://jobs.lever.co/acme/1",
                "https://wellfound.com/company/acme",
            ),
        )

    def ats_handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(200, json=[{"id": "1"}])

    async def scenario() -> None:
        tavily = TavilyClient(
            api_key="k", client=httpx.AsyncClient(transport=httpx.MockTransport(tavily_handler))
        )
        report = await search_startup_boards(
            tavily, budget=TavilyCreditBudget(limit=50), ats_groups=ATS_DOMAIN_GROUPS
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(ats_handler)) as http:
            await validate_candidates(
                report.candidates,
                client=http,
                resolve_ips=_resolve,
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    _run(scenario())

    assert hosts
    for host in hosts:
        assert not any(host == d or host.endswith(f".{d}") for d in FORBIDDEN_DOMAINS)


def test_detect_ats_board_covers_all_supported_ats() -> None:
    assert detect_ats_board("https://job-boards.greenhouse.io/acme/jobs/1") == (
        "greenhouse",
        "acme",
    )
    assert detect_ats_board("https://apply.workable.com/acme/j/ABC") == ("workable", "acme")
    assert detect_ats_board("https://acme.teamtailor.com/jobs/1") == (
        "teamtailor",
        "acme.teamtailor.com",
    )
    assert detect_ats_board("https://www.teamtailor.com/pricing") is None


# --- strength -----------------------------------------------------------------------------


def test_signal_strength_and_term_are_recorded_in_item_metadata_per_term() -> None:
    def handler(body: dict[str, Any]) -> dict[str, Any]:
        slug = "strongco" if "Combinator" in body["query"] else "weakco"
        return _payload(f"https://jobs.lever.co/{slug}/1")

    report = _run(
        search_startup_boards(
            _tavily(handler),
            terms=(
                StartupTerm('"Y Combinator" remote', "forte"),
                StartupTerm('"seed stage" remote', "fraco"),
            ),
            ats_groups={"lever": ("jobs.lever.co",)},
            budget=TavilyCreditBudget(limit=5),
        )
    )

    by_url = {item.url: item.metadata for item in report.items}
    assert by_url["https://jobs.lever.co/strongco/1"]["startup_signal_strength"] == "forte"
    assert by_url["https://jobs.lever.co/strongco/1"]["startup_signal_term"] == (
        '"Y Combinator" remote'
    )
    assert by_url["https://jobs.lever.co/weakco/1"]["startup_signal_strength"] == "fraco"


def test_same_company_seen_with_strong_and_weak_terms_keeps_strong() -> None:
    report = _run(
        search_startup_boards(
            _tavily(lambda _b: _payload("https://jobs.lever.co/acme/1")),
            terms=(StartupTerm("seed", "fraco"), StartupTerm("YC", "forte")),
            ats_groups={"lever": ("jobs.lever.co",)},
            budget=TavilyCreditBudget(limit=5),
        )
    )

    assert len(report.candidates) == 1
    assert report.candidates[0].strength == "forte"
    assert report.candidates[0].terms == ("seed", "YC")


# --- dedupe -------------------------------------------------------------------------------


def test_company_key_matches_across_ats_and_numeric_suffix() -> None:
    assert company_key("weekday") == company_key("weekday-1") == "weekday"
    assert company_key("retell-ai") == company_key("retellai")
    assert company_name_from("retell-ai", "Engineer - Retell AI") == "Retell AI"
    assert company_name_from("weekday-1", None) == "Weekday"
    assert company_key("acme.teamtailor.com") == "acme"
    assert company_name_from("acme.teamtailor.com", None) == "Acme"


def test_same_company_in_two_ats_becomes_one_candidate_with_both_boards() -> None:
    def handler(body: dict[str, Any]) -> dict[str, Any]:
        if body["include_domains"] == ["jobs.lever.co"]:
            return _payload("https://jobs.lever.co/weekday/1")
        return _payload("https://apply.workable.com/weekday-1/j/2")

    report = _run(
        search_startup_boards(
            _tavily(handler),
            terms=(StartupTerm("YC", "forte"),),
            ats_groups={"lever": ("jobs.lever.co",), "workable": ("apply.workable.com",)},
            budget=TavilyCreditBudget(limit=5),
        )
    )

    assert len(report.candidates) == 1
    assert {(b.source_type, b.board_key) for b in report.candidates[0].boards} == {
        ("lever", "weekday"),
        ("workable", "weekday-1"),
    }


def test_boards_that_already_have_a_source_are_not_candidates() -> None:
    report = _run(
        search_startup_boards(
            _tavily(lambda _b: _payload("https://jobs.lever.co/known/1")),
            terms=(StartupTerm("YC", "forte"),),
            ats_groups={"lever": ("jobs.lever.co",)},
            known=frozenset({("lever", "known")}),
            budget=TavilyCreditBudget(limit=5),
        )
    )

    assert report.candidates == []
    assert report.dropped_known == 1


# --- shared budget ------------------------------------------------------------------------


def test_queries_share_the_tavily_budget_and_stop_at_the_ceiling() -> None:
    calls: list[int] = []

    def handler(_body: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return _payload("https://jobs.lever.co/acme/1")

    budget = TavilyCreditBudget(limit=2)
    report = _run(
        search_startup_boards(
            _tavily(handler),
            terms=DEFAULT_STARTUP_TERMS,
            budget=budget,
        )
    )

    assert len(calls) == 2
    assert report.budget_stopped is True
    assert report.credits_spent == 2
    assert budget.spent == 2 and budget.exhausted


def test_budget_already_spent_by_other_tavily_work_runs_no_query() -> None:
    calls: list[int] = []

    def handler(_body: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return _payload()

    report = _run(
        search_startup_boards(
            _tavily(handler), budget=TavilyCreditBudget(limit=3, spent=3)
        )
    )

    assert calls == []
    assert report.budget_stopped is True


# --- validation with probe_direct_ats -----------------------------------------------------


def _candidate(*boards: StartupBoard, name: str = "Acme") -> StartupCandidate:
    return StartupCandidate(
        name=name,
        key=company_key(boards[0].board_key),
        boards=boards,
        strength="forte",
        terms=("YC",),
        excerpt="YC-backed",
        score=0.8,
    )


def _validate(candidate: StartupCandidate, handler: Callable[[httpx.Request], httpx.Response]):
    async def scenario() -> list[ValidatedStartup]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await validate_candidates(
                [candidate],
                client=http,
                resolve_ips=_resolve,
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    return _run(scenario())[0]


def test_board_with_jobs_is_validated_by_direct_probe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.lever.co" and "/acme" in request.url.path:
            return httpx.Response(200, json=[{"id": "1"}])
        return httpx.Response(404, json={})

    result = _validate(
        _candidate(StartupBoard("lever", "acme", "https://jobs.lever.co/acme/1")), handler
    )

    assert result.board == StartupBoard("lever", "acme", "https://jobs.lever.co/acme/1")


def test_teamtailor_board_is_probed_by_subdomain_and_keeps_hostname_as_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "acme.teamtailor.com":
            return httpx.Response(200, json={"items": [{"id": "1"}]})
        return httpx.Response(404, json={})

    board = StartupBoard("teamtailor", "acme.teamtailor.com", "https://acme.teamtailor.com/jobs/1")

    assert _validate(_candidate(board), handler).board == board


def test_board_key_that_is_not_a_plain_slug_is_dropped() -> None:
    report = _run(
        search_startup_boards(
            _tavily(lambda _b: _payload("https://jobs.lever.co/bad%20key/1")),
            terms=(StartupTerm("YC", "forte"),),
            ats_groups={"lever": ("jobs.lever.co",)},
            budget=TavilyCreditBudget(limit=5),
        )
    )

    assert report.candidates == [] and report.dropped_invalid == 1


def test_board_that_probes_empty_or_missing_is_not_validated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.lever.co":
            return httpx.Response(200, json=[])
        return httpx.Response(404, json={})

    result = _validate(
        _candidate(StartupBoard("lever", "acme", "https://jobs.lever.co/acme/1")), handler
    )

    assert result.board is None


def test_probe_hit_on_a_board_the_search_did_not_name_is_ignored() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(200, json={"jobs": [{"id": "1"}]})
        return httpx.Response(404, json={})

    result = _validate(
        _candidate(StartupBoard("lever", "acme", "https://jobs.lever.co/acme/1")), handler
    )

    assert result.board is None


def test_second_board_validates_when_first_is_dead() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "apply.workable.com":
            return httpx.Response(200, json={"jobs": [{"id": "1"}]})
        return httpx.Response(404, json={})

    result = _validate(
        _candidate(
            StartupBoard("lever", "weekday", "https://jobs.lever.co/weekday/1"),
            StartupBoard("workable", "weekday-1", "https://apply.workable.com/weekday-1/j/2"),
        ),
        handler,
    )

    assert result.board is not None and result.board.source_type == "workable"


# --- proposals (database) -----------------------------------------------------------------

_PREFIX = "f20-53:"
_db = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as db:
        _purge(db)
        yield db
        db.rollback()
        _purge(db)


def _purge(db: Session) -> None:
    db.execute(
        delete(SourceDefinitionModel).where(
            SourceDefinitionModel.configuration["company_name"].as_string().startswith(_PREFIX)
        )
    )
    db.execute(delete(Company).where(Company.canonical_name.startswith(_PREFIX)))
    db.commit()


def _registry() -> CollectorRegistry:
    return build_collector_registry(greenhouse_base_url="https://boards-api.greenhouse.io")


def _validated(name: str, *boards: StartupBoard, primary: int = 0) -> ValidatedStartup:
    candidate = StartupCandidate(
        name=name,
        key=uuid4().hex,
        boards=boards,
        strength="forte",
        terms=('"Y Combinator" remote',),
        excerpt="YC S24 startup",
        score=0.9,
    )
    return ValidatedStartup(candidate, boards[primary], 1)


@_db
def test_validated_startup_becomes_inert_proposal_tagged_startup_search(session: Session) -> None:
    name = f"{_PREFIX}Acme {uuid4().hex[:6]}"
    board = StartupBoard("ashby", f"acme-{uuid4().hex[:6]}", "https://jobs.ashbyhq.com/x/1")
    board = StartupBoard(board.source_type, board.board_key, f"https://jobs.ashbyhq.com/{board.board_key}/1")

    outcomes = propose_startups(session, registry=_registry(), validated=[_validated(name, board)])
    session.commit()

    assert outcomes[0].outcome == "created"
    proposal = session.get(SourceDefinitionModel, outcomes[0].proposal_id)
    assert proposal is not None
    assert proposal.configuration["discovery_via"] == DISCOVERY_VIA == "tavily_startup_search"
    assert proposal.configuration["startup_signal_strength"] == "forte"
    assert proposal.configuration["board_identifier"] == board.board_key
    assert proposal.enabled is False
    assert proposal.terms_reviewed is False and proposal.collector_local_tested is False
    assert proposal.evidence_status == "ats_identified"


@_db
def test_cross_ats_company_yields_single_proposal_with_both_boards_as_evidence(
    session: Session,
) -> None:
    name = f"{_PREFIX}Weekday {uuid4().hex[:6]}"
    lever = StartupBoard("lever", f"wd{uuid4().hex[:6]}", "https://jobs.lever.co/wdx/1")
    workable = StartupBoard("workable", f"wd{uuid4().hex[:6]}", "https://apply.workable.com/wdy/j/1")

    outcomes = propose_startups(
        session,
        registry=_registry(),
        validated=[_validated(name, lever, workable, primary=1)],
    )
    session.commit()

    proposals = session.scalars(
        select(SourceDefinitionModel).where(
            SourceDefinitionModel.configuration["company_name"].as_string() == name
        )
    ).all()
    assert len(proposals) == 1
    assert outcomes[0].outcome == "created"
    assert proposals[0].source_type == "workable"
    assert proposals[0].configuration["startup_boards"] == [lever.url, workable.url]


@_db
def test_rerun_does_not_duplicate_startup_proposal(session: Session) -> None:
    name = f"{_PREFIX}Rerun {uuid4().hex[:6]}"
    key = f"rr{uuid4().hex[:8]}"
    board = StartupBoard("lever", key, f"https://jobs.lever.co/{key}/1")

    first = propose_startups(session, registry=_registry(), validated=[_validated(name, board)])
    session.commit()
    second = propose_startups(session, registry=_registry(), validated=[_validated(name, board)])
    session.commit()

    assert first[0].outcome == "created"
    assert second[0].outcome == "already_proposed"
    assert second[0].proposal_id == first[0].proposal_id


@_db
def test_unvalidated_startup_creates_no_company_or_proposal(session: Session) -> None:
    name = f"{_PREFIX}Ghost {uuid4().hex[:6]}"
    board = StartupBoard("lever", "ghost", "https://jobs.lever.co/ghost/1")
    candidate = _validated(name, board).candidate

    outcomes = propose_startups(
        session, registry=_registry(), validated=[ValidatedStartup(candidate, None, 3)]
    )

    assert outcomes[0].outcome == "probe_failed"
    assert session.scalar(select(Company).where(Company.canonical_name == name)) is None


@_db
def test_known_boards_lists_existing_sources(session: Session) -> None:
    name = f"{_PREFIX}Known {uuid4().hex[:6]}"
    key = f"kn{uuid4().hex[:8]}"
    board = StartupBoard("lever", key, f"https://jobs.lever.co/{key}/1")
    propose_startups(session, registry=_registry(), validated=[_validated(name, board)])
    session.commit()

    assert ("lever", key) in known_boards(session)
