"""Query services behind the Overview and the Opportunity Inbox.

Both screens need the same join that no single aggregate owns: an opportunity, the most
recent assessment of it, the most recent semantic analysis of that assessment, and the
company that published it. Building it here keeps the repositories of each context about
one aggregate, as section 8.2 of docs/06-estrutura-projeto-mvp.md requires.

Every row exposes the assessment as optional. An opportunity that was never evaluated is
still in the inbox: hiding it would make the screen quietly disagree with the catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from functools import reduce
from typing import Any
from uuid import UUID

from sqlalchemy import Select, case, func, literal, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.dashboard.search_synonyms import synonym_variants
from opportunity_radar.matching import currency
from opportunity_radar.matching.models import MatchAnalysisModel, MatchAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityCompensationModel,
    OpportunityModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
)
from opportunity_radar.pipeline.models import ApplicationProcessModel

NEW_OPPORTUNITY_WINDOW_DAYS = 7
FOLLOW_UP_WINDOW_DAYS = 7
FAILING_RUN_STATUSES = ("FAILED", "PARTIAL")

# Ordering only. The catalogue stores priority in lower case; matching uppercases it.
_PRIORITY_RANK = {"high": 3, "normal": 2, "low": 1, "blocked": 0}


class InboxOrder(StrEnum):
    PRIORITY = "priority"
    RECENCY = "recency"
    SCORE = "score"


@dataclass(frozen=True, slots=True)
class InboxItem:
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
    assessment_id: UUID | None = None
    assessment_opportunity_version: int | None = None
    assessment_profile_version_id: UUID | None = None
    current_profile_version_id: UUID | None = None
    verdict: str | None = None
    eligibility: str | None = None
    score: Decimal | None = None
    confidence: Decimal | None = None
    rules_version: str | None = None
    is_stale: bool | None = None
    assessed_at: datetime | None = None
    analysis_status: str | None = None
    analysis_recommended_review: bool | None = None
    analysis_summary: str | None = None
    application_id: UUID | None = None
    application_stage: str | None = None
    application_next_action_at: datetime | None = None

    @property
    def applied(self) -> bool:
        """Whether an active candidacy exists. A closed one leaves the opportunity open
        to being applied to again, so it does not count."""
        return self.application_id is not None


@dataclass(frozen=True, slots=True)
class InboxPage:
    items: tuple[InboxItem, ...]
    total: int
    offset: int
    limit: int
    #: Opportunities the same filters would show without the area filter. 0 when no
    #: `role_families` filter is active, so a client never subtracts a filter it did not
    #: apply. Never a count of hidden rows: they stay one click away, never deleted.
    off_filter_count: int = 0


@dataclass(frozen=True, slots=True)
class InboxQuery:
    """Filters from section 50 of the roadmap, minus the ones phase 8 has to enable."""

    verdicts: tuple[str, ...] = ()
    minimum_score: Decimal | None = None
    company_id: UUID | None = None
    work_mode: str | None = None
    lifecycle_status: str | None = None
    published_after: datetime | None = None
    only_assessed: bool = False
    applied: bool | None = None
    search: str | None = None
    #: `role-family-v1` codes. Empty means every area — never a filter that hides rows.
    role_families: tuple[str, ...] = ()
    profile_version_id: UUID | None = None
    #: Empty means every seniority — an unknown/blank value is never an implicit
    #: exclusion (SPEC 37, "Contrato de consulta").
    seniorities: tuple[str, ...] = ()
    #: Compensation range, compared as-is against `OpportunityCompensationModel`
    #: amounts. No currency conversion: mixing currencies in one query compares raw
    #: numbers, a known limitation until a conversion service exists for filtering
    #: (`matching.currency` only converts for scoring today).
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    #: `SourceDefinitionModel` ids. Matches on the opportunity's occurrences (`EXISTS`),
    #: never a join — an opportunity with several matching sources still appears once
    #: (SPEC 37, "Contrato de consulta": "fonte filtra ocorrências, não duplica").
    source_definition_ids: tuple[UUID, ...] = ()
    order: InboxOrder = InboxOrder.PRIORITY
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True, slots=True)
class SourceHealth:
    """A source plus the outcome of its last run, which is what the screen decides on."""

    source_definition_id: UUID
    name: str
    source_type: str
    enabled: bool
    last_run_status: str | None
    last_run_finished_at: datetime | None
    last_run_error: str | None
    evidence_status: str = "unverified"
    terms_reviewed: bool = False
    collector_local_tested: bool = False
    schedule: str | None = None
    last_run_id: UUID | None = None
    last_run_started_at: datetime | None = None
    last_run_error_code: str | None = None
    last_run_items_seen: int | None = None
    last_run_items_persisted: int | None = None
    last_run_items_skipped: int | None = None
    last_run_items_invalid: int | None = None
    seniority_counts: dict[str, int] = field(default_factory=dict)

    @property
    def last_run_duration_seconds(self) -> float | None:
        if self.last_run_started_at is None or self.last_run_finished_at is None:
            return None
        return (self.last_run_finished_at - self.last_run_started_at).total_seconds()


@dataclass(frozen=True, slots=True)
class SourceCoverage:
    source_definition_id: UUID
    name: str
    state: str
    run_status: str | None
    raw_items: int


@dataclass(frozen=True, slots=True)
class SourceCoverageReport:
    correlation_id: str | None
    catalog_companies: int
    catalog_source_records: int
    proposed_sources: int
    homologated_sources: int
    enabled_sources: int
    eligible_sources: int
    sources: tuple[SourceCoverage, ...]


@dataclass(frozen=True, slots=True)
class OverviewSummary:
    opportunities_total: int
    opportunities_active: int
    new_opportunities: int
    assessed_opportunities: int
    verdict_counts: dict[str, int] = field(default_factory=dict)
    analyses_degraded: int = 0
    sources_total: int = 0
    sources_enabled: int = 0
    sources_failing: int = 0
    failing_sources: tuple[SourceHealth, ...] = ()
    pending_normalizations: int = 0
    new_opportunity_window_days: int = NEW_OPPORTUNITY_WINDOW_DAYS
    applications_active: int = 0
    applications_by_stage: dict[str, int] = field(default_factory=dict)
    #: Active applications whose next action is already due or falls inside the window.
    follow_ups_due: int = 0
    follow_up_window_days: int = FOLLOW_UP_WINDOW_DAYS
    #: Support line data for the "Acervo" block (F17-01). `precision_percent` is `None`
    #: when there are not enough marks to compute it — never a frail number.
    precision_percent: Decimal | None = None
    precision_marked_count: int = 0
    companies_covered: int = 0
    companies_with_ats: int = 0


#: Source types with a collector registered (`registry.py`), i.e. an ATS the radar can
#: actually collect from. "Empresas com ATS identificado" per the SPEC notes.
ATS_COLLECTOR_SOURCE_TYPES = ("ashby", "greenhouse", "lever")
#: Number of top Inbox rows, in the default order, that the precision report samples.
PRECISION_SAMPLE_SIZE = 50


@dataclass(frozen=True, slots=True)
class SourceCoverageMetric:
    source_definition_id: UUID
    name: str
    runs: int
    items_seen: int
    items_persisted: int
    items_duplicate: int
    items_invalid: int
    new_opportunities: int


@dataclass(frozen=True, slots=True)
class CoverageMetrics:
    window_days: int
    runs: int
    items_seen: int
    items_persisted: int
    items_duplicate: int
    items_invalid: int
    new_opportunities: int
    companies_covered: int
    companies_with_ats: int
    seniority_unknown_rate: Decimal | None
    #: Rate of `role_family == 'UNKNOWN'` in the whole catalogue. Card F17-02's acceptance
    #: is < 10%, measured here rather than fabricated.
    role_family_unknown_rate: Decimal | None
    by_source: tuple[SourceCoverageMetric, ...] = ()


@dataclass(frozen=True, slots=True)
class PrecisionMetrics:
    """Precision of the top `sample_size` Inbox rows, computed only over marked ones."""

    sample_size: int
    marked_count: int
    relevant_count: int
    precision: Decimal | None


@dataclass(frozen=True, slots=True)
class SearchMetricsReport:
    window_days: int
    generated_at: datetime
    coverage: CoverageMetrics
    precision: PrecisionMetrics


def _latest_assessments(profile_version_id: UUID | None) -> Any:
    current = currency.is_current_assessment(
        MatchAssessmentModel.__table__, rules_version=RULES_VERSION
    )
    ranked = select(
        MatchAssessmentModel.id.label("assessment_id"),
        MatchAssessmentModel.opportunity_id.label("opportunity_id"),
        MatchAssessmentModel.opportunity_version.label("assessment_opportunity_version"),
        MatchAssessmentModel.profile_version_id.label("assessment_profile_version_id"),
        currency.active_profile_version_id().label("current_profile_version_id"),
        MatchAssessmentModel.verdict.label("verdict"),
        MatchAssessmentModel.eligibility.label("eligibility"),
        MatchAssessmentModel.score.label("score"),
        MatchAssessmentModel.confidence.label("confidence"),
        MatchAssessmentModel.rules_version.label("rules_version"),
        (~current).label("is_stale"),
        MatchAssessmentModel.assessed_at.label("assessed_at"),
        func.row_number()
        .over(
            partition_by=MatchAssessmentModel.opportunity_id,
            order_by=(
                current.desc(),
                MatchAssessmentModel.assessed_at.desc(),
                MatchAssessmentModel.id.desc(),
            ),
        )
        .label("position"),
    )
    if profile_version_id is not None:
        ranked = ranked.where(
            MatchAssessmentModel.profile_version_id == profile_version_id
        )
    ranked = ranked.join(
        OpportunityModel,
        OpportunityModel.id == MatchAssessmentModel.opportunity_id,
    )
    numbered = ranked.subquery("ranked_assessments")
    return select(numbered).where(numbered.c.position == 1).subquery("latest_assessment")


def _latest_analyses() -> Any:
    ranked = select(
        MatchAnalysisModel.assessment_id.label("assessment_id"),
        MatchAnalysisModel.status.label("status"),
        MatchAnalysisModel.recommended_review.label("recommended_review"),
        MatchAnalysisModel.summary.label("summary"),
        func.row_number()
        .over(
            partition_by=MatchAnalysisModel.assessment_id,
            order_by=(
                MatchAnalysisModel.analyzed_at.desc(),
                MatchAnalysisModel.id.desc(),
            ),
        )
        .label("position"),
    ).subquery("ranked_analyses")
    return select(ranked).where(ranked.c.position == 1).subquery("latest_analysis")


def _active_applications() -> Any:
    """At most one active application per opportunity and profile, enforced in the DB."""
    return (
        select(
            ApplicationProcessModel.id.label("application_id"),
            ApplicationProcessModel.opportunity_id.label("opportunity_id"),
            ApplicationProcessModel.current_stage.label("current_stage"),
            ApplicationProcessModel.next_action_at.label("next_action_at"),
        )
        .where(ApplicationProcessModel.status == "ACTIVE")
        .subquery("active_application")
    )


def _priority_rank() -> Any:
    return case(
        _PRIORITY_RANK,
        value=func.lower(func.coalesce(Company.priority, literal("normal"))),
        else_=2,
    )


def _inbox_statement(query: InboxQuery) -> tuple[Select[Any], Any, Any]:
    assessments = _latest_assessments(query.profile_version_id)
    analyses = _latest_analyses()
    applications = _active_applications()
    statement = (
        select(
            OpportunityModel.id,
            OpportunityModel.canonical_title,
            OpportunityModel.canonical_company_id,
            OpportunityModel.company_name,
            Company.priority,
            OpportunityModel.location_text,
            OpportunityModel.work_mode,
            OpportunityModel.seniority,
            OpportunityModel.contract_type,
            OpportunityModel.lifecycle_status,
            OpportunityModel.role_family,
            OpportunityModel.published_at,
            OpportunityModel.version,
            assessments.c.assessment_id,
            assessments.c.assessment_opportunity_version,
            assessments.c.assessment_profile_version_id,
            assessments.c.current_profile_version_id,
            assessments.c.verdict,
            assessments.c.eligibility,
            assessments.c.score,
            assessments.c.confidence,
            assessments.c.rules_version,
            assessments.c.is_stale,
            assessments.c.assessed_at,
            analyses.c.status,
            analyses.c.recommended_review,
            analyses.c.summary,
            applications.c.application_id,
            applications.c.current_stage,
            applications.c.next_action_at,
        )
        .select_from(OpportunityModel)
        .outerjoin(assessments, assessments.c.opportunity_id == OpportunityModel.id)
        .outerjoin(Company, Company.id == OpportunityModel.canonical_company_id)
        .outerjoin(analyses, analyses.c.assessment_id == assessments.c.assessment_id)
        .outerjoin(applications, applications.c.opportunity_id == OpportunityModel.id)
    )
    return (
        statement.where(*_inbox_filters(query, assessments, applications)),
        assessments,
        analyses,
    )


def _inbox_filters(query: InboxQuery, assessments: Any, applications: Any) -> list[Any]:
    filters: list[Any] = []
    if query.verdicts:
        filters.append(assessments.c.verdict.in_(query.verdicts))
    if query.minimum_score is not None:
        filters.append(assessments.c.score >= query.minimum_score)
    if query.only_assessed:
        filters.append(assessments.c.assessment_id.is_not(None))
    if query.applied is not None:
        filters.append(
            applications.c.application_id.is_not(None)
            if query.applied
            else applications.c.application_id.is_(None)
        )
    if query.company_id is not None:
        filters.append(OpportunityModel.canonical_company_id == query.company_id)
    if query.work_mode:
        filters.append(OpportunityModel.work_mode == query.work_mode)
    if query.lifecycle_status:
        filters.append(OpportunityModel.lifecycle_status == query.lifecycle_status)
    if query.role_families:
        filters.append(OpportunityModel.role_family.in_(query.role_families))
    if query.published_after is not None:
        filters.append(OpportunityModel.published_at >= query.published_after)
    if query.seniorities:
        filters.append(OpportunityModel.seniority.in_(query.seniorities))
    if query.salary_min is not None or query.salary_max is not None:
        compensation_conditions = [
            OpportunityCompensationModel.opportunity_id == OpportunityModel.id
        ]
        if query.salary_min is not None:
            compensation_conditions.append(
                OpportunityCompensationModel.amount_max.is_(None)
                | (OpportunityCompensationModel.amount_max >= query.salary_min)
            )
        if query.salary_max is not None:
            compensation_conditions.append(
                OpportunityCompensationModel.amount_min.is_(None)
                | (OpportunityCompensationModel.amount_min <= query.salary_max)
            )
        filters.append(
            select(OpportunityCompensationModel.id)
            .where(*compensation_conditions)
            .exists()
        )
    if query.source_definition_ids:
        filters.append(
            select(SourceOccurrenceModel.id)
            .where(
                SourceOccurrenceModel.opportunity_id == OpportunityModel.id,
                SourceOccurrenceModel.source_definition_id.in_(
                    query.source_definition_ids
                ),
            )
            .exists()
        )
    term = query.search.strip() if query.search else ""
    if term:
        filters.append(OpportunityModel.search_document.op("@@")(_search_tsquery(term)))
    return filters


_DICTIONARIES = ("portuguese", "english")


def _search_tsquery(term: str) -> Any:
    """`websearch_to_tsquery` over both dictionaries, ORed across synonym variants.

    Quoted phrases, `AND`/`OR`/`-negation` in `term` come from `websearch_to_tsquery`
    itself; `synonym_variants` only substitutes plain tokens before parsing, so those
    semantics survive (SPEC 37, "Contrato de consulta").
    """
    expressions: list[Any] = [
        func.websearch_to_tsquery(dictionary, variant)
        for variant in synonym_variants(term)
        for dictionary in _DICTIONARIES
    ]
    return reduce(lambda left, right: left.op("||")(right), expressions)


def _search_rank(term: str) -> Any:
    return func.ts_rank_cd(OpportunityModel.search_document, _search_tsquery(term))


def _inbox_ordering(order: InboxOrder, assessments: Any, search_term: str = "") -> list[Any]:
    recency = OpportunityModel.published_at.desc().nulls_last()
    score = assessments.c.score.desc().nulls_last()
    if search_term:
        # Contract: rank when there is a term; tie-break by recency then id so
        # pagination never repeats or drops a row on a tie (SPEC 37, "Contrato de
        # consulta").
        return [_search_rank(search_term).desc(), recency, OpportunityModel.id]
    if order is InboxOrder.RECENCY:
        return [recency, score, OpportunityModel.id]
    if order is InboxOrder.SCORE:
        return [score, recency, OpportunityModel.id]
    return [_priority_rank().desc(), score, recency, OpportunityModel.id]


def list_opportunity_inbox(session: Session, query: InboxQuery) -> InboxPage:
    statement, assessments, _ = _inbox_statement(query)
    total = (
        session.scalar(select(func.count()).select_from(statement.subquery("inbox"))) or 0
    )
    rows = session.execute(
        statement.order_by(
            *_inbox_ordering(
                query.order, assessments, (query.search or "").strip()
            )
        )
        .offset(query.offset)
        .limit(query.limit)
    ).all()
    off_filter_count = 0
    if query.role_families:
        broader_statement, _, _ = _inbox_statement(replace(query, role_families=()))
        broader_total = (
            session.scalar(
                select(func.count()).select_from(broader_statement.subquery("inbox_all"))
            )
            or 0
        )
        off_filter_count = max(broader_total - total, 0)
    return InboxPage(
        items=tuple(_inbox_item(row) for row in rows),
        total=total,
        offset=query.offset,
        limit=query.limit,
        off_filter_count=off_filter_count,
    )


def _inbox_item(row: Any) -> InboxItem:
    return InboxItem(
        opportunity_id=row[0],
        title=row[1],
        company_id=row[2],
        company_name=row[3],
        company_priority=row[4].upper() if row[4] else None,
        location=row[5],
        work_mode=row[6],
        seniority=row[7],
        contract_type=row[8],
        lifecycle_status=row[9],
        role_family=row[10],
        published_at=row[11],
        opportunity_version=row[12],
        assessment_id=row[13],
        assessment_opportunity_version=row[14],
        assessment_profile_version_id=row[15],
        current_profile_version_id=row[16],
        verdict=row[17],
        eligibility=row[18],
        score=row[19],
        confidence=row[20],
        rules_version=row[21],
        is_stale=row[22],
        assessed_at=row[23],
        analysis_status=row[24],
        analysis_recommended_review=row[25],
        analysis_summary=row[26],
        application_id=row[27],
        application_stage=row[28],
        application_next_action_at=row[29],
    )


def summarize_overview(
    session: Session,
    *,
    profile_version_id: UUID | None = None,
    now: datetime | None = None,
) -> OverviewSummary:
    reference = now or datetime.now(UTC)
    since = reference - timedelta(days=NEW_OPPORTUNITY_WINDOW_DAYS)
    assessments = _latest_assessments(profile_version_id)
    analyses = _latest_analyses()

    verdict_rows = session.execute(
        select(assessments.c.verdict, func.count()).group_by(assessments.c.verdict)
    ).all()
    verdict_counts = {str(verdict): int(count) for verdict, count in verdict_rows}

    degraded = session.scalar(
        select(func.count())
        .select_from(analyses)
        .where(analyses.c.status != "AI_COMPLETED")
    )
    failing = list_source_health(session, only_failing=True)
    stage_rows = session.execute(
        select(ApplicationProcessModel.current_stage, func.count())
        .where(ApplicationProcessModel.status == "ACTIVE")
        .group_by(ApplicationProcessModel.current_stage)
    ).all()
    applications_by_stage = {str(stage): int(total) for stage, total in stage_rows}
    precision = _precision_metrics(session, profile_version_id=profile_version_id)
    companies_covered, companies_with_ats = _companies_coverage(session)
    return OverviewSummary(
        opportunities_total=_count(session, select(func.count(OpportunityModel.id))),
        opportunities_active=_count(
            session,
            select(func.count(OpportunityModel.id)).where(
                OpportunityModel.lifecycle_status == "ACTIVE"
            ),
        ),
        new_opportunities=_count(
            session,
            select(func.count(OpportunityModel.id)).where(
                OpportunityModel.created_at >= since
            ),
        ),
        assessed_opportunities=_count(
            session, select(func.count()).select_from(assessments)
        ),
        verdict_counts=verdict_counts,
        analyses_degraded=int(degraded or 0),
        sources_total=_count(session, select(func.count(SourceDefinitionModel.id))),
        sources_enabled=_count(
            session,
            select(func.count(SourceDefinitionModel.id)).where(
                SourceDefinitionModel.enabled.is_(True)
            ),
        ),
        sources_failing=len(failing),
        failing_sources=failing,
        pending_normalizations=_pending_normalizations(session),
        applications_active=sum(applications_by_stage.values()),
        applications_by_stage=applications_by_stage,
        follow_ups_due=_count(
            session,
            select(func.count(ApplicationProcessModel.id)).where(
                ApplicationProcessModel.status == "ACTIVE",
                ApplicationProcessModel.next_action_at.is_not(None),
                ApplicationProcessModel.next_action_at
                <= reference + timedelta(days=FOLLOW_UP_WINDOW_DAYS),
            ),
        ),
        precision_percent=precision.precision,
        precision_marked_count=precision.marked_count,
        companies_covered=companies_covered,
        companies_with_ats=companies_with_ats,
    )


def _count(session: Session, statement: Select[Any]) -> int:
    return int(session.scalar(statement) or 0)


def _pending_normalizations(session: Session) -> int:
    """Raw items preserved but not yet turned into an opportunity."""
    return _count(
        session,
        select(func.count(RawItemModel.id))
        .outerjoin(
            NormalizationResultModel,
            NormalizationResultModel.raw_item_id == RawItemModel.id,
        )
        .where(NormalizationResultModel.id.is_(None)),
    )


def _latest_runs() -> Any:
    ranked = select(
        SourceRunModel.id.label("run_id"),
        SourceRunModel.source_definition_id.label("source_definition_id"),
        SourceRunModel.status.label("status"),
        SourceRunModel.started_at.label("started_at"),
        SourceRunModel.finished_at.label("finished_at"),
        SourceRunModel.error_code.label("error_code"),
        SourceRunModel.error_summary.label("error_summary"),
        SourceRunModel.items_seen.label("items_seen"),
        SourceRunModel.items_persisted.label("items_persisted"),
        SourceRunModel.items_skipped.label("items_skipped"),
        SourceRunModel.items_invalid.label("items_invalid"),
        func.row_number()
        .over(
            partition_by=SourceRunModel.source_definition_id,
            order_by=(
                func.coalesce(SourceRunModel.finished_at, SourceRunModel.started_at).desc(),
                SourceRunModel.id.desc(),
            ),
        )
        .label("position"),
    ).subquery("ranked_runs")
    return select(ranked).where(ranked.c.position == 1).subquery("latest_run")


def list_source_health(
    session: Session,
    *,
    only_failing: bool = False,
) -> tuple[SourceHealth, ...]:
    """Every source with its last run. A source that never ran reports `None`, not zero."""
    latest = _latest_runs()
    statement = (
        select(
            SourceDefinitionModel.id,
            SourceDefinitionModel.name,
            SourceDefinitionModel.source_type,
            SourceDefinitionModel.enabled,
            SourceDefinitionModel.evidence_status,
            SourceDefinitionModel.terms_reviewed,
            SourceDefinitionModel.collector_local_tested,
            SourceDefinitionModel.schedule,
            latest.c.run_id,
            latest.c.status,
            latest.c.started_at,
            latest.c.finished_at,
            latest.c.error_code,
            latest.c.error_summary,
            latest.c.items_seen,
            latest.c.items_persisted,
            latest.c.items_skipped,
            latest.c.items_invalid,
        )
        .select_from(SourceDefinitionModel)
        .outerjoin(latest, latest.c.source_definition_id == SourceDefinitionModel.id)
    )
    if only_failing:
        statement = statement.where(latest.c.status.in_(FAILING_RUN_STATUSES))
    rows = session.execute(
        statement.order_by(
            latest.c.finished_at.desc().nulls_last(), SourceDefinitionModel.name
        )
    ).all()
    seniority_rows = session.execute(
        select(
            SourceOccurrenceModel.source_definition_id,
            OpportunityModel.seniority,
            func.count(),
        )
        .join(
            OpportunityModel,
            OpportunityModel.id == SourceOccurrenceModel.opportunity_id,
        )
        .group_by(SourceOccurrenceModel.source_definition_id, OpportunityModel.seniority)
    ).all()
    seniority_by_source: dict[UUID, dict[str, int]] = {}
    for source_id, seniority, count in seniority_rows:
        seniority_by_source.setdefault(source_id, {})[seniority] = count
    return tuple(
        SourceHealth(
            source_definition_id=row[0],
            name=row[1],
            source_type=row[2],
            enabled=row[3],
            evidence_status=row[4],
            terms_reviewed=row[5],
            collector_local_tested=row[6],
            schedule=row[7],
            last_run_id=row[8],
            last_run_status=row[9],
            last_run_started_at=row[10],
            last_run_finished_at=row[11],
            last_run_error_code=row[12],
            last_run_error=row[13],
            last_run_items_seen=row[14],
            last_run_items_persisted=row[15],
            last_run_items_skipped=row[16],
            last_run_items_invalid=row[17],
            seniority_counts=seniority_by_source.get(row[0], {}),
        )
        for row in rows
    )


def source_coverage_report(
    session: Session, *, correlation_id: str | None = None
) -> SourceCoverageReport:
    """Reconcile catalogue and source execution without mistaking zero items for failure."""
    sources = session.scalars(
        select(SourceDefinitionModel).order_by(SourceDefinitionModel.name)
    ).all()
    source_ids = [source.id for source in sources]
    run_statement = select(SourceRunModel).where(
        SourceRunModel.source_definition_id.in_(source_ids)
    )
    if correlation_id is not None:
        run_statement = run_statement.where(
            SourceRunModel.correlation_id == correlation_id
        )
    runs = session.scalars(
        run_statement.order_by(
            SourceRunModel.finished_at.desc().nulls_last(), SourceRunModel.id.desc()
        )
    ).all()
    latest_by_source: dict[UUID, SourceRunModel] = {}
    for source_run in runs:
        latest_by_source.setdefault(source_run.source_definition_id, source_run)
    run_ids = [source_run.id for source_run in latest_by_source.values()]
    raw_items: dict[UUID, int] = {}
    if run_ids:
        raw_item_rows = session.execute(
            select(RawItemModel.source_definition_id, func.count())
            .where(RawItemModel.source_run_id.in_(run_ids))
            .group_by(RawItemModel.source_definition_id)
        ).all()
        raw_items = {source_id: item_count for source_id, item_count in raw_item_rows}
    eligible = [
        source
        for source in sources
        if source.enabled
        and (
            source.source_type == "manual"
            or (
                source.evidence_status == "confirmed"
                and source.reviewed_at is not None
                and source.terms_reviewed
                and source.collector_local_tested
            )
        )
    ]
    eligible_ids = {source.id for source in eligible}
    coverage = []
    for source in sources:
        run: SourceRunModel | None = latest_by_source.get(source.id)
        if not source.enabled:
            state = "NOT_ENABLED"
        elif source.id not in eligible_ids:
            state = "CONFIGURATION_BLOCKED"
        elif run is None:
            state = "NOT_RUN"
        elif run.status == "SUCCEEDED" and run.items_seen == 0:
            state = "SUCCEEDED_ZERO"
        else:
            state = run.status
        coverage.append(
            SourceCoverage(
                source_definition_id=source.id,
                name=source.name,
                state=state,
                run_status=run.status if run else None,
                raw_items=raw_items.get(source.id, 0),
            )
        )
    return SourceCoverageReport(
        correlation_id=correlation_id,
        catalog_companies=session.scalar(select(func.count(Company.id))) or 0,
        catalog_source_records=session.scalar(select(func.count(CompanySource.id))) or 0,
        proposed_sources=sum(not source.enabled for source in sources),
        homologated_sources=len(eligible),
        enabled_sources=sum(source.enabled for source in sources),
        eligible_sources=len(eligible),
        sources=tuple(coverage),
    )


def _companies_coverage(session: Session) -> tuple[int, int]:
    """(empresas com pelo menos uma fonte habilitada, empresas com ATS identificado)."""
    covered = _count(
        session,
        select(func.count(func.distinct(CompanySource.company_id)))
        .select_from(CompanySource)
        .join(
            SourceDefinitionModel,
            SourceDefinitionModel.company_source_id == CompanySource.id,
        )
        .where(SourceDefinitionModel.enabled.is_(True)),
    )
    with_ats = _count(
        session,
        select(func.count(func.distinct(CompanySource.company_id))).where(
            CompanySource.source_type.in_(ATS_COLLECTOR_SOURCE_TYPES)
        ),
    )
    return covered, with_ats


def _precision_metrics(
    session: Session,
    *,
    profile_version_id: UUID | None = None,
    sample_size: int = PRECISION_SAMPLE_SIZE,
) -> PrecisionMetrics:
    """Precision over the top `sample_size` Inbox rows in the default order.

    Computed only over marked opportunities, `None` when nothing is marked yet: a
    percentage over zero marks would be a frail number, not a metric.
    """
    page = list_opportunity_inbox(
        session,
        InboxQuery(order=InboxOrder.PRIORITY, limit=sample_size, offset=0),
    )
    opportunity_ids = [item.opportunity_id for item in page.items]
    if not opportunity_ids:
        return PrecisionMetrics(
            sample_size=0, marked_count=0, relevant_count=0, precision=None
        )
    latest = (
        select(
            RelevanceMarkModel.opportunity_id.label("opportunity_id"),
            RelevanceMarkModel.relevant.label("relevant"),
            func.row_number()
            .over(
                partition_by=RelevanceMarkModel.opportunity_id,
                order_by=(
                    RelevanceMarkModel.marked_at.desc(),
                    RelevanceMarkModel.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(RelevanceMarkModel.opportunity_id.in_(opportunity_ids))
        .subquery("ranked_marks")
    )
    marks = session.execute(
        select(latest.c.relevant).where(latest.c.position == 1)
    ).all()
    marked_count = len(marks)
    relevant_count = sum(1 for (relevant,) in marks if relevant)
    precision = (
        Decimal(relevant_count) / Decimal(marked_count) if marked_count > 0 else None
    )
    return PrecisionMetrics(
        sample_size=len(opportunity_ids),
        marked_count=marked_count,
        relevant_count=relevant_count,
        precision=precision,
    )


def search_metrics(
    session: Session,
    *,
    window_days: int = 7,
    profile_version_id: UUID | None = None,
    now: datetime | None = None,
) -> SearchMetricsReport:
    """The cobertura and precisão report the SPEC (§3) and F17-01 call for."""
    reference = now or datetime.now(UTC)
    since = reference - timedelta(days=window_days)

    run_rows = session.execute(
        select(
            SourceRunModel.source_definition_id,
            SourceDefinitionModel.name,
            func.count(SourceRunModel.id),
            func.coalesce(func.sum(SourceRunModel.items_seen), 0),
            func.coalesce(func.sum(SourceRunModel.items_persisted), 0),
            func.coalesce(func.sum(SourceRunModel.items_skipped), 0),
            func.coalesce(func.sum(SourceRunModel.items_invalid), 0),
        )
        .join(
            SourceDefinitionModel,
            SourceDefinitionModel.id == SourceRunModel.source_definition_id,
        )
        .where(SourceRunModel.started_at >= since)
        .group_by(SourceRunModel.source_definition_id, SourceDefinitionModel.name)
        .order_by(SourceDefinitionModel.name)
    ).all()

    new_by_source: dict[UUID, int] = {
        row[0]: row[1]
        for row in session.execute(
            select(SourceOccurrenceModel.source_definition_id, func.count())
            .join(
                OpportunityModel,
                OpportunityModel.id == SourceOccurrenceModel.opportunity_id,
            )
            .where(OpportunityModel.created_at >= since)
            .group_by(SourceOccurrenceModel.source_definition_id)
        ).all()
    }

    by_source = tuple(
        SourceCoverageMetric(
            source_definition_id=row[0],
            name=row[1],
            runs=int(row[2]),
            items_seen=int(row[3]),
            items_persisted=int(row[4]),
            items_duplicate=int(row[5]),
            items_invalid=int(row[6]),
            new_opportunities=int(new_by_source.get(row[0], 0)),
        )
        for row in run_rows
    )

    new_opportunities = _count(
        session,
        select(func.count(OpportunityModel.id)).where(
            OpportunityModel.created_at >= since
        ),
    )
    seniority_total = _count(session, select(func.count(OpportunityModel.id)))
    seniority_unknown = _count(
        session,
        select(func.count(OpportunityModel.id)).where(
            OpportunityModel.seniority == "UNKNOWN"
        ),
    )
    seniority_unknown_rate = (
        Decimal(seniority_unknown) / Decimal(seniority_total)
        if seniority_total > 0
        else None
    )
    role_family_unknown = _count(
        session,
        select(func.count(OpportunityModel.id)).where(
            OpportunityModel.role_family == "UNKNOWN"
        ),
    )
    role_family_unknown_rate = (
        Decimal(role_family_unknown) / Decimal(seniority_total)
        if seniority_total > 0
        else None
    )
    companies_covered, companies_with_ats = _companies_coverage(session)

    coverage = CoverageMetrics(
        window_days=window_days,
        runs=sum(item.runs for item in by_source),
        items_seen=sum(item.items_seen for item in by_source),
        items_persisted=sum(item.items_persisted for item in by_source),
        items_duplicate=sum(item.items_duplicate for item in by_source),
        items_invalid=sum(item.items_invalid for item in by_source),
        new_opportunities=new_opportunities,
        companies_covered=companies_covered,
        companies_with_ats=companies_with_ats,
        seniority_unknown_rate=seniority_unknown_rate,
        role_family_unknown_rate=role_family_unknown_rate,
        by_source=by_source,
    )
    precision = _precision_metrics(session, profile_version_id=profile_version_id)
    return SearchMetricsReport(
        window_days=window_days,
        generated_at=reference,
        coverage=coverage,
        precision=precision,
    )


__all__ = [
    "ATS_COLLECTOR_SOURCE_TYPES",
    "FAILING_RUN_STATUSES",
    "FOLLOW_UP_WINDOW_DAYS",
    "NEW_OPPORTUNITY_WINDOW_DAYS",
    "PRECISION_SAMPLE_SIZE",
    "CoverageMetrics",
    "InboxItem",
    "InboxOrder",
    "InboxPage",
    "InboxQuery",
    "OverviewSummary",
    "PrecisionMetrics",
    "SearchMetricsReport",
    "SourceCoverageMetric",
    "SourceHealth",
    "SourceCoverage",
    "SourceCoverageReport",
    "list_opportunity_inbox",
    "list_source_health",
    "search_metrics",
    "source_coverage_report",
    "summarize_overview",
]
