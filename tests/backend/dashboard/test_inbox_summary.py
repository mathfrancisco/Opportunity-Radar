"""Inbox summary: worth count, collected-since-yesterday count and next collection."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel, SourceRunModel
from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard.inbox_summary import inbox_summary, summary_since
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_development_app
from opportunity_radar.presentation.http.auth import RequestIdentity, authenticated_identity
from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel

NOW = datetime(2026, 10, 20, 3, 30, tzinfo=UTC)

needs_database = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def test_since_is_midnight_of_yesterday_in_sao_paulo_as_utc() -> None:
    assert summary_since(NOW) == datetime(2026, 10, 19, 3, 0, tzinfo=UTC)
    # 02:30Z on the 20th is still the 19th in Sao Paulo, so yesterday is the 18th.
    assert summary_since(datetime(2026, 10, 20, 2, 30, tzinfo=UTC)) == datetime(
        2026, 10, 18, 3, 0, tzinfo=UTC
    )


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as db:
        yield db
        db.rollback()


def _profile(session: Session, owner_sub: str) -> ProfileVersionModel:
    profile = CareerProfileModel(version=1, owner_sub=owner_sub)
    session.add(profile)
    session.flush()
    version = ProfileVersionModel(career_profile_id=profile.id, number=1, status="DRAFT")
    session.add(version)
    session.flush()
    return version


def _posting(session: Session, *, first_seen_at: datetime) -> OpportunityModel:
    company = Company(
        canonical_name=f"Summary {uuid4().hex}",
        normalized_name=f"summary-{uuid4().hex}",
        priority="normal",
    )
    session.add(company)
    session.flush()
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Summary role",
        normalized_title="summary role",
        canonical_company_id=company.id,
        company_name=company.canonical_name,
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        published_at=NOW,
        first_seen_at=first_seen_at,
        version=1,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def _assess(
    session: Session,
    opportunity: OpportunityModel,
    profile_version: ProfileVersionModel,
    owner_sub: str,
    verdict: str,
) -> None:
    session.add(
        MatchAssessmentModel(
            owner_sub=owner_sub,
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            profile_version_id=profile_version.id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version=RULES_VERSION,
            taxonomy_version=SKILL_TAXONOMY_VERSION,
            opportunity_snapshot={},
            profile_snapshot={},
            eligibility="ELIGIBLE",
            eligibility_details=[],
            verdict=verdict,
            score=Decimal("80"),
            confidence=Decimal("0.9"),
            assessed_at=NOW,
        )
    )
    session.flush()


@pytest.mark.integration
@needs_database
def test_counts_follow_since_verdict_and_owner(session: Session) -> None:
    owner, other = f"owner-{uuid4().hex}", f"other-{uuid4().hex}"
    mine, theirs = _profile(session, owner), _profile(session, other)
    before = inbox_summary(session, owner, now=NOW)
    since = before.since

    top = _posting(session, first_seen_at=since)
    recommended = _posting(session, first_seen_at=since + timedelta(hours=5))
    low = _posting(session, first_seen_at=since + timedelta(hours=6))
    # Seen at 01:00Z on the 19th: 22:00 on the 18th in Sao Paulo, before `since`.
    too_old = _posting(session, first_seen_at=datetime(2026, 10, 19, 1, 0, tzinfo=UTC))
    foreign = _posting(session, first_seen_at=since + timedelta(hours=7))
    _assess(session, top, mine, owner, "HIGH_PRIORITY")
    _assess(session, recommended, mine, owner, "RECOMMENDED")
    _assess(session, low, mine, owner, "LOW_MATCH")
    _assess(session, too_old, mine, owner, "HIGH_PRIORITY")
    # Only the other member rated this one as worth it: it must not count for `owner`.
    _assess(session, foreign, theirs, other, "HIGH_PRIORITY")

    after = inbox_summary(session, owner, now=NOW)
    assert after.since == datetime(2026, 10, 19, 3, 0, tzinfo=UTC)
    assert after.collected_count - before.collected_count == 4
    assert after.worth_count - before.worth_count == 2
    assert inbox_summary(session, other, now=NOW).worth_count >= 1


def _source(
    session: Session,
    name: str,
    schedule: str | None,
    *,
    enabled: bool = True,
    last_run_at: datetime | None = None,
) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        source_type="greenhouse",
        name=f"{name}-{uuid4().hex}",
        enabled=enabled,
        schedule=schedule,
        configuration={"board_token": uuid4().hex},
    )
    session.add(source)
    session.flush()
    if last_run_at is not None:
        session.add(
            SourceRunModel(
                source_definition_id=source.id,
                status="SUCCEEDED",
                started_at=last_run_at,
                finished_at=last_run_at + timedelta(minutes=1),
            )
        )
        session.flush()
    return source


@pytest.mark.integration
@needs_database
def test_next_collection_is_earliest_due_time_among_scheduled_sources(
    session: Session,
) -> None:
    session.execute(update(SourceDefinitionModel).values(enabled=False))
    owner = f"o-{uuid4().hex}"
    assert inbox_summary(session, owner, now=NOW).next_collection_at is None

    _source(session, "manual", "manual")
    _source(session, "none", None)
    _source(session, "disabled", "0 3 * * *", enabled=False)
    assert inbox_summary(session, owner, now=NOW).next_collection_at is None

    # Both ran yesterday afternoon, so their next slot is a real cron fire time.
    yesterday = datetime(2026, 10, 19, 20, 0, tzinfo=UTC)
    _source(session, "daily", "0 6 * * *", last_run_at=yesterday)
    _source(session, "later", "0 9 * * *", last_run_at=yesterday)
    summary = inbox_summary(session, owner, now=NOW)
    assert summary.next_collection_at == datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
    assert summary.generated_at == NOW


@pytest.mark.integration
@needs_database
def test_a_never_run_scheduled_source_is_reported_as_due_now(session: Session) -> None:
    session.execute(update(SourceDefinitionModel).values(enabled=False))
    _source(session, "later", "0 9 * * *", last_run_at=datetime(2026, 10, 19, 20, 0, tzinfo=UTC))
    _source(session, "fresh", "0 6 * * *")

    summary = inbox_summary(session, f"o-{uuid4().hex}", now=NOW)

    assert summary.next_collection_at == NOW
    assert summary.generated_at == NOW


@pytest.mark.integration
@needs_database
def test_a_source_with_an_invalid_schedule_is_skipped(session: Session) -> None:
    session.execute(update(SourceDefinitionModel).values(enabled=False))
    _source(session, "broken", "not a cron", last_run_at=datetime(2026, 10, 19, 20, 0, tzinfo=UTC))
    _source(session, "ok", "0 9 * * *", last_run_at=datetime(2026, 10, 19, 20, 0, tzinfo=UTC))

    summary = inbox_summary(session, f"o-{uuid4().hex}", now=NOW)

    assert summary.next_collection_at == datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    owner = f"test-summary-{uuid4().hex}"
    app = create_development_app(Settings(database_url=os.environ["DATABASE_URL"]))
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[authenticated_identity] = lambda: RequestIdentity(
        sub=owner, is_owner=False
    )
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.mark.integration
@needs_database
def test_summary_route_is_not_shadowed_and_returns_the_contract(client: TestClient) -> None:
    response = client.get("/inbox/summary")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "worth_count",
        "collected_count",
        "since",
        "next_collection_at",
        "generated_at",
    }
    assert body["worth_count"] <= body["collected_count"]


@pytest.mark.integration
@needs_database
def test_summary_route_requires_identity() -> None:
    app = create_development_app(Settings(database_url=os.environ["DATABASE_URL"]))
    assert TestClient(app).get("/inbox/summary").status_code == 401
