from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.limited_discovery import (
    DiscoveredEndpoint,
    DiscoveryLimits,
    DiscoveryStopReason,
    canonical_board_url,
    direct_slug_candidates,
    endpoint_ats_name,
    is_public_destination,
    normalize_discovery_url,
    probe_direct_ats,
    record_limited_discovery_attempt,
    run_limited_discovery,
    upsert_ats_identified_source,
)
from opportunity_radar.companies import discovery
from opportunity_radar.companies.discovery import robots_allows
from opportunity_radar.companies.models import Company, CompanySource, DiscoveryAttemptModel
from opportunity_radar.platform.database import create_database_engine
from tests.e2e.fake_discovery_site import (
    HOST,
    ORIGIN,
    PRIVATE_IP,
    PUBLIC_IP,
    ats_behind_link_site,
    dynamic_shell_site,
    fake_resolve_ips,
    identifying_query_site,
    redirect_to_private_ip_site,
    robots_disallow_site,
    robots_unavailable_site,
    sitemap_loop_site,
    sitemap_with_noise_site,
    unsafe_sitemap_site,
)

ALLOWLIST = frozenset({".example.test"})


def _run(handler, *, resolve_ips=None, limits: DiscoveryLimits | None = None):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        return asyncio.run(
            run_limited_discovery(
                f"{ORIGIN}/careers",
                company_id=uuid4(),
                limits=limits or DiscoveryLimits(),
                allowlist=ALLOWLIST,
                client=client,
                resolve_ips=resolve_ips or fake_resolve_ips(),
            )
        )
    finally:
        asyncio.run(client.aclose())


def test_sitemap_loop_stops_within_budget() -> None:
    limits = DiscoveryLimits(max_sitemap_files=3, max_html_responses=5)
    outcome = _run(sitemap_loop_site(), limits=limits)

    assert outcome.stop_reason in {
        DiscoveryStopReason.EXHAUSTED,
        DiscoveryStopReason.LIMIT_REACHED,
    }
    # robots.txt + at most one distinct sitemap URL (visited-dedup) + careers + jobs.
    assert outcome.http_requests <= 4
    assert outcome.next_attempt_at is not None


def test_redirect_to_private_ip_is_refused() -> None:
    resolve_ips = fake_resolve_ips({HOST: PUBLIC_IP, "internal.careers.example.test": PRIVATE_IP})
    outcome = _run(redirect_to_private_ip_site(), resolve_ips=resolve_ips)

    assert outcome.stop_reason == DiscoveryStopReason.POLICY
    assert outcome.endpoints == ()
    # robots.txt + the /careers request that hit the redirect: never the redirect target
    # itself, and never the sitemap either (shallow pass first, F20-36 follow-up) — the
    # policy stop during that shallow pass short-circuits before the sitemap is ever
    # fetched.
    assert outcome.http_requests == 2


def test_is_public_destination_refuses_private_and_loopback_ips() -> None:
    assert is_public_destination("10.0.0.5", ("10.0.0.5",)) is False
    assert is_public_destination("careers.example.test", ("127.0.0.1",)) is False
    assert is_public_destination("careers.example.test", ("169.254.1.1",)) is False
    assert is_public_destination("careers.example.test", ()) is False
    assert is_public_destination("careers.example.test", (PUBLIC_IP,)) is True


def test_url_with_identifying_query_is_not_deduplicated_away() -> None:
    first = normalize_discovery_url("https://careers.example.test/careers/job?id=1")
    second = normalize_discovery_url("https://careers.example.test/careers/job?id=2")
    same_again = normalize_discovery_url("https://CAREERS.example.test:443/careers/job?id=1#frag")

    assert first != second
    assert first == same_again


def test_identifying_query_urls_are_both_examined() -> None:
    outcome = _run(identifying_query_site())
    # Sitemap lists two job URLs differing only by query; both must be counted, proving
    # neither collapsed into the other.
    assert outcome.urls_examined >= 3  # sitemap + careers + at least one job page


def test_robots_unavailable_suspends_navigation() -> None:
    outcome = _run(robots_unavailable_site())

    assert outcome.stop_reason == DiscoveryStopReason.POLICY
    assert outcome.endpoints == ()
    assert outcome.http_requests == 1  # only the failed robots.txt request
    assert outcome.next_attempt_at is not None


