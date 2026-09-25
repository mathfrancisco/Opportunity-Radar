"""HTTP contract for the Overview and the Opportunity Inbox."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.analysis_metrics import (
    AnalysisMetricsWindow,
    ModelAnalysisMetrics,
    analysis_metrics,
)
from opportunity_radar.dashboard.metrics import (
    METRIC_WINDOWS,
    SourceMetricsWindow,
    SourceWindowMetrics,
    source_metrics,
)
from opportunity_radar.dashboard.queries import (
    FAILING_RUN_STATUSES,
    InboxItem,
    InboxOrder,
    InboxQuery,
    OverviewSummary,
    SearchMetricsReport,
    SourceCoverageReport,
    SourceHealth,
    list_opportunity_inbox,
    list_source_health,
    search_metrics,
    source_coverage_report,
    summarize_overview,
)
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.opportunities.domain import OpportunityStatus, Seniority, WorkMode
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

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
    role_family: str
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
    off_filter_count: int


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


class SeniorityDistributionResponse(BaseModel):
    counts: dict[str, int]
    percentages: dict[str, float]
    known: int
    unknown: int
    total: int
    mapping_versions: dict[str, int]
    evidence: dict[str, int]


class SourceMetricsResponse(BaseModel):
    source_definition_id: UUID
    name: str
    source_type: str
    enabled: bool
    schedule: str | None
    coverage_state: str
    runs: int
    runs_succeeded: int
    runs_partial: int
    runs_failed: int
    items_seen: int
    items_persisted: int
    items_skipped: int
    items_invalid: int
    latency_p95_seconds: float | None
    #: `null` rather than zero when the window holds no run: an unmeasured rate and a
    #: perfect one must not read the same.
    error_rate: float | None
    dedupe_rate: float | None
    has_runs: bool
    errors_by_code: dict[str, int]
    seniority: SeniorityDistributionResponse
    incident_open: bool


class SourceMetricsWindowResponse(BaseModel):
    window: str
    since: datetime
    until: datetime
    sources: list[SourceMetricsResponse]


class SourceMetricsReportResponse(BaseModel):
    generated_at: datetime
    windows: list[SourceMetricsWindowResponse]


class ModelAnalysisMetricsResponse(BaseModel):
    model_id: str | None
    analyses: int
    completed: int
    failed: int
    #: Percentiles and averages are `null` when no row in the window recorded the cost.
    total_ms_p50: float | None
    total_ms_p95: float | None
    total_ms_p99: float | None
    prompt_tokens_avg: float | None
    output_tokens_avg: float | None
    load_ms_avg: float | None
    failure_rate: float | None
    failure_rates: dict[str, float]
    reuse_rate: float | None


class AnalysisMetricsWindowResponse(BaseModel):
    window: str
    since: datetime
    until: datetime
    models: list[ModelAnalysisMetricsResponse]


class AnalysisMetricsReportResponse(BaseModel):
    generated_at: datetime
    current_model: str
    pending: int
    windows: list[AnalysisMetricsWindowResponse]


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
    precision_percent: str | None
    precision_marked_count: int
    companies_covered: int
    companies_with_ats: int


class SourceCoverageMetricResponse(BaseModel):
    source_definition_id: UUID
    name: str
    runs: int
    items_seen: int
    items_persisted: int
    items_duplicate: int
    items_invalid: int
    new_opportunities: int


class CoverageMetricsResponse(BaseModel):
    window_days: int
    runs: int
    items_seen: int
    items_persisted: int
    items_duplicate: int
    items_invalid: int
    new_opportunities: int
    companies_covered: int
    companies_with_ats: int
    seniority_unknown_rate: str | None
    role_family_unknown_rate: str | None
    by_source: list[SourceCoverageMetricResponse]


class PrecisionMetricsResponse(BaseModel):
    sample_size: int
    marked_count: int
    relevant_count: int
    precision: str | None


class SearchMetricsResponse(BaseModel):
    window_days: int
    generated_at: datetime
    coverage: CoverageMetricsResponse
    precision: PrecisionMetricsResponse


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
    role_family: list[str] | None = Query(default=None),
    all_areas: bool = False,
    seniority: list[Seniority] | None = Query(default=None),
    allowed_country: str | None = None,
    salary_min: Decimal | None = Query(default=None, ge=0),
    salary_max: Decimal | None = Query(default=None, ge=0),
    source_definition_id: list[UUID] | None = Query(default=None),
    profile_version_id: UUID | None = None,
    order: InboxOrder = InboxOrder.PRIORITY,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> InboxPageResponse:
    role_families = tuple(role_family or ())
    if not role_families and not all_areas:
        try:
            active = ProfileService(session).get_active()
            role_families = tuple(active.snapshot.preferences.target_role_families)
        except ProfileNotFoundError:
            role_families = ()
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
            seniorities=tuple(item.value for item in seniority or ()),
            allowed_country=allowed_country,
            salary_min=salary_min,
            salary_max=salary_max,
            source_definition_ids=tuple(source_definition_id or ()),
            role_families=role_families,
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
        off_filter_count=page.off_filter_count,
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


@router.get("/source-metrics", response_model=SourceMetricsReportResponse)
def get_source_metrics(
    window: str | None = Query(
        default=None, description="Restrict the answer to one window: 24h or 7d."
    ),
    session: Session = Depends(get_session),
) -> SourceMetricsReportResponse:
    """Both windows by default, because one of them alone hides a slow degradation."""
    report = source_metrics(session, windows=_selected_window(window))
    return SourceMetricsReportResponse(
        generated_at=report.generated_at,
        windows=[_metrics_window_response(item) for item in report.windows],
    )


@router.get("/analysis-metrics", response_model=AnalysisMetricsReportResponse)
def get_analysis_metrics(
    window: str | None = Query(
        default=None, description="Restrict the answer to one window: 24h or 7d."
    ),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AnalysisMetricsReportResponse:
    """Grouped by model, because a window can span a model change."""
    selected = _selected_window(window)
    pending = MatchingService(session).count_pending_analysis(
        eligible_verdicts=settings.analysis_eligible_verdicts,
        cooldown=timedelta(seconds=settings.analysis_retry_cooldown_seconds),
        attempt_window=timedelta(seconds=settings.analysis_retry_attempt_window_seconds),
        max_attempts=settings.analysis_retry_max_attempts,
    )
    report = analysis_metrics(
        session,
        current_model=settings.ollama_model_analysis,
        pending=pending,
        windows=selected,
    )
    return AnalysisMetricsReportResponse(
        generated_at=report.generated_at,
        current_model=report.current_model,
        pending=report.pending,
        windows=[_analysis_window_response(item) for item in report.windows],
    )


@router.get("/search-metrics", response_model=SearchMetricsResponse)
def get_search_metrics(
    window: str = Query(default="7d", pattern=r"^\d+d$"),
    profile_version_id: UUID | None = None,
    session: Session = Depends(get_session),
) -> SearchMetricsResponse:
    """`GET /search-metrics?window=7d` — SPEC §3, card F17-01."""
    window_days = int(window[:-1])
    report = search_metrics(
        session, window_days=window_days, profile_version_id=profile_version_id
    )
    return _search_metrics_response(report)


@router.get("/overview", response_model=OverviewResponse)
def get_overview(
    profile_version_id: UUID | None = None,
    session: Session = Depends(get_session),
) -> OverviewResponse:
    return _overview_response(
        summarize_overview(session, profile_version_id=profile_version_id)
    )


def _selected_window(window: str | None) -> dict[str, timedelta] | None:
    if window is None:
        return None
    if window not in METRIC_WINDOWS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "unknown_metric_window",
                "message": f"Window must be one of: {', '.join(METRIC_WINDOWS)}.",
            },
        )
    return {window: METRIC_WINDOWS[window]}


def _analysis_window_response(window: AnalysisMetricsWindow) -> AnalysisMetricsWindowResponse:
    return AnalysisMetricsWindowResponse(
        window=window.window,
        since=window.since,
        until=window.until,
        models=[_model_analysis_response(item) for item in window.models],
    )


def _model_analysis_response(item: ModelAnalysisMetrics) -> ModelAnalysisMetricsResponse:
    return ModelAnalysisMetricsResponse(
        model_id=item.model_id,
        analyses=item.analyses,
        completed=item.completed,
        failed=item.failed,
        total_ms_p50=item.total_ms_p50,
        total_ms_p95=item.total_ms_p95,
        total_ms_p99=item.total_ms_p99,
        prompt_tokens_avg=item.prompt_tokens_avg,
        output_tokens_avg=item.output_tokens_avg,
        load_ms_avg=item.load_ms_avg,
        failure_rate=item.failure_rate,
        failure_rates=item.failure_rates,
        reuse_rate=item.reuse_rate,
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
        role_family=item.role_family,
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


def _metrics_window_response(
    window: SourceMetricsWindow,
) -> SourceMetricsWindowResponse:
    return SourceMetricsWindowResponse(
        window=window.window,
        since=window.since,
        until=window.until,
        sources=[_source_metrics_response(source) for source in window.sources],
    )


def _source_metrics_response(source: SourceWindowMetrics) -> SourceMetricsResponse:
    return SourceMetricsResponse(
        source_definition_id=source.source_definition_id,
        name=source.name,
        source_type=source.source_type,
        enabled=source.enabled,
        schedule=source.schedule,
        coverage_state=source.coverage_state,
        runs=source.runs,
        runs_succeeded=source.runs_succeeded,
        runs_partial=source.runs_partial,
        runs_failed=source.runs_failed,
        items_seen=source.items_seen,
        items_persisted=source.items_persisted,
        items_skipped=source.items_skipped,
        items_invalid=source.items_invalid,
        latency_p95_seconds=source.latency_p95_seconds,
        error_rate=source.error_rate,
        dedupe_rate=source.dedupe_rate,
        has_runs=source.has_runs,
        errors_by_code=source.errors_by_code,
        seniority=SeniorityDistributionResponse(
            counts=source.seniority.counts,
            percentages=source.seniority.percentages,
            known=source.seniority.known,
            unknown=source.seniority.unknown,
            total=source.seniority.total,
            mapping_versions=source.seniority.mapping_versions,
            evidence=source.seniority.evidence,
        ),
        incident_open=source.incident_open,
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
        precision_percent=(
            str(summary.precision_percent * 100)
            if summary.precision_percent is not None
            else None
        ),
        precision_marked_count=summary.precision_marked_count,
        companies_covered=summary.companies_covered,
        companies_with_ats=summary.companies_with_ats,
    )


def _search_metrics_response(report: SearchMetricsReport) -> SearchMetricsResponse:
    coverage = report.coverage
    precision = report.precision
    return SearchMetricsResponse(
        window_days=report.window_days,
        generated_at=report.generated_at,
        coverage=CoverageMetricsResponse(
            window_days=coverage.window_days,
            runs=coverage.runs,
            items_seen=coverage.items_seen,
            items_persisted=coverage.items_persisted,
            items_duplicate=coverage.items_duplicate,
            items_invalid=coverage.items_invalid,
            new_opportunities=coverage.new_opportunities,
            companies_covered=coverage.companies_covered,
            companies_with_ats=coverage.companies_with_ats,
            seniority_unknown_rate=(
                str(coverage.seniority_unknown_rate)
                if coverage.seniority_unknown_rate is not None
                else None
            ),
            role_family_unknown_rate=(
                str(coverage.role_family_unknown_rate)
                if coverage.role_family_unknown_rate is not None
                else None
            ),
            by_source=[
                SourceCoverageMetricResponse(
                    source_definition_id=item.source_definition_id,
                    name=item.name,
                    runs=item.runs,
                    items_seen=item.items_seen,
                    items_persisted=item.items_persisted,
                    items_duplicate=item.items_duplicate,
                    items_invalid=item.items_invalid,
                    new_opportunities=item.new_opportunities,
                )
                for item in coverage.by_source
            ],
        ),
        precision=PrecisionMetricsResponse(
            sample_size=precision.sample_size,
            marked_count=precision.marked_count,
            relevant_count=precision.relevant_count,
            precision=(
                str(precision.precision) if precision.precision is not None else None
            ),
        ),
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
