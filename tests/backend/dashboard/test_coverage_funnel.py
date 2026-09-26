"""Canonical-company coverage and acquisition yield metrics (F20-35)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company, CompanyAlias, CompanySource
from opportunity_radar.dashboard.queries import (
    company_coverage_funnel,
    useful_yield_metrics,
)
from opportunity_radar.opportunities.models import (
    OpportunityModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
)
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.presentation.http.dependencies import get_session

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

# A controlled, isolated clock keeps persisted CI fixtures outside this metric window.
NOW = datetime(2040, 1, 1, tzinfo=UTC) + timedelta(days=uuid4().int % 100_000)


@pytest.fixture
def session():
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as db:
        yield db
        db.rollback()
    engine.dispose()


def _company(session: Session, tag: str) -> Company:
    company = Company(
        canonical_name=f"F20-35 {tag} {uuid4().hex[:8]}",
        normalized_name=f"f20-35-{tag}-{uuid4().hex}",
    )
    session.add(company)
    session.flush()
    return company


def _company_source(
    session: Session, company: Company, tag: str
) -> CompanySource:
    source = CompanySource(
        company_id=company.id,
        source_type="greenhouse",
        endpoint=f"https://boards.greenhouse.io/f20-35-{tag}-{uuid4().hex[:8]}",
    )
    session.add(source)
    session.flush()
    return source


def _source_definition(
    session: Session,
    company_source: CompanySource,
    tag: str,
    *,
    enabled: bool = False,
    homologated: bool = False,
) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        source_type="greenhouse",
        name=f"F20-35 {tag} {uuid4().hex[:8]}",
        enabled=enabled,
        schedule="0 0 * * *",
        company_source_id=company_source.id,
        evidence_status="confirmed" if homologated else "unverified",
        reviewed_at=NOW if homologated else None,
        terms_reviewed=homologated,
        collector_local_tested=homologated,
    )
    session.add(source)
    session.flush()
    return source


def _run(
    session: Session,
    source: SourceDefinitionModel,
    *,
    status: str = "SUCCEEDED",
    complete: bool = False,
    started_at: datetime = NOW - timedelta(hours=1),
    http_requests: int = 0,
) -> SourceRunModel:
    run = SourceRunModel(
        source_definition_id=source.id,
        status=status,
        complete=complete,
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
        http_requests=http_requests,
    )
    session.add(run)
    session.flush()
    return run


def _opportunity(
    session: Session,
    company: Company,
    sources: tuple[SourceDefinitionModel, ...],
    *,
    tag: str,
    created_at: datetime = NOW - timedelta(hours=1),
    published_at: datetime | None = None,
    first_seen_at: tuple[datetime, ...] | None = None,
    source_published_at: tuple[datetime | None, ...] | None = None,
) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title=f"F20-35 role {tag}",
        normalized_title=f"f20-35 role {tag}",
        canonical_company_id=company.id,
        company_name=company.canonical_name,
        work_mode="REMOTE",
        seniority="UNKNOWN",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        created_at=created_at,
        published_at=published_at,
        version=1,
    )
    session.add(opportunity)
    session.flush()
    for index, source in enumerate(sources):
        run = _run(session, source)
        raw_item = RawItemModel(
            source_run_id=run.id,
            source_definition_id=source.id,
            identity_key=f"f20-35:{tag}:{index}",
            payload_hash=uuid4().hex + uuid4().hex,
        )
        session.add(raw_item)
        session.flush()
        occurrence = SourceOccurrenceModel(
            opportunity_id=opportunity.id,
            raw_item_id=raw_item.id,
            source_definition_id=source.id,
            first_seen_at=(first_seen_at or (NOW - timedelta(minutes=5),) * len(sources))[index],
            last_seen_at=NOW,
            source_published_at=(source_published_at or (None,) * len(sources))[index],
        )
        session.add(occurrence)
    session.flush()
    return opportunity


def _seed_funnel(session: Session) -> None:
    _company(session, "catalog-only")

    discovered = _company(session, "discovered")
    _source_definition(session, _company_source(session, discovered, "unverified"), "unverified")

    homologated = _company(session, "homologated-disabled")
    _source_definition(
        session,
        _company_source(session, homologated, "homologated-disabled"),
        "homologated-disabled",
        homologated=True,
    )

    failed = _company(session, "enabled-failed")
    failed_source = _source_definition(
        session,
        _company_source(session, failed, "enabled-failed"),
        "enabled-failed",
        enabled=True,
        homologated=True,
    )
    _run(
        session,
        failed_source,
        status="SUCCEEDED",
        complete=True,
        started_at=NOW - timedelta(hours=2),
    )
    _run(session, failed_source, status="FAILED", started_at=NOW - timedelta(hours=1))

    collected = _company(session, "collected-two-sources")
    session.add(
        CompanyAlias(
            company_id=collected.id,
            alias=f"F20-35 alias {uuid4().hex[:8]}",
            normalized_alias=f"f20-35-alias-{uuid4().hex}",
        )
    )
    for suffix, recent in (("a", True), ("b", False)):
        source = _source_definition(
            session,
            _company_source(session, collected, f"collected-{suffix}"),
            f"collected-{suffix}",
            enabled=True,
            homologated=True,
        )
        _run(
            session,
            source,
            status="SUCCEEDED",
            complete=recent,
            started_at=NOW - timedelta(hours=1),
            http_requests=4,
        )


def test_funnel_counts_each_stage_once_per_canonical_company(session: Session) -> None:
    baseline = company_coverage_funnel(session, window_days=7, now=NOW)
    _seed_funnel(session)

    report = company_coverage_funnel(session, window_days=7, now=NOW)

    assert report.canonical_companies_total - baseline.canonical_companies_total == 5
    assert [item.stage for item in report.stages] == [
        "cataloged",
        "endpoint_discovered",
        "homologated",
        "enabled",
        "collected_recently",
    ]
    stage_deltas = [
        item.companies - baseline.stages[index].companies
        for index, item in enumerate(report.stages)
    ]
    assert stage_deltas == [
        5,
        4,
        3,
        2,
        1,
    ]
    assert [item.of_previous for item in report.stages] == [
        None,
        baseline.stages[0].companies + 5,
        baseline.stages[1].companies + 4,
        baseline.stages[2].companies + 3,
        baseline.stages[3].companies + 2,
    ]


def test_enabled_source_with_failing_run_is_not_operational(session: Session) -> None:
    baseline = company_coverage_funnel(session, window_days=7, now=NOW)
    _seed_funnel(session)

    report = company_coverage_funnel(session, window_days=7, now=NOW)

    assert report.stages[-1].companies == baseline.stages[-1].companies + 1
    assert report.enabled_but_unhealthy == baseline.enabled_but_unhealthy + 1


def test_multisource_opportunity_counts_once(session: Session) -> None:
    baseline = useful_yield_metrics(session, window_days=7, now=NOW)
    company = _company(session, "multisource-opportunity")
    sources = tuple(
        _source_definition(
            session,
            _company_source(session, company, f"multisource-{suffix}"),
            f"multisource-{suffix}",
            enabled=True,
            homologated=True,
        )
        for suffix in ("a", "b")
    )
    for index in range(20):
        opportunity = _opportunity(
            session,
            company,
            sources,
            tag=f"multisource-{index}",
            published_at=NOW - timedelta(hours=2) if index == 0 else None,
            first_seen_at=(NOW - timedelta(minutes=20), NOW - timedelta(minutes=5)),
            source_published_at=(
                (NOW - timedelta(hours=2), NOW - timedelta(hours=2))
                if index == 0
                else (None, None)
            ),
        )
        session.add(
            RelevanceMarkModel(
                opportunity_id=opportunity.id,
                relevant=index < 10,
                marked_at=NOW,
            )
        )
    _run(session, sources[0], http_requests=2)
    _run(session, sources[1], http_requests=3)

    report = useful_yield_metrics(session, window_days=7, now=NOW)

    assert report.new_unique_opportunities == baseline.new_unique_opportunities + 20
    assert report.requests == baseline.requests + 5
    assert report.discovery_delay_p50_seconds == pytest.approx(6_000)
    assert report.discovery_delay_p95_seconds == pytest.approx(6_000)
    assert report.contribution_by_source[sources[0].id] == 20
    assert report.contribution_by_source[sources[1].id] == 20
    assert report.judged_relevant == 10
    assert report.judged_opportunities == 20
    assert report.judgement_rate == 1
    assert report.yield_per_100_requests == 200


def test_metrics_expose_window_denominator_support_and_null(session: Session) -> None:
    baseline = useful_yield_metrics(session, window_days=7, now=NOW)
    company = _company(session, "no-trustworthy-publication")
    source = _source_definition(
        session,
        _company_source(session, company, "no-trustworthy-publication"),
        "no-trustworthy-publication",
        enabled=True,
        homologated=True,
    )
    _run(session, source, http_requests=12)
    opportunity = _opportunity(session, company, (source,), tag="missing-publication")
    session.add(
        RelevanceMarkModel(
            opportunity_id=opportunity.id, relevant=True, marked_at=NOW
        )
    )

    report = useful_yield_metrics(session, window_days=7, now=NOW)

    assert report.window_days == 7
    assert report.requests == baseline.requests + 12
    assert report.new_unique_opportunities == baseline.new_unique_opportunities + 1
    assert report.judged_opportunities == baseline.judged_opportunities + 1
    assert report.judged_relevant is None
    assert report.judgement_rate is None
    assert report.yield_per_100_requests is None
    assert report.discovery_delay_p50_seconds is None
    assert report.discovery_delay_p95_seconds is None


def test_endpoint_reports_funnel_block(session: Session) -> None:
    _seed_funnel(session)
    app = create_app(Settings(database_url=os.environ["DATABASE_URL"]))
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    try:
        response = client.get("/search-metrics", params={"window": "7d"})
    finally:
        app.dependency_overrides.pop(get_session)

    assert response.status_code == 200
    body = response.json()
    assert {"window_days", "generated_at", "coverage", "precision"} <= body.keys()
    assert body["company_coverage_funnel"]["stages"][-1]["stage"] == "collected_recently"
    assert body["useful_yield"]["window_days"] == 7
