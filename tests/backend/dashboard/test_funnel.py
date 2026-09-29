"""F48-06: funnel and north-star, with exact counts on a seeded catalogue.

The test database is shared and never truncated, so every count is asserted as the delta
between two reports taken around a seeded, never-committed transaction.
"""

from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.funnel import (
    TECHNICAL_PROXY_FAMILIES,
    FunnelReport,
    funnel_report,
)
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)
from tests.backend.dashboard.test_metrics import NOW, _normalized_posting, _run, _source

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _profile_version(session: Session) -> ProfileVersionModel:
    profile = CareerProfileModel(version=1)
    session.add(profile)
    session.flush()
    version = ProfileVersionModel(career_profile_id=profile.id, number=1, status="DRAFT")
    session.add(version)
    session.flush()
    session.add(EmploymentPreferenceModel(profile_version_id=version.id))
    session.flush()
    return version


def _posting(
    session: Session,
    marker: str,
    company: str,
    title: str,
    *,
    family: str,
    created_ago: timedelta = timedelta(hours=1),
    published_ago: timedelta | None = timedelta(days=1),
    lifecycle: str = "ACTIVE",
    countries: list[str] | None = None,
    duplicate_of: Any = None,
) -> OpportunityModel:
    published = None if published_ago is None else NOW - published_ago
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title=title,
        normalized_title=title.lower(),
        company_name=f"{company} {marker}",
        normalized_company_name=f"{company.lower()}-{marker}",
        work_mode="REMOTE",
        seniority="UNKNOWN",
        contract_type="FULL_TIME",
        lifecycle_status=lifecycle,
        role_family=family,
        published_at=published,
        first_seen_at=published or NOW,
        created_at=NOW - created_ago,
        allowed_countries=countries,
        duplicate_of=duplicate_of,
        version=1,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def _assess(session: Session, opportunity: OpportunityModel, version_id: Any, verdict: str) -> None:
    session.add(
        MatchAssessmentModel(
            opportunity_id=opportunity.id,
            opportunity_version=1,
            profile_version_id=version_id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version="matching-v1",
            taxonomy_version=SKILL_TAXONOMY_VERSION,
            opportunity_snapshot={},
            profile_snapshot={},
            eligibility="ELIGIBLE",
            eligibility_details=[],
            verdict=verdict,
            score=Decimal("50"),
            confidence=Decimal("0.900"),
            assessed_at=NOW,
        )
    )
    session.flush()


def _stages(report: FunnelReport) -> dict[str, int]:
    return {stage.key: stage.count for stage in report.stages}


def test_funnel_and_north_star_have_exact_counts_on_a_seeded_catalogue() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        try:
            before = funnel_report(session, now=NOW)
            before_data = funnel_report(session, now=NOW, target_role_families=("DATA",))
            marker = uuid4().hex[:8]
            version = _profile_version(session)
            first = _posting(
                session, marker, "Alpha", "Backend Engineer",
                family="SOFTWARE_ENGINEERING", created_ago=timedelta(hours=2),
            )
            # Same company and title in another city: one posting, not two.
            _posting(
                session, marker, "Alpha", "Backend Engineer",
                family="SOFTWARE_ENGINEERING", created_ago=timedelta(hours=3),
            )
            _posting(
                session, marker, "Beta", "Data Engineer", family="DATA",
                created_ago=timedelta(hours=30), published_ago=timedelta(days=2),
            )
            _posting(session, marker, "Gamma", "Sales Rep", family="SALES")
            _posting(session, marker, "Delta", "SRE", family="INFRASTRUCTURE", countries=["US"])
            _posting(session, marker, "Eps", "Security Eng", family="SECURITY", lifecycle="CLOSED")
            _posting(
                session, marker, "Zeta", "Old role", family="SOFTWARE_ENGINEERING",
                created_ago=timedelta(days=60), published_ago=timedelta(days=60),
            )
            _posting(
                session, marker, "Eta", "Dup", family="SOFTWARE_ENGINEERING",
                duplicate_of=first.id,
            )
            ineligible = _posting(session, marker, "Theta", "ML Eng", family="DATA")
            _assess(session, ineligible, version.id, "INELIGIBLE")
            useful = _posting(
                session, marker, "Iota", "Platform Eng",
                family="INFRASTRUCTURE", countries=["BR"],
            )
            _assess(session, useful, version.id, "HIGH_PRIORITY")

            after = funnel_report(session, now=NOW)
            stage_delta = {
                key: value - _stages(before)[key] for key, value in _stages(after).items()
            }
            assert stage_delta["opportunities"] == 10
            assert stage_delta["open"] == 8
            assert stage_delta["unique_company_title"] == 7
            assert stage_delta["default_filter"] == 7
            assert stage_delta["assessed"] == 2
            assert stage_delta["verdict"] == 1

            was, now = dict(before.north_star.stack), dict(after.north_star.stack)
            assert {key: now[key] - was[key] for key in now} == {
                "open": 8,
                "recent": 7,
                "not_ineligible": 6,
                "country": 5,
                "area": 4,
                "unique_company_title": 3,
            }
            assert after.north_star.proxy is True
            assert after.north_star.role_families == TECHNICAL_PROXY_FAMILIES
            assert after.north_star.stock - before.north_star.stock == 3
            assert after.north_star.new_in_window - before.north_star.new_in_window == 2

            # A profile that names areas replaces the proxy: only Beta/DATA survives.
            data = funnel_report(session, now=NOW, target_role_families=("DATA",))
            assert data.north_star.proxy is False
            assert data.north_star.stock - before_data.north_star.stock == 1
            assert data.north_star.new_in_window - before_data.north_star.new_in_window == 0
        finally:
            session.rollback()


def test_funnel_counts_sources_raw_items_and_normalization_stages() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        try:
            before = _stages(funnel_report(session, now=NOW))
            ran = _source(session)
            _source(session)  # enabled, never ran
            _source(session, enabled=False)
            run = _run(session, ran, status="SUCCEEDED", started_at=NOW - timedelta(hours=1))
            _normalized_posting(
                session, ran, run, seniority="SENIOR", evidence="title", processed_at=NOW
            )
            after = _stages(funnel_report(session, now=NOW))
            assert after["sources_enabled"] - before["sources_enabled"] == 2
            assert after["sources_collected"] - before["sources_collected"] == 1
            assert after["raw_items"] - before["raw_items"] == 1
            assert after["normalized"] - before["normalized"] == 1
        finally:
            session.rollback()


def test_funnel_reports_guards_and_marks_unmeasurable_ones() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        report = funnel_report(session, now=NOW)
    assert {
        "sources_on_schedule",
        "normalization_failed",
        "default_list_repetition",
        "seniority_unknown",
        "work_mode_unknown",
        "country_unknown",
        "useful_verdict",
        "ai_failed_by_quota",
    } <= set(report.guards)
    assert "false_closures" in report.not_measured
    assert report.forbidden_hosts_touched >= 0
