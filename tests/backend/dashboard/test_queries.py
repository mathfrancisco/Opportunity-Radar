"""The inbox read model must agree with the catalogue and with the latest decision."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel, SourceRunModel
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.dashboard.queries import (
    InboxOrder,
    InboxQuery,
    list_opportunity_inbox,
    list_source_health,
    search_metrics,
    source_coverage_report,
    summarize_overview,
)
from opportunity_radar.matching.models import MatchAnalysisModel, MatchAssessmentModel
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.pipeline.domain import ApplicationStage
from opportunity_radar.pipeline.service import PipelineService
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _profile_version(session: Session) -> ProfileVersionModel:
    profile = session.scalar(select(CareerProfileModel).limit(1))
    if profile is None:
        profile = CareerProfileModel(version=1)
        session.add(profile)
        session.flush()
    version = ProfileVersionModel(
        career_profile_id=profile.id,
        number=(
            session.scalar(
                select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                    ProfileVersionModel.career_profile_id == profile.id
                )
            )
            or 0
        )
        + 1,
        status="DRAFT",
    )
    session.add(version)
    session.flush()
    # Loading a version as a domain object requires its preference row.
    session.add(EmploymentPreferenceModel(profile_version_id=version.id))
    session.flush()
    return version


def _company(session: Session, priority: str) -> Company:
    marker = uuid4().hex[:12]
    company = Company(
        canonical_name=f"Dashboard {marker}",
        normalized_name=f"dashboard-{marker}",
        priority=priority,
    )
    session.add(company)
    session.flush()
    return company


def _opportunity(
    session: Session,
    company: Company,
    *,
    title: str,
    published_at: datetime | None,
    lifecycle_status: str = "ACTIVE",
    work_mode: str = "REMOTE",
    seniority: str = "SENIOR",
    description: str | None = None,
    role_family: str = "UNKNOWN",
    search_skills: str | None = None,
) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title=title,
        normalized_title=title.lower(),
        canonical_company_id=company.id,
        company_name=company.canonical_name,
        work_mode=work_mode,
        seniority=seniority,
        contract_type="FULL_TIME",
        lifecycle_status=lifecycle_status,
        published_at=published_at,
        description=description,
        role_family=role_family,
        search_skills=search_skills,
        version=1,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def _assessment(
    session: Session,
    opportunity: OpportunityModel,
    profile_version_id: UUID,
    *,
    verdict: str,
    score: str,
    assessed_at: datetime,
) -> MatchAssessmentModel:
    assessment = MatchAssessmentModel(
        opportunity_id=opportunity.id,
        opportunity_version=opportunity.version,
        profile_version_id=profile_version_id,
        input_hash=uuid4().hex + uuid4().hex,
        rules_version="matching-v1",
        taxonomy_version="skills-v1",
        opportunity_snapshot={"work_mode": opportunity.work_mode},
        profile_snapshot={"skills": ["python"]},
        eligibility="ELIGIBLE",
        eligibility_details=[],
        verdict=verdict,
        score=Decimal(score),
        confidence=Decimal("0.900"),
        assessed_at=assessed_at,
    )
    session.add(assessment)
    session.flush()
    return assessment


def test_inbox_keeps_unassessed_opportunities_and_uses_the_latest_decision() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_version = _profile_version(session)
        company = _company(session, "high")
        assessed = _opportunity(
            session, company, title="Assessed role", published_at=NOW - timedelta(days=1)
        )
        never_assessed = _opportunity(
            session, company, title="Fresh role", published_at=NOW
        )
        _assessment(
            session,
            assessed,
            profile_version.id,
            verdict="WATCHLIST",
            score="40.0000",
            assessed_at=NOW - timedelta(hours=2),
        )
        current = _assessment(
            session,
            assessed,
            profile_version.id,
            verdict="HIGH_PRIORITY",
            score="91.5000",
            assessed_at=NOW,
        )
        session.add(
            MatchAnalysisModel(
                assessment_id=current.id,
                cache_key=uuid4().hex + uuid4().hex,
                status="AI_COMPLETED",
                summary="Strong match.",
                recommended_review=False,
                model_id="llama3.2:3b",
                prompt_version="opportunity_analysis/v1",
                schema_version="analysis-v1",
                analyzed_at=NOW,
            )
        )
        session.commit()

        page = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, order=InboxOrder.SCORE)
        )

        assert page.total == 2
        by_id = {item.opportunity_id: item for item in page.items}
        assert by_id[assessed.id].verdict == "HIGH_PRIORITY"
        assert by_id[assessed.id].score == Decimal("91.5000")
        assert by_id[assessed.id].assessment_id == current.id
        assert by_id[assessed.id].analysis_status == "AI_COMPLETED"
        assert by_id[assessed.id].analysis_recommended_review is False
        assert by_id[assessed.id].company_priority == "HIGH"
        assert by_id[never_assessed.id].assessment_id is None
        assert by_id[never_assessed.id].verdict is None
        assert page.items[0].opportunity_id == assessed.id


def test_inbox_prefers_a_current_assessment_and_falls_back_to_a_stale_one() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_version = _profile_version(session)
        session.execute(
            update(ProfileVersionModel)
            .where(ProfileVersionModel.id != profile_version.id)
            .values(status="ARCHIVED")
        )
        profile_version.status = "ACTIVE"
        company = _company(session, "normal")
        with_fresh = _opportunity(session, company, title="Current result", published_at=NOW)
        fallback_only = _opportunity(session, company, title="Waiting result", published_at=NOW)
        old_current = _assessment(
            session,
            with_fresh,
            profile_version.id,
            verdict="HIGH_PRIORITY",
            score="91.0000",
            assessed_at=NOW,
        )
        stale = _assessment(
            session,
            fallback_only,
            profile_version.id,
            verdict="WATCHLIST",
            score="40.0000",
            assessed_at=NOW,
        )
        with_fresh.version = fallback_only.version = 2
        fresh = _assessment(
            session,
            with_fresh,
            profile_version.id,
            verdict="RECOMMENDED",
            score="75.0000",
            assessed_at=NOW - timedelta(hours=1),
        )
        session.commit()

        items = {
            item.opportunity_id: item
            for item in list_opportunity_inbox(session, InboxQuery(company_id=company.id)).items
        }

        assert items[with_fresh.id].assessment_id == fresh.id
        assert items[with_fresh.id].is_stale is False
        assert items[with_fresh.id].assessment_opportunity_version == 2
        assert items[with_fresh.id].current_profile_version_id == profile_version.id
        assert items[fallback_only.id].assessment_id == stale.id
        assert items[fallback_only.id].is_stale is True
        assert items[fallback_only.id].assessment_opportunity_version == 1
        assert old_current.id != fresh.id


def test_inbox_filters_by_verdict_score_search_and_only_assessed() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_version = _profile_version(session)
        company = _company(session, "normal")
        strong = _opportunity(
            session, company, title="Staff Platform Engineer", published_at=NOW
        )
        weak = _opportunity(
            session, company, title="Junior Support Analyst", published_at=NOW
        )
        _opportunity(session, company, title="Unscored Role", published_at=NOW)
        _assessment(
            session,
            strong,
            profile_version.id,
            verdict="RECOMMENDED",
            score="82.0000",
            assessed_at=NOW,
        )
        _assessment(
            session,
            weak,
            profile_version.id,
            verdict="LOW_MATCH",
            score="12.0000",
            assessed_at=NOW,
        )
        session.commit()

        base = InboxQuery(company_id=company.id)
        assert list_opportunity_inbox(session, base).total == 3

        only_assessed = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, only_assessed=True)
        )
        assert only_assessed.total == 2

        recommended = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, verdicts=("RECOMMENDED",))
        )
        assert [item.opportunity_id for item in recommended.items] == [strong.id]

        scored = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, minimum_score=Decimal("50"))
        )
        assert [item.opportunity_id for item in scored.items] == [strong.id]

        searched = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="junior support")
        )
        assert [item.opportunity_id for item in searched.items] == [weak.id]


def test_inbox_filters_by_role_family_without_deleting_off_filter_rows() -> None:
    """Card F17-02: the area filter narrows the page, never hides a row for good."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        company = _company(session, "normal")
        engineering = _opportunity(
            session, company, title="Backend Engineer", published_at=NOW
        )
        engineering.role_family = "SOFTWARE_ENGINEERING"
        sales = _opportunity(session, company, title="Account Executive", published_at=NOW)
        sales.role_family = "SALES"
        session.commit()

        everything = list_opportunity_inbox(session, InboxQuery(company_id=company.id))
        assert everything.total == 2
        assert everything.off_filter_count == 0

        engineering_only = list_opportunity_inbox(
            session,
            InboxQuery(company_id=company.id, role_families=("SOFTWARE_ENGINEERING",)),
        )
        assert [item.opportunity_id for item in engineering_only.items] == [engineering.id]
        assert engineering_only.off_filter_count == 1

        # The sales role stays reachable without the area filter: never deleted.
        broadened = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="account executive")
        )
        assert [item.opportunity_id for item in broadened.items] == [sales.id]


