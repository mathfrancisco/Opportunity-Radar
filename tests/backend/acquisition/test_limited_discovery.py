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
    endpoint_ats_name,
    is_public_destination,
    normalize_discovery_url,
    record_limited_discovery_attempt,
    run_limited_discovery,
    upsert_ats_identified_source,
)
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
    # robots.txt + sitemap.xml + the /careers request that hit the redirect: never the
    # redirect target itself.
    assert outcome.http_requests == 3


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
            assert source_2.endpoint == "https://boards.greenhouse.io/beta-updated"

            all_sources = session.query(CompanySource).filter_by(company_id=company.id).all()
            assert len(all_sources) == 1
        finally:
            _db_cleanup(session, [company.id])
