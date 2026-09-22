"""Query services behind the Overview and the Opportunity Inbox.

Both screens need the same join that no single aggregate owns: an opportunity, the most
recent assessment of it, the most recent semantic analysis of that assessment, and the
company that published it. Building it here keeps the repositories of each context about
one aggregate, as section 8.2 of docs/06-estrutura-projeto-mvp.md requires.

Every row exposes the assessment as optional. An opportunity that was never evaluated is
still in the inbox: hiding it would make the screen quietly disagree with the catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Select, case, func, literal, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company
from opportunity_radar.matching import currency
from opportunity_radar.matching.models import MatchAnalysisModel, MatchAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
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
    profile_version_id: UUID | None = None
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

    @property
    def last_run_duration_seconds(self) -> float | None:
        if self.last_run_started_at is None or self.last_run_finished_at is None:
            return None
        return (self.last_run_finished_at - self.last_run_started_at).total_seconds()


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
    if query.published_after is not None:
        filters.append(OpportunityModel.published_at >= query.published_after)
    if query.search and query.search.strip():
        pattern = f"%{query.search.strip().lower()}%"
        filters.append(
            func.lower(OpportunityModel.canonical_title).like(pattern)
            | func.lower(func.coalesce(OpportunityModel.company_name, "")).like(pattern)
        )
    return filters


def _inbox_ordering(order: InboxOrder, assessments: Any) -> list[Any]:
    recency = OpportunityModel.published_at.desc().nulls_last()
    score = assessments.c.score.desc().nulls_last()
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
        statement.order_by(*_inbox_ordering(query.order, assessments))
        .offset(query.offset)
        .limit(query.limit)
    ).all()
    return InboxPage(
        items=tuple(_inbox_item(row) for row in rows),
        total=total,
        offset=query.offset,
        limit=query.limit,
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
        published_at=row[10],
        opportunity_version=row[11],
        assessment_id=row[12],
        assessment_opportunity_version=row[13],
        assessment_profile_version_id=row[14],
        current_profile_version_id=row[15],
        verdict=row[16],
        eligibility=row[17],
        score=row[18],
        confidence=row[19],
        rules_version=row[20],
        is_stale=row[21],
        assessed_at=row[22],
        analysis_status=row[23],
        analysis_recommended_review=row[24],
        analysis_summary=row[25],
        application_id=row[26],
        application_stage=row[27],
        application_next_action_at=row[28],
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
        )
        for row in rows
    )


__all__ = [
    "FAILING_RUN_STATUSES",
    "FOLLOW_UP_WINDOW_DAYS",
    "NEW_OPPORTUNITY_WINDOW_DAYS",
    "InboxItem",
    "InboxOrder",
    "InboxPage",
    "InboxQuery",
    "OverviewSummary",
    "SourceHealth",
    "list_opportunity_inbox",
    "list_source_health",
    "summarize_overview",
]
