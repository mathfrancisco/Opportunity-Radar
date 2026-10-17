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
    BoardHit,
    discover_boards,
    eligible_companies,
    probe_inhire,
    probe_known_ats,
    probe_slugs,
    propose_boards,
)
from opportunity_radar.acquisition.domain import AcquisitionError, AcquisitionErrorCode
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyCreditBudget
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine
from scripts import discover_boards as cli

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
    tavily_client: Any = None,
    retry_days: int = 14,
) -> BoardDiscoveryReport:
    async def scenario() -> BoardDiscoveryReport:
        tclient = tavily_client or (net.tavily_client() if tavily else None)
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
                retry_days=retry_days,
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


# --- identity: slug luck is not a match ---------------------------------------------------


def test_probe_slugs_drop_public_suffix_short_and_unrelated_labels() -> None:
    br = Company(canonical_name="R55b6 Empresa", normalized_name="x", domain="empresa.com.br")
    other = Company(canonical_name="R55b6 Delta Labs", normalized_name="y", domain="gamma.io")
    short = Company(canonical_name="Ab", normalized_name="z", domain="ab.com")

    assert "com" not in probe_slugs(br)
    assert probe_slugs(br) == ("r55b6empresa", "r55b6-empresa")
    assert "gamma" not in probe_slugs(other)
    assert probe_slugs(short) == ()