def test_inbox_orders_by_priority_recency_and_score() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_version = _profile_version(session)
        high = _company(session, "high")
        low = _company(session, "low")
        old_high = _opportunity(
            session, high, title="Old at high", published_at=NOW - timedelta(days=30)
        )
        new_low = _opportunity(session, low, title="New at low", published_at=NOW)
        _assessment(
            session,
            old_high,
            profile_version.id,
            verdict="RECOMMENDED",
            score="70.0000",
            assessed_at=NOW,
        )
        _assessment(
            session,
            new_low,
            profile_version.id,
            verdict="HIGH_PRIORITY",
            score="95.0000",
            assessed_at=NOW,
        )
        session.commit()

        def ids(order: InboxOrder, company_id: UUID | None = None) -> list[UUID]:
            page = list_opportunity_inbox(
                session,
                InboxQuery(order=order, company_id=company_id, only_assessed=True, limit=200),
            )
            return [
                item.opportunity_id
                for item in page.items
                if item.opportunity_id in {old_high.id, new_low.id}
            ]

        assert ids(InboxOrder.PRIORITY) == [old_high.id, new_low.id]
        assert ids(InboxOrder.RECENCY) == [new_low.id, old_high.id]
        assert ids(InboxOrder.SCORE) == [new_low.id, old_high.id]


