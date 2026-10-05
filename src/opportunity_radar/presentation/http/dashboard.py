"""HTTP contract for the Overview and the Opportunity Inbox."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.analysis_metrics import (
    AnalysisMetricsWindow,
    ModelAnalysisMetrics,
    analysis_metrics,
)
from opportunity_radar.dashboard.funnel import funnel_report
from opportunity_radar.dashboard.metrics import (
    METRIC_WINDOWS,
    SourceMetricsWindow,
    SourceWindowMetrics,
    source_metrics,
)
from opportunity_radar.dashboard.queries import (
    FAILING_RUN_STATUSES,
    CompanyCoverageFunnel,
    InboxItem,
    InboxOrder,
    InboxQuery,
    OverviewSummary,
    SearchMetricsReport,
    SourceCoverageReport,
    SourceHealth,
    UsefulYieldMetric,
    company_coverage_funnel,
    list_opportunity_inbox,
    list_source_health,
    search_metrics,
    source_coverage_report,
    summarize_overview,
    useful_yield_metrics,
)
from opportunity_radar.dashboard.saved_searches import (
    SavedSearch,
    SavedSearchNotFoundError,
    create_saved_search,
    delete_saved_search,
    list_saved_searches,
    new_count,
    open_saved_search,
    rename_saved_search,
)
from opportunity_radar.matching.analysis import SemanticAnalysisPort
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.operations.collection_alarm import collection_gap_report
from opportunity_radar.opportunities.domain import (
    DEFAULT_RECENCY_WINDOW_DAYS,
    OpportunityStatus,
    Seniority,
    WorkMode,
)
from opportunity_radar.platform.ai.config import ai_status
from opportunity_radar.platform.ai.metrics import ModelAIMetrics, ai_metrics
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.presentation.http.dependencies import get_analysis_adapter, get_session
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
    #: Cards F20-61/F48-16: `published_at ?? source_updated_at ?? first_seen_at`
    #: (never a fabricated real date).
    recency_effective_date: datetime | None
    #: `True` when `recency_effective_date` is not the source's `published_at`, never
    #: presented as a real publication date without this flag.
    date_is_estimated: bool
    #: `published`, `updated` or `first_seen` (persisted `recency_basis`).
    recency_basis: str
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
    has_pending_duplicate: bool
    #: Card F20-54: startup evidence summary; `None` when the company has none.
    startup_strength: str | None = None
    startup_batch: str | None = None
    #: Card F48-10: other postings of the same company/title/source folded into this row.
    sibling_count: int = 0


class InboxPageResponse(BaseModel):
    items: list[InboxItemResponse]
    total: int
    offset: int
    limit: int
    order: str
    off_filter_count: int


class SavedSearchCreateRequest(BaseModel):
    name: str
    term: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)


class SavedSearchPatchRequest(BaseModel):
    name: str | None = None
    open: bool = False


class SavedSearchResponse(BaseModel):
    id: UUID
    name: str
    term: str | None
    filters: dict[str, Any]
    last_opened_at: datetime | None
    created_at: datetime


class SavedSearchNewCountResponse(BaseModel):
    new_count: int


class SourceHealthResponse(BaseModel):
    source_definition_id: UUID
    name: str
    source_type: str
    enabled: bool
    evidence_status: str
    terms_reviewed: bool
    collector_local_tested: bool
    schedule: str | None
    version: int
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
    last_run_bytes_received: int | None = None
    last_run_newest_item_age_seconds: int | None = None
    #: F48-07: scheduled but no scheduled run in more than twice its cadence.
    collection_overdue: bool = False
    seniority_counts: dict[str, int]


class CollectionGapResponse(BaseModel):
    """F48-07: `alarming` is the one field a screen needs; the rest says why."""

    alarming: bool
    global_overdue: bool
    factor: float
    evaluated_sources: int
    global_cadence_seconds: float | None
    last_scheduled_run_at: datetime | None
    overdue_sources: int


class FunnelStageResponse(BaseModel):
    key: str
    label: str
    count: int
    lost: int | None


class RatioResponse(BaseModel):
    count: int
    total: int
    ratio: float | None


class NorthStarResponse(BaseModel):
    role_families: list[str]
    proxy: bool
    stock: int
    new_in_window: int
    window_hours: int
    stack: dict[str, int]


class FunnelReportResponse(BaseModel):
    generated_at: datetime
    stages: list[FunnelStageResponse]
    north_star: NorthStarResponse
    guards: dict[str, RatioResponse]
    forbidden_hosts_touched: int
    not_measured: list[str]


class SourceHealthListResponse(BaseModel):
    items: list[SourceHealthResponse]
    total: int
    failing: int
    collection_gap: CollectionGapResponse | None = None


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
    #: F20-39: revisits in this window that confirmed presence without re-normalizing or
    #: re-running AI, because the raw evidence matched what was already held.
    presence_confirmed_without_reprocessing: int


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


class ModelAIMetricsResponse(BaseModel):
    model: str
    requests: int
    success_rate: float | None
    rate_limited_rate: float | None
    fallback_rate: float | None
    latency_ms_avg: float | None
    latency_ms_p95: float | None
    prompt_tokens: int
    completion_tokens: int
    json_valid_rate: float | None
    breaker: str
    day_requests_used: int
    day_requests_limit: int | None
    day_tokens_used: int
    day_tokens_limit: int | None


class AIMetricsResponse(BaseModel):
    state: str
    window_hours: int
    by_model: list[ModelAIMetricsResponse]
    cache_hit_rate: float | None


class AnalysisMetricsReportResponse(BaseModel):
    generated_at: datetime
    current_model: str
    pending: int
    windows: list[AnalysisMetricsWindowResponse]
    ai: AIMetricsResponse


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


class CompanyFunnelStageResponse(BaseModel):
    stage: str
    companies: int
    of_previous: int | None


class CompanyCoverageFunnelResponse(BaseModel):
    window_days: int
    generated_at: datetime
    canonical_companies_total: int
    stages: list[CompanyFunnelStageResponse]
    enabled_but_unhealthy: int


class UsefulYieldMetricResponse(BaseModel):
    window_days: int
    requests: int
    new_unique_opportunities: int
    judged_opportunities: int
    judged_relevant: int | None
    judgement_rate: str | None
    yield_per_100_requests: str | None
    discovery_delay_p50_seconds: float | None
    discovery_delay_p95_seconds: float | None
    contribution_by_source: dict[UUID, int]


class SearchMetricsResponse(BaseModel):
    window_days: int
    generated_at: datetime
    coverage: CoverageMetricsResponse
    precision: PrecisionMetricsResponse
    company_coverage_funnel: CompanyCoverageFunnelResponse
    useful_yield: UsefulYieldMetricResponse


def _saved_search_response(saved_search: SavedSearch) -> SavedSearchResponse:
    return SavedSearchResponse(
        id=saved_search.id,
        name=saved_search.name,
        term=saved_search.term,
        filters=saved_search.filters,
        last_opened_at=saved_search.last_opened_at,
        created_at=saved_search.created_at,
    )


@router.post(
    "/saved-searches",
    response_model=SavedSearchResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_saved_search(
    request: SavedSearchCreateRequest,
    session: Session = Depends(get_session),
) -> SavedSearchResponse:
    return _saved_search_response(
        create_saved_search(
            session,
            name=request.name,
            term=request.term,
            filters=request.filters,
        )
    )


@router.get("/saved-searches", response_model=list[SavedSearchResponse])
def get_saved_searches(session: Session = Depends(get_session)) -> list[SavedSearchResponse]:
    return [_saved_search_response(item) for item in list_saved_searches(session)]


@router.patch("/saved-searches/{saved_search_id}", response_model=SavedSearchResponse)
def patch_saved_search(
    saved_search_id: UUID,
    request: SavedSearchPatchRequest,
    session: Session = Depends(get_session),
) -> SavedSearchResponse:
    if request.name is None and not request.open:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    try:
        saved_search = (
            rename_saved_search(session, saved_search_id, name=request.name)
            if request.name is not None
            else None
        )
        if request.open:
            saved_search = open_saved_search(session, saved_search_id)
        if saved_search is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
    except SavedSearchNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    return _saved_search_response(saved_search)


@router.delete("/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_saved_search(
    saved_search_id: UUID,
    session: Session = Depends(get_session),
) -> Response:
    try:
        delete_saved_search(session, saved_search_id)
    except SavedSearchNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/saved-searches/{saved_search_id}/new-count",
    response_model=SavedSearchNewCountResponse,
)
def get_saved_search_new_count(
    saved_search_id: UUID,
    session: Session = Depends(get_session),
) -> SavedSearchNewCountResponse:
    saved_searches = {item.id: item for item in list_saved_searches(session)}
    saved_search = saved_searches.get(saved_search_id)
    if saved_search is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return SavedSearchNewCountResponse(new_count=new_count(session, saved_search))


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
    #: Card F20-61: the server's own default, absent this parameter, is filtered.
    #: The client's "mostrar tudo" toggle passes `only_recent=false`.
    only_recent: bool = Query(default=True),
    #: Card F48-16: window over the reference date (default 30 days; the "Novas" lens
    #: sends 14).
    recency_window_days: int = Query(default=DEFAULT_RECENCY_WINDOW_DAYS, ge=1, le=365),
    #: Card F48-16 lens "Abertas na fonte": seen in the last complete run of the
    #: occurrence's source, no date limit.
    open_at_source: bool = False,
    #: Card F20-54: only companies with at least one startup-evidence row.
    only_startups: bool = False,
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
            only_recent=only_recent,
            recency_window_days=recency_window_days,
            open_at_source=open_at_source,
            only_startups=only_startups,
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
    status_filter: Literal["proposed"] | None = Query(default=None, alias="status"),
    session: Session = Depends(get_session),
) -> SourceHealthListResponse:
    """Named `/source-health` rather than `/sources/health`: that path is a source id."""
    items = list_source_health(session, only_failing=only_failing, status=status_filter)
    failing = sum(1 for item in items if item.last_run_status in FAILING_RUN_STATUSES)
    gap = collection_gap_report(session)
    overdue = gap.overdue_source_ids
    return SourceHealthListResponse(
        items=[
            _source_response(item, overdue=item.source_definition_id in overdue)
            for item in items
        ],
        total=len(items),
        failing=failing,
        collection_gap=CollectionGapResponse(
            alarming=gap.alarming,
            global_overdue=gap.global_overdue,
            factor=gap.factor,
            evaluated_sources=gap.evaluated_sources,
            global_cadence_seconds=gap.global_cadence_seconds,
            last_scheduled_run_at=gap.last_scheduled_run_at,
            overdue_sources=len(overdue),
        ),
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


@router.get("/funnel-metrics", response_model=FunnelReportResponse)
def get_funnel_metrics(session: Session = Depends(get_session)) -> FunnelReportResponse:
    """F48-06: the SPEC 48 funnel, the north-star and its guards, from persisted rows."""
    try:
        active = ProfileService(session).get_active()
        families = tuple(active.snapshot.preferences.target_role_families)
    except ProfileNotFoundError:
        families = ()
    report = funnel_report(session, target_role_families=families)
    return FunnelReportResponse(
        generated_at=report.generated_at,
        stages=[
            FunnelStageResponse(key=item.key, label=item.label, count=item.count, lost=item.lost)
            for item in report.stages
        ],
        north_star=NorthStarResponse(
            role_families=list(report.north_star.role_families),
            proxy=report.north_star.proxy,
            stock=report.north_star.stock,
            new_in_window=report.north_star.new_in_window,
            window_hours=report.north_star.window_hours,
            stack=dict(report.north_star.stack),
        ),
        guards={
            name: RatioResponse(count=value.count, total=value.total, ratio=value.ratio)
            for name, value in report.guards.items()
        },
        forbidden_hosts_touched=report.forbidden_hosts_touched,
        not_measured=list(report.not_measured),
    )


@router.get("/analysis-metrics", response_model=AnalysisMetricsReportResponse)
def get_analysis_metrics(
    window: str | None = Query(
        default=None, description="Restrict the answer to one window: 24h or 7d."
    ),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    adapter: SemanticAnalysisPort = Depends(get_analysis_adapter),
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
        current_model=settings.groq_reasoning_model,
        pending=pending,
        windows=selected,
    )
    return AnalysisMetricsReportResponse(
        generated_at=report.generated_at,
        current_model=report.current_model,
        pending=report.pending,
        windows=[_analysis_window_response(item) for item in report.windows],
        ai=_ai_metrics_response(session, settings, adapter),
    )


def _ai_metrics_response(
    session: Session, settings: Settings, adapter: SemanticAnalysisPort
) -> AIMetricsResponse:
    """Card F20-20: the block never removes or renames an existing metrics field."""
    engine = cast(Engine, session.get_bind())
    report = ai_metrics(
        engine,
        state=ai_status(settings).value,
        guard=getattr(adapter, "quota_guard", None),
        breaker=getattr(adapter, "breaker", None),
        day_requests_limit=settings.ai_daily_requests_soft_limit,
        day_tokens_limit=settings.ai_daily_tokens_soft_limit,
    )
    return AIMetricsResponse(
        state=report.state,
        window_hours=report.window_hours,
        cache_hit_rate=report.cache_hit_rate,
        by_model=[_model_ai_metrics_response(item) for item in report.by_model],
    )


def _model_ai_metrics_response(item: ModelAIMetrics) -> ModelAIMetricsResponse:
    return ModelAIMetricsResponse(
        model=item.model,
        requests=item.requests,
        success_rate=item.success_rate,
        rate_limited_rate=item.rate_limited_rate,
        fallback_rate=item.fallback_rate,
        latency_ms_avg=item.latency_ms_avg,
        latency_ms_p95=item.latency_ms_p95,
        prompt_tokens=item.prompt_tokens,
        completion_tokens=item.completion_tokens,
        json_valid_rate=item.json_valid_rate,
        breaker=item.breaker,
        day_requests_used=item.day_requests_used,
        day_requests_limit=item.day_requests_limit,
        day_tokens_used=item.day_tokens_used,
        day_tokens_limit=item.day_tokens_limit,
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
    return _search_metrics_response(
        report,
        company_coverage_funnel(session, window_days=window_days),
        useful_yield_metrics(session, window_days=window_days),
    )


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
        recency_effective_date=item.recency_effective_date,
        date_is_estimated=item.date_is_estimated,
        recency_basis=item.recency_basis,
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
        has_pending_duplicate=item.has_pending_duplicate,
        startup_strength=item.startup_strength,
        startup_batch=item.startup_batch,
        sibling_count=item.sibling_count,
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
        presence_confirmed_without_reprocessing=source.presence_confirmed_without_reprocessing,
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


def _search_metrics_response(
    report: SearchMetricsReport,
    funnel: CompanyCoverageFunnel,
    useful_yield: UsefulYieldMetric,
) -> SearchMetricsResponse:
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
        company_coverage_funnel=CompanyCoverageFunnelResponse(
            window_days=funnel.window_days,
            generated_at=funnel.generated_at,
            canonical_companies_total=funnel.canonical_companies_total,
            stages=[
                CompanyFunnelStageResponse(
                    stage=item.stage,
                    companies=item.companies,
                    of_previous=item.of_previous,
                )
                for item in funnel.stages
            ],
            enabled_but_unhealthy=funnel.enabled_but_unhealthy,
        ),
        useful_yield=UsefulYieldMetricResponse(
            window_days=useful_yield.window_days,
            requests=useful_yield.requests,
            new_unique_opportunities=useful_yield.new_unique_opportunities,
            judged_opportunities=useful_yield.judged_opportunities,
            judged_relevant=useful_yield.judged_relevant,
            judgement_rate=(
                str(useful_yield.judgement_rate)
                if useful_yield.judgement_rate is not None
                else None
            ),
            yield_per_100_requests=(
                str(useful_yield.yield_per_100_requests)
                if useful_yield.yield_per_100_requests is not None
                else None
            ),
            discovery_delay_p50_seconds=useful_yield.discovery_delay_p50_seconds,
            discovery_delay_p95_seconds=useful_yield.discovery_delay_p95_seconds,
            contribution_by_source=useful_yield.contribution_by_source,
        ),
    )


def _source_response(source: SourceHealth, *, overdue: bool = False) -> SourceHealthResponse:
    return SourceHealthResponse(
        source_definition_id=source.source_definition_id,
        name=source.name,
        source_type=source.source_type,
        enabled=source.enabled,
        evidence_status=source.evidence_status,
        terms_reviewed=source.terms_reviewed,
        collector_local_tested=source.collector_local_tested,
        schedule=source.schedule,
        version=source.version,
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
        last_run_bytes_received=source.last_run_bytes_received,
        last_run_newest_item_age_seconds=source.last_run_newest_item_age_seconds,
        collection_overdue=overdue,
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