def test_com_br_domain_never_probes_the_com_slug() -> None:
    company = Company(canonical_name="R55b6 Empresa", normalized_name="x", domain="empresa.com.br")
    net = Net()

    async def scenario() -> Any:
        async with net.http() as http:
            return await probe_known_ats(
                company,
                client=http,
                resolve_ips=_resolve,
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    assert _run(scenario()) is None
    urls = [str(r.url) for r in net.requests]
    assert urls
    assert not any(
        marker in url
        for url in urls
        for marker in ("/boards/com/", "/postings/com", "/job-board/com", "/accounts/com", "//com.")
    )
    assert not any(r.headers.get("X-Tenant") == "com" for r in net.requests)


@_requires_database
def test_slug_collision_with_another_companys_board_is_not_a_match(session: Session) -> None:
    company = Company(
        canonical_name=f"{_PREFIX}Delta Labs", normalized_name="r55b6-delta-labs", domain="gamma.io"
    )
    session.add(company)
    session.commit()
    # The domain label `gamma` is somebody else's live board.
    net = Net(boards={"/v1/boards/gamma/jobs": {"jobs": [{"id": 1}]}})

    report = _discover(session, net, [company], apply=True)

    assert [o.outcome for o in report.outcomes] == ["no_match"]
    assert _proposals(session) == []
    assert not any("/boards/gamma/" in str(r.url) for r in net.requests)


# --- hit shape ----------------------------------------------------------------------------


@_requires_database
def test_teamtailor_hit_uses_the_career_site_host_as_key_and_url(session: Session) -> None:
    company = _company(session, "Tt Co")
    net = Net(
        boards={"r55b6-tt-co.teamtailor.com/jobs.json": {"items": [{"id": 1}]}},
    )

    async def probe() -> Any:
        async with net.http() as http:
            return await probe_known_ats(
                company,
                client=http,
                resolve_ips=_resolve,
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    hit = _run(probe())
    report = _discover(session, net, [company], apply=True)

    assert (hit.source_type, hit.board_key, hit.board_url) == (
        "teamtailor",
        "r55b6-tt-co.teamtailor.com",
        "https://r55b6-tt-co.teamtailor.com",
    )
    assert [o.outcome for o in report.outcomes] == ["created"]
    (proposal,) = _proposals(session)
    assert proposal.source_type == "teamtailor"
    assert proposal.configuration["company_identifier"] == "r55b6-tt-co.teamtailor.com"
    assert proposal.enabled is False


# --- apply: rejected proposals roll back and do not claim the board ------------------------


def _failing_once(service: AcquisitionService) -> Callable[..., Any]:
    real = service.create_source
    calls = {"n": 0}

    def create_source(**kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise AcquisitionError(AcquisitionErrorCode.INVALID_CONFIGURATION, "boom")
        return real(**kwargs)

    return create_source


@_requires_database
def test_rejected_proposal_rolls_back_and_the_board_is_not_claimed(session: Session) -> None:
    first = _company(session, "Rej One")
    second = _company(session, "Rej Two")
    service = _service(session)
    service.create_source = _failing_once(service)  # type: ignore[method-assign]
    shared = BoardHit(
        "greenhouse",
        "r55b6-shared",
        "https://boards.greenhouse.io/r55b6-shared",
        DISCOVERY_VIA_PROBE,
        "direct probe",
    )
    report = BoardDiscoveryReport()

    propose_boards(
        session, [(first, shared), (second, shared)], service=service, report=report, apply=True
    )

    assert report.outcomes[0].outcome.startswith("rejected")
    assert report.outcomes[1].outcome == "created"
    assert [p.configuration["company_name"] for p in _proposals(session)] == [second.canonical_name]


@_requires_database
def test_apply_with_a_rejected_proposal_leaves_nothing_and_no_attempt_stamp(
    session: Session,
) -> None:
    company = _company(session, "Acme Co")
    net = Net(boards={"/v1/boards/r55b6-acme-co/jobs": {"jobs": [{"id": 1}]}})
    service = _service(session)
    service.create_source = _failing_once(service)  # type: ignore[method-assign]

    async def scenario() -> BoardDiscoveryReport:
        async with net.http() as http:
            return await discover_boards(
                session,
                service=service,
                client=http,
                resolve_ips=_resolve,
                apply=True,
                companies=[company],
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    report = _run(scenario())

    assert report.outcomes[0].outcome.startswith("rejected")
    assert _proposals(session) == []
    session.refresh(company)
    assert company.board_discovery_attempted_at is None
    assert session.scalar(select(func.count()).select_from(Company)) >= 1  # session usable


# --- reruns do not re-probe or re-spend ----------------------------------------------------


@_requires_database
def test_rerun_skips_a_recently_attempted_company_and_spends_no_more_credits(
    session: Session,
) -> None:
    company = _company(session, "Ghost Inc")
    net = Net(tavily=lambda _b: _tavily_results())

    first = _discover(
        session, net, [company], apply=True, tavily=True, budget=TavilyCreditBudget(limit=10)
    )
    requests_after_first = len(net.requests)
    second = _discover(
        session, net, [company], apply=True, tavily=True, budget=TavilyCreditBudget(limit=10)
    )

    assert net.tavily_calls == 1
    assert first.tavily_queries == 1 and second.tavily_queries == 0
    assert second.skipped_recent_attempt == 1 and second.companies_considered == 0
    assert len(net.requests) == requests_after_first
    session.refresh(company)
    assert company.board_discovery_attempted_at is not None
    assert company.board_discovery_used_tavily is True


@_requires_database
def test_probe_only_attempt_does_not_block_a_later_tavily_run_and_window_expires(
    session: Session,
) -> None:
    company = _company(session, "Ghost Inc")
    net = Net(tavily=lambda _b: _tavily_results())

    _discover(session, net, [company], apply=True)  # probes only
    assert net.tavily_calls == 0
    _discover(session, net, [company], apply=True, tavily=True, budget=TavilyCreditBudget(limit=10))
    assert net.tavily_calls == 1
    # Window disabled: tried again even though the paid search already ran.
    _discover(
        session,
        net,
        [company],
        apply=True,
        tavily=True,
        budget=TavilyCreditBudget(limit=10),
        retry_days=0,
    )
    assert net.tavily_calls == 2


@_requires_database
def test_dry_run_stamps_nothing(session: Session) -> None:
    company = _company(session, "Ghost Inc")

    _discover(session, Net(), [company], apply=False)

    session.refresh(company)
    assert company.board_discovery_attempted_at is None


# --- Tavily budget and failures ------------------------------------------------------------


class _Boom:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, **_kwargs: Any) -> Any:
        self.calls += 1
        raise RuntimeError("provider down")

    async def aclose(self) -> None:
        return None


@_requires_database
def test_failing_tavily_is_charged_and_stops_after_three_consecutive_errors(
    session: Session,
) -> None:
    companies = [_company(session, f"Miss {n}") for n in range(5)]
    boom = _Boom()
    budget = TavilyCreditBudget(limit=10)

    report = _discover(session, Net(), companies, apply=True, tavily_client=boom, budget=budget)

    assert boom.calls == 3
    assert budget.spent == 3 and report.tavily_credits_spent == 3
    assert report.tavily_disabled_after_errors is True
    assert [o.outcome for o in report.outcomes] == [
        "tavily_error",
        "tavily_error",
        "tavily_error",
        "no_match_tavily_disabled",
        "no_match_tavily_disabled",
    ]


@_requires_database
def test_failing_calls_cannot_exceed_the_budget(session: Session) -> None:
    companies = [_company(session, f"Miss {n}") for n in range(3)]
    boom = _Boom()
    budget = TavilyCreditBudget(limit=2)

    report = _discover(session, Net(), companies, apply=True, tavily_client=boom, budget=budget)

    assert boom.calls == 2 and budget.spent == 2
    assert report.tavily_budget_stopped is True


@_requires_database
def test_max_credits_zero_makes_no_tavily_call(session: Session) -> None:
    company = _company(session, "Ghost Inc")
    net = Net(tavily=lambda _b: _tavily_results())

    report = _discover(
        session, net, [company], apply=True, tavily=True, budget=TavilyCreditBudget(limit=0)
    )

    assert net.tavily_calls == 0
    assert report.tavily_budget_stopped is True


# --- CLI ----------------------------------------------------------------------------------


def test_cli_use_tavily_requires_apply() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["--use-tavily"])
    assert exit_info.value.code == 2
    with pytest.raises(SystemExit):
        cli.parse_args(["--apply", "--use-tavily", "--max-credits", "-1"])
    assert cli.parse_args(["--apply", "--use-tavily"]).use_tavily is True


def test_default_cli_is_a_dry_run_that_builds_no_tavily_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args = cli.parse_args([])
    assert (args.apply, args.use_tavily) == (False, False)
    seen: dict[str, Any] = {}

    def forbidden(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("no Tavily client may be built without --use-tavily")

    async def fake_discover(_session: Any, **kwargs: Any) -> BoardDiscoveryReport:
        seen.update(kwargs)
        return BoardDiscoveryReport()

    monkeypatch.setattr(cli, "TavilyClient", forbidden)
    monkeypatch.setattr(cli, "discover_boards", fake_discover)
    monkeypatch.setattr(cli, "AcquisitionService", lambda *_a, **_k: object())

    _run(
        cli.run(
            None,  # type: ignore[arg-type]
            apply=args.apply,
            limit=args.limit,
            use_tavily=args.use_tavily,
            max_credits=args.max_credits,
            retry_days=args.retry_days,
        )
    )

    assert seen["apply"] is False
    assert seen["tavily"] is None and seen["budget"] is None


# --- a paid hit that does not become a proposal is not paid for again ----------------------


def _tavily_zeta_net() -> Net:
    return Net(
        boards={"/v0/postings/r55b6zeta-labs": [{"id": "a"}]},
        tavily=lambda _body: _tavily_results("https://jobs.lever.co/r55b6zeta-labs/abc"),
    )


def _discover_with(
    session: Session, net: Net, company: Company, service: AcquisitionService
) -> BoardDiscoveryReport:
    async def scenario() -> BoardDiscoveryReport:
        async with net.http() as http:
            return await discover_boards(
                session,
                service=service,
                client=http,
                resolve_ips=_resolve,
                apply=True,
                companies=[company],
                tavily=net.tavily_client(),
                budget=TavilyCreditBudget(limit=10),
                min_interval_seconds=0,
                sleeper=_no_sleep,
            )

    return _run(scenario())


@_requires_database
def test_tavily_hit_on_an_already_known_board_is_stamped_and_not_searched_again(
    session: Session,
) -> None:
    owner = _company(session, "Owner Co")
    company = _company(session, "Zeta Labs")
    service = _service(session)
    service.create_source(
        source_type="lever",
        name="Proposed owner lever",
        configuration={"company_name": owner.canonical_name, "site_identifier": "r55b6zeta-labs"},
        evidence_status="ats_identified",
    )
    net = _tavily_zeta_net()

    first = _discover_with(session, net, company, service)
    second = _discover_with(session, net, company, service)

    assert [o.outcome for o in first.outcomes] == ["board_already_known"]
    assert net.tavily_calls == 1
    assert second.skipped_recent_attempt == 1 and second.tavily_queries == 0
    session.refresh(company)
    assert company.board_discovery_used_tavily is True


@_requires_database
def test_tavily_hit_rejected_on_apply_is_stamped_and_not_searched_again(
    session: Session,
) -> None:
    company = _company(session, "Zeta Labs")
    service = _service(session)

    def reject(**_kwargs: Any) -> Any:
        raise AcquisitionError(AcquisitionErrorCode.INVALID_CONFIGURATION, "boom")

    service.create_source = reject  # type: ignore[method-assign]
    net = _tavily_zeta_net()

    first = _discover_with(session, net, company, service)
    second = _discover_with(session, net, company, service)

    assert first.outcomes[0].outcome.startswith("rejected")
    assert net.tavily_calls == 1
    assert second.skipped_recent_attempt == 1
    assert _proposals(session) == []
    session.refresh(company)
    assert company.board_discovery_used_tavily is True
