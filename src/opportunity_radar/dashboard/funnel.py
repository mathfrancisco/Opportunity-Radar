"""Funnel and north-star of the catalogue (SPEC 48 sections 1 and 2, card F48-06).

The north-star is "useful new postings per day that the default Inbox shows". A posting is
useful and visible when it is open, not a duplicate, inside the default recency window, not
`INELIGIBLE` for the active profile, allowed in Brazil (or in an unknown country or
anywhere), in a target area, and counted once per (normalized company, normalized title).
While the active profile names no target areas the technical proxy stands in for them; a
profile that names areas replaces it.

Everything is a `SELECT` over persisted rows and takes the clock as an argument. A guard
that cannot be computed from the database is listed in `not_measured` rather than reported
as zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, Text, cast, func, or_, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.forbidden import FORBIDDEN_HOST_PATTERNS
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.dashboard.queries import (
    InboxQuery,
    _latest_assessments,
    _recency_condition,
)
from opportunity_radar.matching.models import MatchAnalysisModel, MatchAssessmentModel
from opportunity_radar.operations.collection_alarm import collection_gap_report
from opportunity_radar.opportunities.models import NormalizationResultModel, OpportunityModel
from opportunity_radar.opportunities.regions import ANY_COUNTRY

#: Areas used as target areas while the active profile has none (SPEC 48 section 1.1).
TECHNICAL_PROXY_FAMILIES: tuple[str, ...] = (
    "SOFTWARE_ENGINEERING",
    "DATA",
    "INFRASTRUCTURE",
    "SECURITY",
)

#: Verdicts that mean "the ranking said something" (anything but review/ineligible).
USEFUL_VERDICTS: tuple[str, ...] = ("HIGH_PRIORITY", "RECOMMENDED", "WATCHLIST", "LOW_MATCH")

#: Hosts the project must never touch (SPEC 48 section 1.2): the central F48-19 list.
FORBIDDEN_HOSTS: tuple[str, ...] = FORBIDDEN_HOST_PATTERNS

NEW_WINDOW = timedelta(hours=24)
_COUNTRY = "BR"

#: Guards section 1.2 asks for that no persisted row can answer.
NOT_MEASURED: tuple[str, ...] = (
    "sources_evaluated_per_pass",
    "false_closures",
)


@dataclass(frozen=True, slots=True)
class FunnelStage:
    key: str
    label: str
    count: int
    #: What this stage lost against the one it narrows; `None` for a stage that only counts.
    lost: int | None = None


@dataclass(frozen=True, slots=True)
class Ratio:
    count: int
    total: int

    @property
    def ratio(self) -> float | None:
        return None if self.total == 0 else self.count / self.total


@dataclass(frozen=True, slots=True)
class NorthStar:
    role_families: tuple[str, ...]
    #: True while the technical proxy stands in for the profile's areas.
    proxy: bool
    #: Useful visible postings right now (the stock).
    stock: int
    #: ...of which created in the last `window_hours`.
    new_in_window: int
    window_hours: int
    #: Cumulative narrowing that ends in `stock`.
    stack: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class FunnelReport:
    generated_at: datetime
    stages: tuple[FunnelStage, ...]
    north_star: NorthStar
    guards: dict[str, Ratio] = field(default_factory=dict)
    forbidden_hosts_touched: int = 0
    not_measured: tuple[str, ...] = NOT_MEASURED


def funnel_report(
    session: Session,
    *,
    now: datetime | None = None,
    target_role_families: Sequence[str] = (),
    recency_window_days: int | None = None,
    window: timedelta = NEW_WINDOW,
) -> FunnelReport:
    reference = now or datetime.now(UTC)
    inbox = (
        InboxQuery(now=reference, only_recent=True)
        if recency_window_days is None
        else InboxQuery(
            now=reference, only_recent=True, recency_window_days=recency_window_days
        )
    )
    families = tuple(target_role_families)
    proxy = not families
    if proxy:
        families = TECHNICAL_PROXY_FAMILIES

    opportunities = OpportunityModel
    is_open = (
        opportunities.lifecycle_status != "CLOSED",
        opportunities.duplicate_of.is_(None),
    )
    recent = _recency_condition(inbox)

    def count(*conditions: Any) -> int:
        return _scalar(
            session, select(func.count()).select_from(opportunities).where(*conditions)
        )

    def unique(*conditions: Any) -> int:
        return _unique_postings(session, conditions)

    assessments = _latest_assessments(None)
    ineligible_ids = select(assessments.c.opportunity_id).where(
        assessments.c.verdict == "INELIGIBLE"
    )
    not_ineligible = opportunities.id.not_in(ineligible_ids)
    country_ok = or_(
        opportunities.allowed_countries.is_(None),
        opportunities.allowed_countries.any(_COUNTRY),
        opportunities.allowed_countries.any(ANY_COUNTRY),
    )
    in_area = opportunities.role_family.in_(families)

    stack_conditions = [
        ("open", is_open),
        ("recent", (recent,)),
        ("not_ineligible", (not_ineligible,)),
        ("country", (country_ok,)),
        ("area", (in_area,)),
    ]
    stack: list[tuple[str, int]] = []
    accumulated: list[Any] = []
    for label, conditions in stack_conditions:
        accumulated.extend(conditions)
        stack.append((label, count(*accumulated)))
    stock = unique(*accumulated)
    stack.append(("unique_company_title", stock))
    new_in_window = unique(*accumulated, opportunities.created_at >= reference - window)

    total_opportunities = count()
    open_total = count(*is_open)
    open_unique = unique(*is_open)
    default_list = count(*is_open, recent)
    default_unique = unique(*is_open, recent)
    raw_items = _scalar(session, select(func.count()).select_from(RawItemModel))
    normalization_failed = _scalar(
        session,
        select(func.count(func.distinct(NormalizationResultModel.raw_item_id))).where(
            NormalizationResultModel.status == "FAILED"
        ),
    )
    normalized = _scalar(
        session,
        select(func.count(func.distinct(NormalizationResultModel.raw_item_id))).where(
            NormalizationResultModel.opportunity_id.is_not(None)
        ),
    )
    eligible_sources = _eligible_sources(session)
    with_scheduled_run = _scalar(
        session,
        select(func.count(func.distinct(SourceRunModel.source_definition_id)))
        .join(
            SourceDefinitionModel,
            SourceDefinitionModel.id == SourceRunModel.source_definition_id,
        )
        .where(
            SourceRunModel.execution_trigger == "SCHEDULED",
            *_eligible_source_conditions(),
        ),
    )
    assessed = _scalar(
        session,
        select(func.count(func.distinct(MatchAssessmentModel.opportunity_id))),
    )
    with_verdict = _scalar(
        session,
        select(func.count())
        .select_from(assessments)
        .where(assessments.c.verdict.in_(USEFUL_VERDICTS)),
    )
    analysis_attempts = _scalar(
        session,
        select(func.count())
        .select_from(MatchAnalysisModel)
        .where(MatchAnalysisModel.status.in_(("AI_COMPLETED", "AI_FAILED"))),
    )
    analysis_completed = _scalar(
        session,
        select(func.count())
        .select_from(MatchAnalysisModel)
        .where(MatchAnalysisModel.status == "AI_COMPLETED"),
    )
    analysis_failed = analysis_attempts - analysis_completed
    quota_failures = _scalar(
        session,
        select(func.count())
        .select_from(MatchAnalysisModel)
        .where(
            MatchAnalysisModel.status == "AI_FAILED",
            MatchAnalysisModel.failure_code == "QUOTA_EXHAUSTED",
        ),
    )

    stages = (
        FunnelStage("sources_enabled", "Fontes habilitadas e nao manuais", eligible_sources),
        FunnelStage(
            "sources_collected",
            "...com ao menos uma execucao agendada",
            with_scheduled_run,
            eligible_sources - with_scheduled_run,
        ),
        FunnelStage("raw_items", "raw_item coletados", raw_items),
        FunnelStage(
            "normalized",
            "Normalizados com oportunidade",
            normalized,
            normalization_failed,
        ),
        FunnelStage("opportunities", "Oportunidades", total_opportunities),
        FunnelStage(
            "open", "Abertas (nao CLOSED, nao duplicadas)", open_total,
            total_opportunities - open_total,
        ),
        FunnelStage(
            "unique_company_title",
            "Sem repetir empresa+titulo",
            open_unique,
            open_total - open_unique,
        ),
        FunnelStage(
            "default_filter",
            "No filtro padrao (recencia)",
            default_list,
            open_total - default_list,
        ),
        FunnelStage(
            "assessed",
            "Avaliadas pelo matching",
            assessed,
            total_opportunities - assessed,
        ),
        FunnelStage(
            "verdict",
            "Veredito diferente de REVIEW_REQUIRED/INELIGIBLE",
            with_verdict,
            assessed - with_verdict,
        ),
        FunnelStage(
            "ai_analysis",
            "Analise de IA concluida",
            analysis_completed,
            analysis_failed,
        ),
    )

    default_condition = (*is_open, recent)
    gap = collection_gap_report(session, now=reference)
    guards = {
        "sources_on_schedule": Ratio(
            gap.evaluated_sources - len(gap.overdue_sources), gap.evaluated_sources
        ),
        "normalization_failed": Ratio(normalization_failed, raw_items),
        "default_list_repetition": Ratio(default_list - default_unique, default_list),
        "seniority_unknown": Ratio(
            count(*default_condition, opportunities.seniority == "UNKNOWN"), default_list
        ),
        "work_mode_unknown": Ratio(
            count(*default_condition, opportunities.work_mode == "UNKNOWN"), default_list
        ),
        "country_unknown": Ratio(
            count(*default_condition, opportunities.allowed_countries.is_(None)),
            default_list,
        ),
        "useful_verdict": Ratio(with_verdict, assessed),
        "ai_failed_by_quota": Ratio(quota_failures, analysis_attempts),
    }
    return FunnelReport(
        generated_at=reference,
        stages=stages,
        north_star=NorthStar(
            role_families=families,
            proxy=proxy,
            stock=stock,
            new_in_window=new_in_window,
            window_hours=int(window.total_seconds() // 3600),
            stack=tuple(stack),
        ),
        guards=guards,
        forbidden_hosts_touched=_forbidden_hosts_touched(session),
    )


def _scalar(session: Session, statement: Select[Any]) -> int:
    return int(session.scalar(statement) or 0)


def _unique_postings(session: Session, conditions: Sequence[Any]) -> int:
    """One per (normalized company, normalized title): 100 cities of a job are one job."""
    grouped = (
        select(
            func.coalesce(OpportunityModel.normalized_company_name, "").label("company"),
            OpportunityModel.normalized_title.label("title"),
        )
        .where(*conditions)
        .distinct()
        .subquery("unique_postings")
    )
    return _scalar(session, select(func.count()).select_from(grouped))


def _eligible_source_conditions() -> tuple[Any, ...]:
    return (
        SourceDefinitionModel.enabled.is_(True),
        SourceDefinitionModel.source_type != "manual",
    )


def _eligible_sources(session: Session) -> int:
    return _scalar(
        session,
        select(func.count())
        .select_from(SourceDefinitionModel)
        .where(*_eligible_source_conditions()),
    )


def _forbidden_hosts_touched(session: Session) -> int:
    """Sources configured for, or items fetched from, a host on the forbidden list."""
    on_configuration = or_(
        *(
            func.lower(cast(SourceDefinitionModel.configuration, Text)).contains(host)
            for host in FORBIDDEN_HOSTS
        )
    )
    on_item = or_(
        *(func.lower(RawItemModel.canonical_url).contains(host) for host in FORBIDDEN_HOSTS)
    )
    sources = _scalar(
        session, select(func.count()).select_from(SourceDefinitionModel).where(on_configuration)
    )
    items = _scalar(session, select(func.count()).select_from(RawItemModel).where(on_item))
    return sources + items


__all__ = [
    "FORBIDDEN_HOSTS",
    "NOT_MEASURED",
    "TECHNICAL_PROXY_FAMILIES",
    "USEFUL_VERDICTS",
    "FunnelReport",
    "FunnelStage",
    "NorthStar",
    "Ratio",
    "funnel_report",
]
