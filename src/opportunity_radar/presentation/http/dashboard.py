"""HTTP contract for the Overview and the Opportunity Inbox."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.queries import (
    FAILING_RUN_STATUSES,
    InboxItem,
    InboxOrder,
    InboxQuery,
    OverviewSummary,
    SourceCoverageReport,
    SourceHealth,
    list_opportunity_inbox,
    list_source_health,
    source_coverage_report,
    summarize_overview,
)
from opportunity_radar.opportunities.domain import OpportunityStatus, WorkMode
from opportunity_radar.presentation.http.dependencies import get_session

router = APIRouter(tags=["dashboard"])


class InboxItemResponse(BaseModel):
    opportunity_id: UUID
    title: str
    company_id: UUID | None
    company_name: str | None
    company_priority: str | None
    location: str | None
    work_mode: str
    seniority: str
    contract_type: str
    lifecycle_status: str
    published_at: datetime | None
    opportunity_version: int
    assessment_id: UUID | None
    assessment_opportunity_version: int | None
    assessment_profile_version_id: UUID | None
    current_profile_version_id: UUID | None
    verdict: str | None
    eligibility: str | None
    score: str | None
    confidence: str | None
    rules_version: str | None
    is_stale: bool | None
    assessed_at: datetime | None
    analysis_status: str | None
    analysis_recommended_review: bool | None
    analysis_summary: str | None
    applied: bool
    application_id: UUID | None
    application_stage: str | None
    application_next_action_at: datetime | None


class InboxPageResponse(BaseModel):
    items: list[InboxItemResponse]
    total: int
    offset: int
    limit: int
    order: str


class SourceHealthResponse(BaseModel):
    source_definition_id: UUID
    name: str
    source_type: str
    enabled: bool
    evidence_status: str
    terms_reviewed: bool
    collector_local_tested: bool
    schedule: str | None
    last_run_id: UUID | None
    last_run_status: str | None
    last_run_started_at: datetime | None
    last_run_finished_at: datetime | None
    last_run_duration_seconds: float | None
    last_run_error_code: str | None
    last_run_error: str | None
    last_run_items_seen: int | None
    last_run_items_persisted: int | None
    last_run_items_skipped: int | None
    last_run_items_invalid: int | None
    seniority_counts: dict[str, int]


class SourceHealthListResponse(BaseModel):
    items: list[SourceHealthResponse]
    total: int
    failing: int


class SourceCoverageResponse(BaseModel):
    source_definition_id: UUID
    name: str
    state: str
    run_status: str | None
    raw_items: int


class SourceCoverageReportResponse(BaseModel):
    correlation_id: str | None
    catalog_companies: int
    catalog_source_records: int
    proposed_sources: int
    homologated_sources: int
    enabled_sources: int
    eligible_sources: int
    sources: list[SourceCoverageResponse]


class OverviewResponse(BaseModel):
    opportunities_total: int
    opportunities_active: int
    new_opportunities: int
    new_opportunity_window_days: int
    assessed_opportunities: int
    verdict_counts: dict[str, int]
    analyses_degraded: int
    sources_total: int
    sources_enabled: int
    sources_failing: int
    failing_sources: list[SourceHealthResponse]
    pending_normalizations: int
    applications_active: int
    applications_by_stage: dict[str, int]
    follow_ups_due: int
    follow_up_window_days: int


@router.get("/inbox", response_model=InboxPageResponse)
def list_inbox(
    verdict: list[str] | None = Query(default=None),
    minimum_score: Decimal | None = Query(default=None, ge=0, le=100),
    company_id: UUID | None = None,
    work_mode: WorkMode | None = None,
    lifecycle_status: OpportunityStatus | None = None,
    published_after: datetime | None = None,
    only_assessed: bool = False,
    applied: bool | None = None,
    search: str | None = None,
    profile_version_id: UUID | None = None,
    order: InboxOrder = InboxOrder.PRIORITY,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> InboxPageResponse:
    page = list_opportunity_inbox(
        session,
        InboxQuery(
            verdicts=tuple(verdict or ()),
            minimum_score=minimum_score,
            company_id=company_id,
            work_mode=work_mode.value if work_mode else None,
            lifecycle_status=lifecycle_status.value if lifecycle_status else None,
            published_after=published_after,
            only_assessed=only_assessed,
            applied=applied,
            search=search,
            profile_version_id=profile_version_id,
            order=order,
            offset=offset,
            limit=limit,
        ),
    )
    return InboxPageResponse(
        items=[_inbox_item_response(item) for item in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
        order=order.value,
    )


@router.get("/source-health", response_model=SourceHealthListResponse)
def list_sources_health(
    only_failing: bool = False,
    session: Session = Depends(get_session),
) -> SourceHealthListResponse:
    """Named `/source-health` rather than `/sources/health`: that path is a source id."""
    items = list_source_health(session, only_failing=only_failing)
    failing = sum(1 for item in items if item.last_run_status in FAILING_RUN_STATUSES)
    return SourceHealthListResponse(
        items=[_source_response(item) for item in items],
        total=len(items),
        failing=failing,
    )


@router.get("/source-coverage", response_model=SourceCoverageReportResponse)
def get_source_coverage(
    correlation_id: str | None = None,
    session: Session = Depends(get_session),
) -> SourceCoverageReportResponse:
    return _source_coverage_response(
        source_coverage_report(session, correlation_id=correlation_id)
    )


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    profile_version_id: UUID | None = None,
    session: Session = Depends(get_session),
) -> OverviewResponse:
    return _overview_response(
        summarize_overview(session, profile_version_id=profile_version_id)
    )


def _inbox_item_response(item: InboxItem) -> InboxItemResponse:
    return InboxItemResponse(
        opportunity_id=item.opportunity_id,
        title=item.title,
        company_id=item.company_id,
        company_name=item.company_name,
        company_priority=item.company_priority,
        location=item.location,
        work_mode=item.work_mode,
        seniority=item.seniority,
        contract_type=item.contract_type,
        lifecycle_status=item.lifecycle_status,
        published_at=item.published_at,
        opportunity_version=item.opportunity_version,
        assessment_id=item.assessment_id,
        assessment_opportunity_version=item.assessment_opportunity_version,
        assessment_profile_version_id=item.assessment_profile_version_id,
        current_profile_version_id=item.current_profile_version_id,
        verdict=item.verdict,
        eligibility=item.eligibility,
        score=str(item.score) if item.score is not None else None,
        confidence=str(item.confidence) if item.confidence is not None else None,
        rules_version=item.rules_version,
        is_stale=item.is_stale,
        assessed_at=item.assessed_at,
        analysis_status=item.analysis_status,
        analysis_recommended_review=item.analysis_recommended_review,
        analysis_summary=item.analysis_summary,
        applied=item.applied,
        application_id=item.application_id,
        application_stage=item.application_stage,
        application_next_action_at=item.application_next_action_at,
    )


def _overview_response(summary: OverviewSummary) -> OverviewResponse:
    return OverviewResponse(
        opportunities_total=summary.opportunities_total,
        opportunities_active=summary.opportunities_active,
        new_opportunities=summary.new_opportunities,
        new_opportunity_window_days=summary.new_opportunity_window_days,
        assessed_opportunities=summary.assessed_opportunities,
        verdict_counts=summary.verdict_counts,
        analyses_degraded=summary.analyses_degraded,
        sources_total=summary.sources_total,
        sources_enabled=summary.sources_enabled,
        sources_failing=summary.sources_failing,
        failing_sources=[_source_response(item) for item in summary.failing_sources],
        pending_normalizations=summary.pending_normalizations,
        applications_active=summary.applications_active,
        applications_by_stage=summary.applications_by_stage,
        follow_ups_due=summary.follow_ups_due,
        follow_up_window_days=summary.follow_up_window_days,
    )


def _source_response(source: SourceHealth) -> SourceHealthResponse:
    return SourceHealthResponse(
        source_definition_id=source.source_definition_id,
        name=source.name,
        source_type=source.source_type,
        enabled=source.enabled,
        evidence_status=source.evidence_status,
        terms_reviewed=source.terms_reviewed,
        collector_local_tested=source.collector_local_tested,
        schedule=source.schedule,
        last_run_id=source.last_run_id,
        last_run_status=source.last_run_status,
        last_run_started_at=source.last_run_started_at,
        last_run_finished_at=source.last_run_finished_at,
        last_run_duration_seconds=source.last_run_duration_seconds,
        last_run_error_code=source.last_run_error_code,
        last_run_error=source.last_run_error,
        last_run_items_seen=source.last_run_items_seen,
        last_run_items_persisted=source.last_run_items_persisted,
        last_run_items_skipped=source.last_run_items_skipped,
        last_run_items_invalid=source.last_run_items_invalid,
        seniority_counts=source.seniority_counts,
    )


def _source_coverage_response(
    report: SourceCoverageReport,
) -> SourceCoverageReportResponse:
    return SourceCoverageReportResponse(
        correlation_id=report.correlation_id,
        catalog_companies=report.catalog_companies,
        catalog_source_records=report.catalog_source_records,
        proposed_sources=report.proposed_sources,
        homologated_sources=report.homologated_sources,
        enabled_sources=report.enabled_sources,
        eligible_sources=report.eligible_sources,
        sources=[
            SourceCoverageResponse(
                source_definition_id=source.source_definition_id,
                name=source.name,
                state=source.state,
                run_status=source.run_status,
                raw_items=source.raw_items,
            )
            for source in report.sources
        ],
    )
