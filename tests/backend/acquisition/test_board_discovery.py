"""R55-B6: board discovery for catalogue companies, no real network.

Every HTTP client is a `MockTransport`; DNS is a fake that answers a public address. The
database tests run only in the isolated `*_test` database.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.board_discovery import (
    DISCOVERY_VIA_PROBE,
    DISCOVERY_VIA_TAVILY,
    BoardDiscoveryReport,
    discover_boards,
    eligible_companies,
    probe_inhire,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyCreditBudget
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

PUBLIC_IP = "93.184.216.34"
_PREFIX = "R55b6 "

_requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


async def _resolve(_host: str) -> tuple[str, ...]:
    return (PUBLIC_IP,)


async def _no_sleep(_seconds: float) -> None:
    return None


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class Net:
    """Mock HTTP world: ATS probes answer by host+path substring, Tavily by callback."""

    def __init__(
        self,
        *,
        boards: dict[str, Any] | None = None,
        tavily: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.boards = boards or {}
        self.tavily_handler = tavily
        self.requests: list[httpx.Request] = []
        self.tavily_calls = 0

    def _ats(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        for needle, payload in self.boards.items():
            if needle in url or (
                needle.startswith("tenant:")
                and request.headers.get("X-Tenant") == needle.removeprefix("tenant:")
            ):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    def _tavily(self, request: httpx.Request) -> httpx.Response:
        self.tavily_calls += 1
        assert self.tavily_handler is not None
        return httpx.Response(200, json=self.tavily_handler(json.loads(request.content)))

    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._ats))

    def tavily_client(self) -> TavilyClient:
        return TavilyClient(
            api_key="test-key",
            client=httpx.AsyncClient(transport=httpx.MockTransport(self._tavily)),
        )


def _tavily_results(*urls: str, credits: int = 1) -> dict[str, Any]:
    return {
        "results": [{"url": u, "title": "Jobs", "content": "x", "score": 0.5} for u in urls],
        "usage": {"credits": credits},
    }


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


def _company(session: Session, name: str, *, domain: str | None = None) -> Company:
    company = Company(
        canonical_name=f"{_PREFIX}{name}",
        normalized_name=f"r55b6-{name.lower().replace(' ', '-')}",
        domain=domain,
    )
    session.add(company)
    session.commit()
    return company


def _service(session: Session) -> AcquisitionService:
    return AcquisitionService(session, registry=build_collector_registry())


def _discover(
    session: Session,
    net: Net,
    companies: list[Company],
    *,
    apply: bool,
    tavily: bool = False,
    budget: TavilyCreditBudget | None = None,
) -> BoardDiscoveryReport:
    async def scenario() -> BoardDiscoveryReport:
        tclient = net.tavily_client() if tavily else None
        async with net.http() as http:
            return await discover_boards(
                session,
                service=_service(session),
                client=http,
                resolve_ips=_resolve,
                apply=apply,
                companies=companies,
                tavily=tclient,
                budget=budget,
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    return _run(scenario())


def _proposals(session: Session) -> list[SourceDefinitionModel]:
    return list(
        session.scalars(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.configuration["company_name"].as_string().startswith(_PREFIX)
            )
        )
    )


# --- inHire probe (no database) -----------------------------------------------------------


def test_inhire_probe_accepts_a_populated_tenant_and_rejects_empty_or_bad_slugs() -> None:
    net = Net(boards={"tenant:acme": {"tenantName": "Acme", "jobsPage": [{"jobId": "1"}]}})

    async def scenario() -> tuple[Any, Any]:
        async with net.http() as http:
            hit = await probe_inhire(
                ["bad slug", "nope", "acme"], client=http, resolve_ips=_resolve
            )
            empty = await probe_inhire(["nope"], client=http, resolve_ips=_resolve)
            return hit, empty

    hit, empty = _run(scenario())

    assert (hit.source_type, hit.board_key, hit.board_url) == (
        "inhire",
        "acme",
        "https://acme.inhire.app",
    )
    assert empty is None


# --- positive -----------------------------------------------------------------------------


@_requires_database
def test_known_ats_found_creates_a_disabled_proposal_in_the_queue(session: Session) -> None:
    company = _company(session, "Acme Co")
    net = Net(boards={"/v1/boards/r55b6-acme-co/jobs": {"jobs": [{"id": 1}]}})

    report = _discover(session, net, [company], apply=True)

    proposals = _proposals(session)
    assert [o.outcome for o in report.outcomes] == ["created"]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.source_type == "greenhouse"
    assert proposal.enabled is False
    assert proposal.terms_reviewed is False
    assert proposal.collector_local_tested is False
    assert proposal.evidence_status == "ats_identified"
    assert proposal.name == f"Proposed {company.canonical_name} greenhouse"
    assert proposal.configuration["board_token"] == "r55b6-acme-co"
    assert proposal.configuration["discovery_via"] == DISCOVERY_VIA_PROBE
    assert report.tavily_queries == 0


@_requires_database
def test_dry_run_reports_the_board_and_writes_nothing(session: Session) -> None:
    company = _company(session, "Acme Co")
    net = Net(boards={"/v1/boards/r55b6-acme-co/jobs": {"jobs": [{"id": 1}]}})

    report = _discover(session, net, [company], apply=False)

    assert [(o.outcome, o.source_type) for o in report.outcomes] == [
        ("would_propose", "greenhouse")
    ]
    assert _proposals(session) == []


@_requires_database
def test_tavily_is_used_only_when_no_known_ats_matches_and_the_board_is_confirmed(
    session: Session,
) -> None:
    probed = _company(session, "Probed Co")
    searched = _company(session, "Zeta Labs")
    # Lever answers only for the exact board key the search names, which no name-derived
    # slug guess equals, so the probe misses and the search is the only way to find it.
    net = Net(
        boards={
            "/v1/boards/r55b6-probed-co/jobs": {"jobs": [{"id": 1}]},
            "/v0/postings/r55b6zeta-labs": [{"id": "a"}],
        },
        tavily=lambda _body: _tavily_results(
            "https://jobs.lever.co/r55b6zeta-labs/abc",
            "https://jobs.lever.co/someone-else/abc",
            "https://example.com/careers",
        ),
    )

    report = _discover(
        session,
        net,
        [probed, searched],
        apply=True,
        tavily=True,
        budget=TavilyCreditBudget(limit=10),
    )

    by_company = {p.configuration["company_name"]: p for p in _proposals(session)}
    assert by_company[probed.canonical_name].configuration["discovery_via"] == DISCOVERY_VIA_PROBE
    assert by_company[searched.canonical_name].source_type == "lever"
    assert by_company[searched.canonical_name].configuration["discovery_via"] == (
        DISCOVERY_VIA_TAVILY
    )
    assert all(p.enabled is False for p in by_company.values())
    # Tavily was asked only for the company no known ATS answered for.
    assert net.tavily_calls == 1
    assert report.tavily_queries == 1 and report.tavily_credits_spent == 1


# --- negative -----------------------------------------------------------------------------


@_requires_database
def test_no_match_creates_nothing(session: Session) -> None:
    company = _company(session, "Ghost Inc")

    report = _discover(session, Net(), [company], apply=True)

    assert [o.outcome for o in report.outcomes] == ["no_match"]
    assert _proposals(session) == []


@_requires_database
def test_tavily_result_for_another_company_or_unconfirmed_board_is_ignored(
    session: Session,
) -> None:
    company = _company(session, "Ghost Inc")
    net = Net(
        tavily=lambda _b: _tavily_results(
            "https://jobs.lever.co/unrelated/1",  # key does not name the company
            "https://jobs.lever.co/r55b6-ghost-inc/1",  # names it, but the API says no board
        )
    )

    report = _discover(
        session, net, [company], apply=True, tavily=True, budget=TavilyCreditBudget(limit=5)
    )

    assert [o.outcome for o in report.outcomes] == ["no_match"]
    assert _proposals(session) == []


@_requires_database
def test_tavily_stops_at_the_credit_budget_while_probes_keep_running(session: Session) -> None:
    companies = [_company(session, f"Miss {n}") for n in range(4)]
    late = _company(session, "Zz Late Co")
    net = Net(
        boards={"/v1/boards/r55b6-zz-late-co/jobs": {"jobs": [{"id": 1}]}},
        tavily=lambda _b: _tavily_results(),
    )
    budget = TavilyCreditBudget(limit=2)

    report = _discover(session, net, [*companies, late], apply=True, tavily=True, budget=budget)

    assert net.tavily_calls == 2
    assert budget.spent == 2 and budget.exhausted
    assert report.tavily_budget_stopped is True
    assert report.tavily_credits_spent == 2
    outcomes = {o.company: o.outcome for o in report.outcomes}
    assert outcomes[late.canonical_name] == "created"
    exhausted = [o for o in outcomes.values() if o == "no_match_tavily_budget_exhausted"]
    assert len(exhausted) == 2


@_requires_database
def test_a_budget_already_spent_makes_no_tavily_call(session: Session) -> None:
    company = _company(session, "Ghost Inc")
    net = Net(tavily=lambda _b: _tavily_results())

    report = _discover(
        session,
        net,
        [company],
        apply=True,
        tavily=True,
        budget=TavilyCreditBudget(limit=3, spent=3),
    )

    assert net.tavily_calls == 0
    assert report.tavily_budget_stopped is True


@_requires_database
def test_tavily_stays_off_without_a_client(session: Session) -> None:
    company = _company(session, "Ghost Inc")
    net = Net(tavily=lambda _b: _tavily_results())

    _discover(session, net, [company], apply=True)

    assert net.tavily_calls == 0


@_requires_database
def test_company_with_an_existing_source_is_skipped_without_any_request(
    session: Session,
) -> None:
    covered = _company(session, "Covered Co")
    _service(session).create_source(
        source_type="greenhouse",
        name=f"Proposed {covered.canonical_name} greenhouse",
        configuration={"company_name": covered.canonical_name, "board_token": "covered"},
        evidence_status="ats_identified",
    )
    net = Net(boards={"covered": {"jobs": [{"id": 1}]}})

    eligible, skipped = eligible_companies(session)
    report = _discover(session, net, [covered], apply=True)

    assert covered.id not in {c.id for c in eligible}
    assert skipped >= 1
    assert report.companies_considered == 0
    assert net.requests == []
    assert len(_proposals(session)) == 1


@_requires_database
def test_rerun_does_not_duplicate_proposals(session: Session) -> None:
    company = _company(session, "Acme Co")
    net = Net(boards={"/v1/boards/r55b6-acme-co/jobs": {"jobs": [{"id": 1}]}})

    first = _discover(session, net, [company], apply=True)
    second = _discover(session, net, [company], apply=True)

    assert [o.outcome for o in first.outcomes] == ["created"]
    assert second.companies_considered == 0
    count = session.scalar(
        select(func.count())
        .select_from(SourceDefinitionModel)
        .where(SourceDefinitionModel.configuration["company_name"].as_string().startswith(_PREFIX))
    )
    assert count == 1


@_requires_database
def test_board_already_owned_by_another_source_is_not_proposed_twice(session: Session) -> None:
    owner = _company(session, "Owner Co")
    twin = _company(session, "Twin Co")
    _service(session).create_source(
        source_type="greenhouse",
        name="Proposed shared greenhouse",
        configuration={"company_name": owner.canonical_name, "board_token": "r55b6-twin-co"},
        evidence_status="ats_identified",
    )
    net = Net(boards={"/v1/boards/r55b6-twin-co/jobs": {"jobs": [{"id": 1}]}})

    report = _discover(session, net, [twin], apply=True)

    assert [o.outcome for o in report.outcomes] == ["board_already_known"]
    assert len(_proposals(session)) == 1