# One table of robots.txt fetch outcomes, pinned to both readers (RFC 9309, as in
# `companies.discovery.robots_allows`): the same answer means the same decision.
_ROBOTS_OUTCOMES = [
    ("200 with rules", lambda: httpx.Response(200, text="User-agent: *\nDisallow: /x\n"), True),
    ("404", lambda: httpx.Response(404), True),
    ("410", lambda: httpx.Response(410), True),
    ("400", lambda: httpx.Response(400), True),
    ("401", lambda: httpx.Response(401), False),
    ("403", lambda: httpx.Response(403), False),
    ("500", lambda: httpx.Response(500), False),
    ("timeout", lambda: httpx.ReadTimeout("slow"), False),
]


@pytest.mark.parametrize(("name", "make", "allowed"), _ROBOTS_OUTCOMES)
def test_robots_fetch_outcomes_match_the_company_discovery_reader(
    name, make, allowed, monkeypatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            outcome = make()
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return httpx.Response(
            200, text="<html>Careers</html>", headers={"content-type": "text/html"}
        )

    outcome = _run(handler)
    # Allowed means the crawl went past robots.txt; a stop leaves it as the only request.
    assert (outcome.http_requests > 1) is allowed, name
    assert (outcome.stop_reason != DiscoveryStopReason.POLICY) is allowed, name

    def fake_fetch(robots_url: str, user_agent: str) -> httpx.Response:
        response = make()
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(discovery, "_fetch_robots", fake_fetch)
    assert robots_allows(f"{ORIGIN}/careers") is allowed, name


def test_robots_disallow_refuses_seed() -> None:
    outcome = _run(robots_disallow_site())

    assert outcome.stop_reason == DiscoveryStopReason.POLICY
    assert outcome.endpoints == ()


def test_unsafe_sitemap_xml_stops_as_policy() -> None:
    outcome = _run(unsafe_sitemap_site())

    assert outcome.stop_reason == DiscoveryStopReason.POLICY
    assert outcome.endpoints == ()


def test_dynamic_site_is_flagged_not_treated_as_success_or_failure() -> None:
    outcome = _run(dynamic_shell_site())

    assert outcome.stop_reason == DiscoveryStopReason.DYNAMIC_SITE
    assert outcome.endpoints == ()


def test_ats_found_one_click_deeper_than_f20_27_checks() -> None:
    outcome = _run(ats_behind_link_site())

    assert outcome.stop_reason == DiscoveryStopReason.EXHAUSTED
    assert len(outcome.endpoints) == 1
    assert endpoint_ats_name(outcome.endpoints[0]) == "greenhouse"


def test_sitemap_keyword_filter_excludes_unrelated_urls() -> None:
    """`sitemap_with_noise_site` blows up if `/blog/launch` is ever fetched; reaching the
    real Greenhouse hit at `/careers/team` without that error is the whole assertion."""
    outcome = _run(sitemap_with_noise_site())

    assert outcome.stop_reason == DiscoveryStopReason.EXHAUSTED
    assert len(outcome.endpoints) == 1
    assert endpoint_ats_name(outcome.endpoints[0]) == "greenhouse"


def test_direct_slug_candidates_shapes_name_and_domain() -> None:
    candidates = direct_slug_candidates("Acme Corp", "https://www.acme-corp.example/careers")

    # Compact and hyphenated forms of the name; the domain label ("acme-corp") coincides
    # with the hyphenated form here, so it is not repeated.
    assert candidates == ("acmecorp", "acme-corp")


def test_direct_slug_candidates_deduplicates() -> None:
    # Compact name, hyphenated name and domain label all collapse to the same slug: tried
    # once, not three times.
    candidates = direct_slug_candidates("Acme", "https://acme.example/careers")

    assert candidates == ("acme",)


def _direct_probe_handler(routes: dict[str, dict | list]):
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.host}{request.url.path}"
        for path, payload in routes.items():
            if key.endswith(path):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})

    return handler


