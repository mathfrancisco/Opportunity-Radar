"""No real network anywhere here: every `httpx.AsyncClient` is a `MockTransport`, and
`resolve_ips` is always the injectable fake from `tests/e2e/fake_discovery_site.py` (the
same fake `run_limited_discovery`'s own tests use), never real DNS."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company, CompanySource, DiscoveryAttemptModel
from opportunity_radar.platform.database import create_database_engine
from scripts import discover_ats
from scripts.discover_ats import _confirmed_careers_url, _discover_company, run_discovery
from tests.e2e.fake_discovery_site import PUBLIC_IP, fake_resolve_ips

CAREERS_URL = "https://careers.example.test/careers"


def _company(*, careers_url: str | None = CAREERS_URL) -> Company:
    sources = []
    if careers_url is not None:
        sources.append(
            CompanySource(
                source_type="careers",
                endpoint=careers_url,
                verification_method="manual",
                verification_status="careers_confirmed",
            )
        )
    return Company(
        id=uuid4(),
        canonical_name="careers",  # matches HOST's domain label -> "careers" slug
        normalized_name="careers",
        sources=sources,
    )


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_confirmed_careers_url_returns_the_endpoint_when_confirmed() -> None:
    assert _confirmed_careers_url(_company()) == CAREERS_URL


def test_confirmed_careers_url_returns_none_without_a_confirmed_careers_source() -> None:
    assert _confirmed_careers_url(_company(careers_url=None)) is None


def test_discover_company_skips_the_careers_page_on_a_direct_slug_hit(monkeypatch) -> None:
    def never_crawl_the_site(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("a direct-slug hit must skip the careers-page request")

    def routed(request: httpx.Request) -> httpx.Response:
        if request.url.host == "careers.example.test":
            return never_crawl_the_site(request)
        if request.url.host == "api.ashbyhq.com":
            return httpx.Response(200, json={"jobs": [{"id": "1"}]})
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setattr(
        discover_ats, "_resolve_ips", fake_resolve_ips({"api.ashbyhq.com": PUBLIC_IP})
    )
    company = _company()
    client = _mock_client(routed)
    try:
        outcome = asyncio.run(
            _discover_company(
                company, CAREERS_URL, client=client, robots_checker=lambda _url: True
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ats_found == "ashby"
    assert outcome.final_url == "https://api.ashbyhq.com/posting-api/job-board/careers"


def test_discover_company_falls_back_to_the_careers_page_when_no_direct_hit(monkeypatch) -> None:
    def routed(request: httpx.Request) -> httpx.Response:
        if request.url.host == "careers.example.test":
            return httpx.Response(
                200,
                content=(
                    b'<html><body><iframe src="https://boards.greenhouse.io/acme">'
                    b"</iframe></body></html>"
                ),
            )
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setattr(discover_ats, "_resolve_ips", fake_resolve_ips({}))
    company = _company()
    client = _mock_client(routed)
    try:
        outcome = asyncio.run(
            _discover_company(
                company, CAREERS_URL, client=client, robots_checker=lambda _url: True
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ats_found == "greenhouse"
    assert outcome.checked_url == CAREERS_URL


_requires_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _db_company(session: Session, *, marker: str, careers_url: str) -> Company:
    company = Company(canonical_name=f"Co {marker}", normalized_name=f"co-{marker}")
    session.add(company)
    session.flush()
    session.add(
        CompanySource(
            company_id=company.id,
            source_type="careers",
            endpoint=careers_url,
            verification_method="manual",
            verification_status="careers_confirmed",
        )
    )
    session.commit()
    session.refresh(company)
    return company


def _db_cleanup(session: Session, company_ids: list) -> None:
    session.execute(delete(DiscoveryAttemptModel).where(DiscoveryAttemptModel.company_id.in_(company_ids)))
    session.execute(delete(CompanySource).where(CompanySource.company_id.in_(company_ids)))
    session.execute(delete(Company).where(Company.id.in_(company_ids)))
    session.commit()


@pytest.mark.integration
@_requires_database
def test_run_discovery_processes_companies_concurrently_and_counts_errors(monkeypatch) -> None:
    """Three companies on three different hosts, run concurrently: one gets a direct-
    slug ashby hit (no careers-page request), one falls back to a greenhouse signature
    on its careers page, and one has its careers-page request raise — proving that
    company's failure is counted, not fatal to the batch."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        hit = _db_company(
            session, marker=f"hit-{marker}", careers_url="https://hit.example.test/careers"
        )
        fallback = _db_company(
            session,
            marker=f"fallback-{marker}",
            careers_url="https://fallback.example.test/careers",
        )
        failing = _db_company(
            session, marker=f"failing-{marker}", careers_url="https://failing.example.test/careers"
        )
        company_ids = [hit.id, fallback.id, failing.id]

        def routed(request: httpx.Request) -> httpx.Response:
            host = request.url.host
            if host == "api.ashbyhq.com" and "hit" in str(request.url):
                return httpx.Response(200, json={"jobs": [{"id": "1"}]})
            if host == "fallback.example.test":
                return httpx.Response(
                    200,
                    content=(
                        b'<html><body><iframe src="https://boards.greenhouse.io/acme">'
                        b"</iframe></body></html>"
                    ),
                )
            if host == "failing.example.test":
                raise httpx.ConnectError("simulated outage")
            return httpx.Response(404, json={"error": "not found"})

        async def fake_resolve(host: str) -> tuple[str, ...]:
            mapping = {
                "api.ashbyhq.com": PUBLIC_IP,
                "hit.example.test": PUBLIC_IP,
                "fallback.example.test": PUBLIC_IP,
                "failing.example.test": PUBLIC_IP,
            }
            ip = mapping.get(host)
            return (ip,) if ip else ()

        real_async_client = httpx.AsyncClient
        monkeypatch.setattr(discover_ats, "_resolve_ips", fake_resolve)
        # `discover_one`'s fallback path checks robots via `robots_allows`, a real
        # `urllib.robotparser` lookup — faked here so the DB-integration test never
        # opens a real socket either.
        monkeypatch.setattr(discover_ats, "robots_allows", lambda url, user_agent=None: True)
        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda *a, **k: real_async_client(transport=httpx.MockTransport(routed)),
        )
        try:
            report = asyncio.run(run_discovery(session, concurrency=8, min_interval_seconds=0.0))

            assert report["checked"] == 2  # hit + fallback; `failing` counted as an error
            assert report["errors"] == 1
            assert report["by_ats"] == {"ashby": 1, "greenhouse": 1}

            attempts = (
                session.query(DiscoveryAttemptModel)
                .filter(DiscoveryAttemptModel.company_id.in_(company_ids))
                .all()
            )
            assert len(attempts) == 2  # `failing` never reached record_discovery_attempt
        finally:
            _db_cleanup(session, company_ids)