def test_inbox_knows_whether_an_opportunity_was_already_applied_to() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_version = _profile_version(session)
        company = _company(session, "normal")
        applied_to = _opportunity(session, company, title="Applied role", published_at=NOW)
        untouched = _opportunity(session, company, title="Open role", published_at=NOW)
        session.commit()

        application = PipelineService(session).start(
            applied_to.id,
            profile_version_id=profile_version.id,
            stage=ApplicationStage.APPLIED,
            next_action="Enviar follow-up",
            next_action_at=NOW + timedelta(days=2),
        )

        applied_page = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, applied=True)
        )
        open_page = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, applied=False)
        )

        assert [item.opportunity_id for item in applied_page.items] == [applied_to.id]
        assert [item.opportunity_id for item in open_page.items] == [untouched.id]
        item = applied_page.items[0]
        assert item.applied is True
        assert item.application_id == application.id
        assert item.application_stage == "APPLIED"
        assert item.application_next_action_at is not None
        assert open_page.items[0].applied is False

        summary = summarize_overview(session, now=NOW)
        assert summary.applications_active >= 1
        assert summary.applications_by_stage.get("APPLIED", 0) >= 1
        assert summary.follow_ups_due >= 1
        assert summary.follow_up_window_days == 7

        # Closing the application frees the opportunity again.
        PipelineService(session).transition(
            application.id,
            target=ApplicationStage.WITHDRAWN,
            expected_version=application.version,
        )
        reopened = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, applied=False)
        )
        assert {item.opportunity_id for item in reopened.items} == {
            applied_to.id,
            untouched.id,
        }


def test_source_health_reports_the_last_run_and_keeps_never_run_sources() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        failed = SourceDefinitionModel(
            source_type="manual",
            name=f"Failing {marker}",
            enabled=True,
            evidence_status="confirmed",
            terms_reviewed=True,
            collector_local_tested=True,
        )
        never_run = SourceDefinitionModel(
            source_type="manual",
            name=f"Idle {marker}",
            enabled=False,
        )
        session.add_all([failed, never_run])
        session.flush()
        session.add_all(
            [
                SourceRunModel(
                    source_definition_id=failed.id,
                    status="SUCCEEDED",
                    started_at=NOW - timedelta(hours=3),
                    finished_at=NOW - timedelta(hours=3) + timedelta(seconds=5),
                    items_seen=2,
                    items_persisted=2,
                ),
                SourceRunModel(
                    source_definition_id=failed.id,
                    status="FAILED",
                    started_at=NOW - timedelta(minutes=10),
                    finished_at=NOW - timedelta(minutes=9),
                    error_code="TRANSPORT_ERROR",
                    error_summary="connection reset",
                ),
            ]
        )
        session.commit()

        by_id = {item.source_definition_id: item for item in list_source_health(session)}

        assert by_id[failed.id].last_run_status == "FAILED"
        assert by_id[failed.id].last_run_error_code == "TRANSPORT_ERROR"
        assert by_id[failed.id].last_run_duration_seconds == 60
        assert by_id[failed.id].terms_reviewed is True
        # A source that never ran reports absence, not a zeroed run.
        assert by_id[never_run.id].last_run_status is None
        assert by_id[never_run.id].last_run_items_seen is None
        assert by_id[never_run.id].last_run_duration_seconds is None

        failing = list_source_health(session, only_failing=True)
        failing_ids = {item.source_definition_id for item in failing}
        assert failed.id in failing_ids
        assert never_run.id not in failing_ids