def test_probe_direct_ats_finds_a_populated_ashby_board() -> None:
    handler = _direct_probe_handler(
        {"api.ashbyhq.com/posting-api/job-board/acme": {"jobs": [{"id": "1"}]}}
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        endpoint, requests_made = asyncio.run(
            probe_direct_ats(
                uuid4(),
                "Acme",
                "https://acme.example/careers",
                client=client,
                resolve_ips=fake_resolve_ips({"api.ashbyhq.com": PUBLIC_IP}),
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert endpoint is not None
    assert endpoint_ats_name(endpoint) == "ashby"
    assert endpoint.method == "direct_slug"
    assert requests_made == 1  # first candidate, first ATS: no wasted requests


def test_probe_direct_ats_skips_empty_boards_and_stops_at_budget() -> None:
    # Every candidate answers 200 with an empty job list: a real, but unpopulated (or
    # wrong-slug) board must never be reported as a hit.
    def empty_boards(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobs": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(empty_boards))
    try:
        endpoint, requests_made = asyncio.run(
            probe_direct_ats(
                uuid4(),
                "Acme",
                "https://acme.example/careers",
                client=client,
                resolve_ips=fake_resolve_ips(
                    {
                        "api.ashbyhq.com": PUBLIC_IP,
                        "boards-api.greenhouse.io": PUBLIC_IP,
                        "api.lever.co": PUBLIC_IP,
                        "apply.workable.com": PUBLIC_IP,
                        "acme.teamtailor.com": PUBLIC_IP,
                        "acmecorp.teamtailor.com": PUBLIC_IP,
                    }
                ),
                max_requests=3,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert endpoint is None
    assert requests_made == 3  # stopped at the budget, not the candidate/ATS product


def test_canonical_board_url_normalizes_greenhouse_hostname() -> None:
    canonical = canonical_board_url(
        "greenhouse", "https://boards.greenhouse.io/gitlab/jobs/12345?gh_src=abc"
    )

    assert canonical == "https://job-boards.greenhouse.io/gitlab"


def test_canonical_board_url_leaves_unknown_ats_untouched() -> None:
    url = "https://apply.workable.com/api/v1/widget/accounts/acme"
    assert canonical_board_url("workable", url) == url


def test_run_limited_discovery_skips_crawling_the_site_on_a_direct_slug_hit() -> None:
    """With `company_name` given, a direct-slug hit must never touch the company's own
    site at all: the fake site's handler raises if the crawler contacts it."""

    def never_crawl_the_site(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("direct-slug hit should have skipped crawling the site")

    def routed(request: httpx.Request) -> httpx.Response:
        if request.url.host == HOST:
            return never_crawl_the_site(request)
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(200, json={"jobs": [{"id": "1"}]})
        return httpx.Response(404, json={"error": "not found"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(routed))
    try:
        outcome = asyncio.run(
            run_limited_discovery(
                f"{ORIGIN}/careers",
                company_id=uuid4(),
                company_name="careers",  # matches HOST's domain label -> "careers" slug
                limits=DiscoveryLimits(),
                allowlist=ALLOWLIST,
                client=client,
                resolve_ips=fake_resolve_ips({"api.ashbyhq.com": PUBLIC_IP}),
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.stop_reason == DiscoveryStopReason.EXHAUSTED
    assert len(outcome.endpoints) == 1
    assert outcome.endpoints[0].method == "direct_slug"
    assert endpoint_ats_name(outcome.endpoints[0]) == "ashby"
    assert outcome.http_requests == 1


_requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _db_company(session: Session, *, marker: str) -> Company:
    company = Company(
        canonical_name=f"Discovery Co {marker}", normalized_name=f"discovery-co-{marker}"
    )
    session.add(company)
    session.flush()
    return company


def _db_cleanup(session: Session, company_ids: list) -> None:
    session.execute(delete(DiscoveryAttemptModel).where(DiscoveryAttemptModel.company_id.in_(company_ids)))
    session.execute(delete(CompanySource).where(CompanySource.company_id.in_(company_ids)))
    session.execute(delete(Company).where(Company.id.in_(company_ids)))
    session.commit()


@pytest.mark.integration
@_requires_database
def test_limit_or_error_does_not_mean_no_jobs() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _db_company(session, marker=marker)
        session.commit()
        try:
            for handler in (robots_unavailable_site(), unsafe_sitemap_site()):
                outcome = asyncio.run(
                    run_limited_discovery(
                        f"{ORIGIN}/careers",
                        company_id=company.id,
                        limits=DiscoveryLimits(),
                        allowlist=ALLOWLIST,
                        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                        resolve_ips=fake_resolve_ips(),
                    )
                )
                assert outcome.stop_reason == DiscoveryStopReason.POLICY
                record_limited_discovery_attempt(session, outcome, checked_url=f"{ORIGIN}/careers")

            sources = session.query(CompanySource).filter_by(company_id=company.id).all()
            assert sources == []  # a limit/error never writes a "no jobs" CompanySource
            attempts = (
                session.query(DiscoveryAttemptModel).filter_by(company_id=company.id).all()
            )
            assert len(attempts) == 2
            assert all(attempt.stop_reason == "POLICY" for attempt in attempts)
        finally:
            _db_cleanup(session, [company.id])


@pytest.mark.integration
@_requires_database
def test_existing_proposal_is_reused_with_discovery_history() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _db_company(session, marker=marker)
        session.commit()
        try:
            first = DiscoveredEndpoint(
                company_id=company.id,
                seed_url=f"{ORIGIN}/careers",
                discovered_url="https://boards.greenhouse.io/beta",
                method="html_link",
                fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
                evidence_excerpt="boards.greenhouse.io/beta",
                confidence_reason="ats_signature:greenhouse",
            )
            second = DiscoveredEndpoint(
                company_id=company.id,
                seed_url=f"{ORIGIN}/careers",
                discovered_url="https://boards.greenhouse.io/beta-updated",
                method="html_link",
                fetched_at=datetime(2026, 9, 27, tzinfo=UTC),
                evidence_excerpt="boards.greenhouse.io/beta-updated",
                confidence_reason="ats_signature:greenhouse",
            )

            source_1 = upsert_ats_identified_source(session, first)
            source_2 = upsert_ats_identified_source(session, second)

            assert source_1.id == source_2.id
            assert "2026-09-01" in source_2.evidence_note
            assert "2026-09-27" in source_2.evidence_note
            # Canonicalized to the current Greenhouse hostname (F20-36 follow-up): the
            # historical `boards.greenhouse.io` and current `job-boards.greenhouse.io`
            # serve the same board, so `endpoint` always ends up on the latter.
            assert source_2.endpoint == "https://job-boards.greenhouse.io/beta-updated"

            all_sources = session.query(CompanySource).filter_by(company_id=company.id).all()
            assert len(all_sources) == 1
        finally:
            _db_cleanup(session, [company.id])


@pytest.mark.integration
@_requires_database
def test_upsert_recovers_from_a_concurrent_duplicate_insert() -> None:
    """Regression for the GitLab case: two discovery passes for the same company+ATS
    (now genuinely concurrent across hosts, F20-36 follow-up) can both see "no existing
    row" before either commits. The second insert then hits
    `uq_company_source_company_type_endpoint` instead of finding the row its sibling just
    created — `upsert_ats_identified_source` must recover by updating, not raise."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _db_company(session, marker=marker)
        session.commit()
        try:
            # Simulates the sibling task's insert having already landed between this
            # call's own (stale) "no existing row" read and its attempted insert.
            already_inserted = CompanySource(
                company_id=company.id,
                source_type="greenhouse",
                endpoint="https://job-boards.greenhouse.io/gitlab",
                verification_method="discovery",
                verification_status="ats_identified",
                evidence_note="prior discovery pass",
                last_verified_at=datetime(2026, 9, 28, 17, 5, tzinfo=UTC),
            )
            session.add(already_inserted)
            session.commit()

            real_scalar = session.scalar
            calls = {"n": 0}

            def stale_scalar(*args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    return None  # the race window: this call's own lookup missed it
                return real_scalar(*args, **kwargs)

            session.scalar = stale_scalar  # type: ignore[method-assign]
            try:
                endpoint = DiscoveredEndpoint(
                    company_id=company.id,
                    seed_url=f"{ORIGIN}/careers",
                    discovered_url="https://job-boards.greenhouse.io/gitlab/",
                    method="sitemap",
                    fetched_at=datetime(2026, 9, 28, 17, 6, tzinfo=UTC),
                    evidence_excerpt="job-boards.greenhouse.io/gitlab",
                    confidence_reason="ats_signature:greenhouse",
                )
                result = upsert_ats_identified_source(session, endpoint)
            finally:
                session.scalar = real_scalar  # type: ignore[method-assign]

            assert result.id == already_inserted.id
            assert result.endpoint == "https://job-boards.greenhouse.io/gitlab"
            assert "prior discovery pass" in result.evidence_note

            all_sources = session.query(CompanySource).filter_by(company_id=company.id).all()
            assert len(all_sources) == 1  # never a duplicate row
        finally:
            _db_cleanup(session, [company.id])
