"""F20-27: the ATS-signature detector, eligibility, robots.txt, and the recorded evidence.

Discovery makes one request per eligible company and never a `SourceRun`/`RawItem`
(SPEC 43); these tests use `httpx.MockTransport` and a fake `robots_checker`, never a real
network call.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.companies.discovery import (
    ATS_SIGNATURES,
    detect_ats,
    discover_one,
    eligible_companies,
    record_ats_identified,
    record_discovery_attempt,
)
from opportunity_radar.companies.models import Company, CompanySource, DiscoveryAttemptModel
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)

_SAMPLE_HTML = {
    "ashby": '<a href="https://jobs.ashbyhq.com/acme">Careers</a>',
    "greenhouse": '<iframe src="https://boards.greenhouse.io/acme"></iframe>',
    "lever": '<a href="https://jobs.lever.co/acme">Jobs</a>',
    "gupy": '<script src="https://acme.gupy.io/widget.js"></script>',
    "teamtailor": '<iframe src="https://acme.teamtailor.com/jobs"></iframe>',
    "workable": '<a href="https://apply.workable.com/acme/">Apply</a>',
    "workday": '<a href="https://acme.myworkdayjobs.com/en-US/careers">Jobs</a>',
    "factorial": '<script src="https://acme.factorialhr.com/jobs.js"></script>',
}


@pytest.mark.parametrize("ats", sorted(ATS_SIGNATURES))
def test_detect_ats_matches_each_signature(ats: str) -> None:
    html = f"<html><body>{_SAMPLE_HTML[ats]}</body></html>"
    assert detect_ats(html) == ats


def test_detect_ats_returns_none_without_signature() -> None:
    html = "<html><body><a href='https://acme.example.com/careers'>Jobs</a></body></html>"
    assert detect_ats(html) is None


def _company(session: Session, *, marker: str) -> Company:
    company = Company(
        canonical_name=f"Discovery Co {marker}",
        normalized_name=f"discovery-co-{marker}",
    )
    session.add(company)
    session.flush()
    return company


def _careers_source(session: Session, company: Company, *, marker: str) -> CompanySource:
    source = CompanySource(
        company_id=company.id,
        source_type="careers",
        endpoint=f"https://acme-{marker}.example.com/careers",
        verification_status="careers_confirmed",
    )
    session.add(source)
    session.commit()
    return source


def _cleanup(session: Session, company_ids: list) -> None:
    session.execute(
        delete(DiscoveryAttemptModel).where(
            DiscoveryAttemptModel.company_id.in_(company_ids)
        )
    )
    session.execute(
        delete(CompanySource).where(CompanySource.company_id.in_(company_ids))
    )
    session.execute(delete(Company).where(Company.id.in_(company_ids)))
    session.commit()


def test_eligible_companies_excludes_known_ats() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        without_ats = _company(session, marker=f"no-ats-{marker}")
        _careers_source(session, without_ats, marker=f"no-ats-{marker}")
        with_ats = _company(session, marker=f"has-ats-{marker}")
        _careers_source(session, with_ats, marker=f"has-ats-{marker}")
        session.add(
            CompanySource(
                company_id=with_ats.id,
                source_type="greenhouse",
                endpoint=f"https://boards.greenhouse.io/has-ats-{marker}",
                verification_status="ats_identified",
            )
        )
        session.commit()
        try:
            eligible_ids = {company.id for company in eligible_companies(session)}
            assert without_ats.id in eligible_ids
            assert with_ats.id not in eligible_ids
        finally:
            _cleanup(session, [without_ats.id, with_ats.id])


def test_eligible_companies_excludes_recent_attempt() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _company(session, marker=marker)
        _careers_source(session, company, marker=marker)
        session.add(
            DiscoveryAttemptModel(
                company_id=company.id,
                checked_url="https://acme.example.com/careers",
                http_status=200,
                ats_found=None,
                attempted_at=NOW - timedelta(days=1),
            )
        )
        session.commit()
        try:
            eligible_ids = {c.id for c in eligible_companies(session, now=NOW)}
            assert company.id not in eligible_ids
        finally:
            _cleanup(session, [company.id])


def test_attempt_not_repeated_before_interval() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _company(session, marker=marker)
        _careers_source(session, company, marker=marker)
        session.commit()
        try:
            # No attempt yet: eligible.
            assert company.id in {c.id for c in eligible_companies(session, now=NOW)}

            session.add(
                DiscoveryAttemptModel(
                    company_id=company.id,
                    checked_url="https://acme.example.com/careers",
                    http_status=200,
                    ats_found=None,
                    attempted_at=NOW - timedelta(days=29),
                )
            )
            session.commit()
            # Inside the 30-day interval: not eligible again.
            assert company.id not in {c.id for c in eligible_companies(session, now=NOW)}

            # Outside the interval: eligible again.
            future = NOW + timedelta(days=2)
            assert company.id in {c.id for c in eligible_companies(session, now=future)}
        finally:
            _cleanup(session, [company.id])


def test_discover_one_respects_robots_txt() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _company(session, marker=marker)
        _careers_source(session, company, marker=marker)
        session.commit()
        try:

            def handler(request: httpx.Request) -> httpx.Response:
                raise AssertionError("robots.txt disallows this URL; no GET expected")

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                outcome = asyncio.run(
                    discover_one(
                        company, client=client, robots_checker=lambda _url: False
                    )
                )
            finally:
                asyncio.run(client.aclose())

            assert outcome.http_status is None
            assert outcome.ats_found is None
        finally:
            _cleanup(session, [company.id])


def test_discover_one_records_final_url_on_redirect() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _company(session, marker=marker)
        source = _careers_source(session, company, marker=marker)
        session.commit()
        final_url = f"https://ats.example.com/{marker}"

        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == source.endpoint:
                return httpx.Response(302, headers={"Location": final_url})
            return httpx.Response(
                200,
                html=f'<a href="https://jobs.ashbyhq.com/{marker}">Careers</a>',
            )

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            outcome = asyncio.run(
                discover_one(company, client=client, robots_checker=lambda _url: True)
            )
        finally:
            asyncio.run(client.aclose())

        try:
            assert outcome.http_status == 200
            assert outcome.final_url == final_url
            assert outcome.ats_found == "ashby"
        finally:
            _cleanup(session, [company.id])


def test_record_ats_identified_creates_company_source_with_discovery_method() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        company = _company(session, marker=marker)
        _careers_source(session, company, marker=marker)
        session.commit()
        try:
            outcome_html = _SAMPLE_HTML["lever"]

            def handler(request: httpx.Request) -> httpx.Response:
                return httpx.Response(200, html=f"<html><body>{outcome_html}</body></html>")

            client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            try:
                outcome = asyncio.run(
                    discover_one(
                        company, client=client, robots_checker=lambda _url: True
                    )
                )
            finally:
                asyncio.run(client.aclose())

            record_discovery_attempt(session, outcome)
            created = record_ats_identified(session, outcome)

            assert created is not None
            assert created.source_type == "lever"
            assert created.verification_method == "discovery"
            assert created.verification_status == "ats_identified"
            assert created.evidence_note is not None

            attempts = session.query(DiscoveryAttemptModel).filter(
                DiscoveryAttemptModel.company_id == company.id
            ).all()
            assert len(attempts) == 1
            assert attempts[0].ats_found == "lever"
        finally:
            _cleanup(session, [company.id])
