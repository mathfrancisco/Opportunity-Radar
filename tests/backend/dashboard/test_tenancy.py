"""Dashboard read models keep personal activity inside the verified owner boundary."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard.queries import (
    InboxQuery,
    list_opportunity_inbox,
    summarize_overview,
)
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_development_app
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

OWNER_A = "owner-a-synthetic"
OWNER_B = "owner-b-synthetic"
NOW = datetime.now(UTC)


def _profile(session: Session, owner_sub: str) -> ProfileVersionModel:
    profile = CareerProfileModel(version=1, owner_sub=owner_sub)
    session.add(profile)
    session.flush()
    version = ProfileVersionModel(career_profile_id=profile.id, number=1, status="ACTIVE")
    session.add(version)
    session.flush()
    return version


def _assessment(
    session: Session,
    *,
    opportunity: OpportunityModel,
    profile_version: ProfileVersionModel,
    owner_sub: str,
    verdict: str,
    score: str,
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
            score=Decimal(score),
            confidence=Decimal("0.9"),
            assessed_at=NOW,
        )
    )
    session.flush()


def test_dashboard_routes_reject_requests_without_a_verified_identity() -> None:
    """Even the local app factory cannot make dashboard data anonymously readable."""
    client = TestClient(create_development_app(Settings(database_url=os.environ["DATABASE_URL"])))
    assert client.get("/inbox").status_code == 401
    assert client.get("/overview").status_code == 401


def test_inbox_and_overview_scope_personal_assessments_and_applications() -> None:
    """A member cannot obtain another member's scores, verdicts, IDs, or follow-ups."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_a = _profile(session, OWNER_A)
        profile_b = _profile(session, OWNER_B)
        company = Company(
            canonical_name=f"Tenant {uuid4().hex}",
            normalized_name=f"tenant-{uuid4().hex}",
            priority="normal",
        )
        session.add(company)
        session.flush()
        opportunity = OpportunityModel(
            fingerprint=uuid4().hex,
            fingerprint_version="v1",
            canonical_title="Tenant-safe role",
            normalized_title="tenant-safe role",
            canonical_company_id=company.id,
            company_name=company.canonical_name,
            work_mode="REMOTE",
            seniority="SENIOR",
            contract_type="FULL_TIME",
            lifecycle_status="ACTIVE",
            published_at=NOW,
            version=1,
        )
        session.add(opportunity)
        session.flush()
        _assessment(
            session,
            opportunity=opportunity,
            profile_version=profile_a,
            owner_sub=OWNER_A,
            verdict="RECOMMENDED",
            score="81",
        )
        _assessment(
            session,
            opportunity=opportunity,
            profile_version=profile_b,
            owner_sub=OWNER_B,
            verdict="LOW_MATCH",
            score="13",
        )
        session.add_all(
            [
                ApplicationProcessModel(
                    owner_sub=OWNER_A,
                    opportunity_id=opportunity.id,
                    profile_version_id=profile_a.id,
                    current_stage="APPLIED",
                    status="ACTIVE",
                    started_at=NOW,
                    next_action_at=NOW + timedelta(days=1),
                    version=1,
                ),
                ApplicationProcessModel(
                    owner_sub=OWNER_B,
                    opportunity_id=opportunity.id,
                    profile_version_id=profile_b.id,
                    current_stage="INTERVIEW",
                    status="ACTIVE",
                    started_at=NOW,
                    next_action_at=NOW + timedelta(days=1),
                    version=1,
                ),
            ]
        )
        session.flush()

        member_a = list_opportunity_inbox(
            session, InboxQuery(search="tenant-safe"), owner_sub=OWNER_A
        )
        member_b = list_opportunity_inbox(
            session, InboxQuery(search="tenant-safe"), owner_sub=OWNER_B
        )

        assert len(member_a.items) == len(member_b.items) == 1
        assert member_a.items[0].verdict == "RECOMMENDED"
        assert str(member_a.items[0].score) == "81.0000"
        assert member_a.items[0].application_stage == "APPLIED"
        assert member_b.items[0].verdict == "LOW_MATCH"
        assert str(member_b.items[0].score) == "13.0000"
        assert member_b.items[0].application_stage == "INTERVIEW"

        overview_a = summarize_overview(session, owner_sub=OWNER_A, now=NOW)
        overview_b = summarize_overview(session, owner_sub=OWNER_B, now=NOW)
        assert overview_a.verdict_counts == {"RECOMMENDED": 1}
        assert overview_b.verdict_counts == {"LOW_MATCH": 1}
        assert overview_a.applications_by_stage == {"APPLIED": 1}
        assert overview_b.applications_by_stage == {"INTERVIEW": 1}
        assert overview_a.follow_ups_due == overview_b.follow_ups_due == 1
        # The member summary never runs nor exposes operations/source diagnostics.
        assert overview_a.sources_total == overview_a.pending_normalizations == 0