def test_source_coverage_distinguishes_disabled_not_run_and_successful_zero() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        zero = SourceDefinitionModel(
            source_type="manual", name=f"Zero {marker}", enabled=True
        )
        idle = SourceDefinitionModel(
            source_type="manual", name=f"Idle {marker}", enabled=True
        )
        proposal = SourceDefinitionModel(
            source_type="manual", name=f"Proposal {marker}", enabled=False
        )
        session.add_all([zero, idle, proposal])
        session.flush()
        session.add(
            SourceRunModel(
                source_definition_id=zero.id,
                status="SUCCEEDED",
                correlation_id="coverage-round",
                started_at=NOW - timedelta(minutes=2),
                finished_at=NOW - timedelta(minutes=1),
            )
        )
        session.commit()

        report = source_coverage_report(session, correlation_id="coverage-round")
        by_id = {source.source_definition_id: source for source in report.sources}

        assert report.correlation_id == "coverage-round"
        assert report.enabled_sources >= 2
        assert report.eligible_sources >= 2
        assert by_id[zero.id].state == "SUCCEEDED_ZERO"
        assert by_id[zero.id].raw_items == 0
        assert by_id[idle.id].state == "NOT_RUN"
        assert by_id[proposal.id].state == "NOT_ENABLED"


def test_overview_counts_reflect_the_catalogue_and_flag_the_missing_pipeline() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_version = _profile_version(session)
        company = _company(session, "high")
        opportunity = _opportunity(session, company, title="Overview role", published_at=NOW)
        _assessment(
            session,
            opportunity,
            profile_version.id,
            verdict="HIGH_PRIORITY",
            score="88.0000",
            assessed_at=NOW,
        )
        session.commit()

        summary = summarize_overview(session)

        assert summary.opportunities_total >= 1
        assert summary.opportunities_active >= 1
        assert summary.new_opportunities >= 1
        assert summary.new_opportunity_window_days == 7
        assert summary.assessed_opportunities >= 1
        assert summary.verdict_counts.get("HIGH_PRIORITY", 0) >= 1
        assert summary.sources_failing == len(summary.failing_sources)
        assert summary.applications_active == sum(summary.applications_by_stage.values())
        assert summary.follow_ups_due <= summary.applications_active


def test_search_metrics_reports_coverage_numeric_fields() -> None:
    """Card F17-01: per-source run counters, company coverage, and seniority-unknown."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        ats_company = Company(
            canonical_name=f"ATS Co {marker}",
            normalized_name=f"ats-co-{marker}",
        )
        plain_company = Company(
            canonical_name=f"Plain Co {marker}",
            normalized_name=f"plain-co-{marker}",
        )
        session.add_all([ats_company, plain_company])
        session.flush()

        ats_source = CompanySource(
            company_id=ats_company.id,
            source_type="greenhouse",
            endpoint=f"https://boards.greenhouse.io/{marker}",
        )
        session.add(ats_source)
        session.flush()

        source_definition = SourceDefinitionModel(
            source_type="greenhouse",
            name=f"Coverage source {marker}",
            enabled=True,
            company_source_id=ats_source.id,
        )
        session.add(source_definition)
        session.flush()

        session.add(
            SourceRunModel(
                source_definition_id=source_definition.id,
                status="SUCCEEDED",
                started_at=NOW - timedelta(minutes=5),
                finished_at=NOW - timedelta(minutes=4),
                items_seen=10,
                items_persisted=6,
                items_skipped=3,
                items_invalid=1,
            )
        )
        _opportunity(
            session, ats_company, title="Known Seniority", published_at=NOW,
            seniority="SENIOR",
        )
        _opportunity(
            session, plain_company, title="Unknown Seniority", published_at=NOW,
            seniority="UNKNOWN",
        )
        session.commit()

        report = search_metrics(session, window_days=7, now=NOW)

        by_source = {item.source_definition_id: item for item in report.coverage.by_source}
        assert by_source[source_definition.id].runs == 1
        assert by_source[source_definition.id].items_seen == 10
        assert by_source[source_definition.id].items_persisted == 6
        assert by_source[source_definition.id].items_duplicate == 3
        assert by_source[source_definition.id].items_invalid == 1
        assert report.coverage.runs >= 1
        assert report.coverage.items_seen >= 10
        assert report.coverage.items_duplicate >= 3
        assert report.coverage.companies_with_ats >= 1
        assert report.coverage.seniority_unknown_rate is not None
        assert report.coverage.seniority_unknown_rate > 0
