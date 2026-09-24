"""Persistence adapter for immutable deterministic matching assessments."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import Select, case, delete, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session, aliased, selectinload

from opportunity_radar.matching.models import (
    MatchAnalysisClaimModel,
    MatchAnalysisModel,
    MatchAssessmentModel,
    MatchFactorModel,
)
from opportunity_radar.opportunities.models import OpportunityModel

# A degraded attempt is what the retry budget counts. `AI_PENDING` is not an attempt and
# `AI_COMPLETED` ends the budget by removing the assessment from the queue entirely.
ANALYSIS_ATTEMPT_STATUSES = ("AI_FAILED", "AI_SKIPPED")

# The order the operator reads the Inbox in, so a backlog spends the model on what will be
# read first. A verdict outside this list still queues, after all of these.
ANALYSIS_VERDICT_PRIORITY = ("HIGH_PRIORITY", "RECOMMENDED", "REVIEW_REQUIRED", "WATCHLIST")


@dataclass(frozen=True, slots=True)
class AssessmentRecord:
    opportunity_id: UUID
    opportunity_version: int
    profile_version_id: UUID
    input_hash: str
    rules_version: str
    taxonomy_version: str
    opportunity_snapshot: dict[str, Any]
    profile_snapshot: dict[str, Any]
    eligibility: str
    eligibility_details: tuple[Any, ...]
    verdict: str
    score: Decimal
    confidence: Decimal
    assessed_at: datetime
    status: str = "COMPLETED"


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    assessment_id: UUID
    cache_key: str
    status: str
    schema_version: str
    analyzed_at: datetime
    failure_code: str | None = None
    detail: str | None = None
    summary: str | None = None
    strengths: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    inferences: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    recommended_review: bool | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    total_ms: int | None = None
    load_ms: int | None = None
    prompt_tokens: int | None = None
    prompt_eval_ms: int | None = None
    output_tokens: int | None = None
    eval_ms: int | None = None


@dataclass(frozen=True, slots=True)
class FactorRecord:
    factor_code: str
    weight: Decimal
    raw_score: Decimal | None
    contribution: Decimal
    status: str
    confidence: Decimal
    missing_policy: str
    explanation: str
    evidence_refs: tuple[Any, ...] = ()


class SqlAlchemyMatchingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_existing(
        self,
        *,
        input_hash: str,
    ) -> MatchAssessmentModel | None:
        return self.session.scalars(
            self._assessments().where(
                MatchAssessmentModel.input_hash == input_hash,
            )
        ).unique().one_or_none()

    def get(self, assessment_id: UUID) -> MatchAssessmentModel | None:
        return self.session.scalars(
            self._assessments().where(MatchAssessmentModel.id == assessment_id)
        ).unique().one_or_none()

    def list(
        self,
        *,
        opportunity_id: UUID | None = None,
        profile_version_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[MatchAssessmentModel], int]:
        filters = []
        if opportunity_id is not None:
            filters.append(MatchAssessmentModel.opportunity_id == opportunity_id)
        if profile_version_id is not None:
            filters.append(MatchAssessmentModel.profile_version_id == profile_version_id)
        items = list(
            self.session.scalars(
                self._assessments()
                .where(*filters)
                .order_by(MatchAssessmentModel.assessed_at.desc(), MatchAssessmentModel.id)
                .offset(offset)
                .limit(limit)
            ).unique()
        )
        total = self.session.scalar(
            select(func.count(MatchAssessmentModel.id)).where(*filters)
        ) or 0
        return items, total

    def add(
        self,
        record: AssessmentRecord,
        factors: Sequence[FactorRecord],
    ) -> MatchAssessmentModel:
        existing = self.get_existing(
            input_hash=record.input_hash,
        )
        if existing is not None:
            return existing
        assessment = MatchAssessmentModel(
            opportunity_id=record.opportunity_id,
            opportunity_version=record.opportunity_version,
            profile_version_id=record.profile_version_id,
            input_hash=record.input_hash,
            rules_version=record.rules_version,
            taxonomy_version=record.taxonomy_version,
            opportunity_snapshot=deepcopy(record.opportunity_snapshot),
            profile_snapshot=deepcopy(record.profile_snapshot),
            eligibility=record.eligibility,
            eligibility_details=deepcopy(list(record.eligibility_details)),
            status=record.status,
            verdict=record.verdict,
            score=record.score,
            confidence=record.confidence,
            assessed_at=record.assessed_at,
            factors=[
                MatchFactorModel(
                    factor_code=factor.factor_code,
                    weight=factor.weight,
                    raw_score=factor.raw_score,
                    contribution=factor.contribution,
                    status=factor.status,
                    confidence=factor.confidence,
                    missing_policy=factor.missing_policy,
                    explanation=factor.explanation,
                    evidence_refs=deepcopy(list(factor.evidence_refs)),
                )
                for factor in factors
            ],
        )
        self.session.add(assessment)
        return assessment

    def get_completed_analysis(self, assessment_id: UUID) -> MatchAnalysisModel | None:
        """The reusable analysis: a completed one survives restarts, a degraded one does not."""
        return self.session.scalars(
            select(MatchAnalysisModel)
            .where(
                MatchAnalysisModel.assessment_id == assessment_id,
                MatchAnalysisModel.status == "AI_COMPLETED",
            )
            .order_by(MatchAnalysisModel.analyzed_at.desc(), MatchAnalysisModel.id)
            .limit(1)
        ).one_or_none()

    def completed_analysis_by_key(self, cache_key: str) -> MatchAnalysisModel | None:
        """The newest completed analysis under a key, whichever assessment it belongs to."""
        return self.session.scalars(
            select(MatchAnalysisModel)
            .where(
                MatchAnalysisModel.cache_key == cache_key,
                MatchAnalysisModel.status == "AI_COMPLETED",
            )
            .order_by(MatchAnalysisModel.analyzed_at.desc(), MatchAnalysisModel.id)
            .limit(1)
        ).one_or_none()

    def latest_analysis(self, assessment_id: UUID) -> MatchAnalysisModel | None:
        return self.session.scalars(
            select(MatchAnalysisModel)
            .where(MatchAnalysisModel.assessment_id == assessment_id)
            .order_by(MatchAnalysisModel.analyzed_at.desc(), MatchAnalysisModel.id)
            .limit(1)
        ).first()

    def pending_analysis_ids(
        self,
        *,
        eligible_verdicts: Sequence[str],
        limit: int,
        now: datetime,
        cooldown: timedelta,
        attempt_window: timedelta,
        max_attempts: int,
        # `Sequence` rather than `list`: the class already binds `list` to a method above,
        # which shadows the builtin for every annotation declared after it.
    ) -> Sequence[UUID]:
        """Assessments whose semantic layer is worth attempting right now.

        Four independent reasons to stay out of the queue, and none of them deletes
        history: the verdict is not worth the model's time, the analysis already
        completed, a newer assessment superseded this one, or the retry budget says wait.
        """
        if not eligible_verdicts or limit <= 0 or max_attempts <= 0:
            return []
        verdict_rank = case(
            {verdict: rank for rank, verdict in enumerate(ANALYSIS_VERDICT_PRIORITY)},
            value=MatchAssessmentModel.verdict,
            else_=len(ANALYSIS_VERDICT_PRIORITY),
        )
        # Value first, then the freshest posting; `id` last keeps every batch deterministic.
        return list(
            self.session.scalars(
                select(MatchAssessmentModel.id)
                .join(
                    OpportunityModel,
                    OpportunityModel.id == MatchAssessmentModel.opportunity_id,
                )
                .where(
                    *self._pending_analysis_conditions(
                        eligible_verdicts=eligible_verdicts,
                        now=now,
                        cooldown=cooldown,
                        attempt_window=attempt_window,
                        max_attempts=max_attempts,
                    )
                )
                .order_by(
                    verdict_rank,
                    OpportunityModel.published_at.desc().nulls_last(),
                    MatchAssessmentModel.assessed_at.desc(),
                    MatchAssessmentModel.id,
                )
                .limit(limit)
            )
        )

    def count_pending_analysis(
        self,
        *,
        eligible_verdicts: Sequence[str],
        now: datetime,
        cooldown: timedelta,
        attempt_window: timedelta,
        max_attempts: int,
    ) -> int:
        """How far behind the queue is: the same selection, without the batch cap."""
        if not eligible_verdicts or max_attempts <= 0:
            return 0
        total = self.session.scalar(
            select(func.count())
            .select_from(MatchAssessmentModel)
            .where(
                *self._pending_analysis_conditions(
                    eligible_verdicts=eligible_verdicts,
                    now=now,
                    cooldown=cooldown,
                    attempt_window=attempt_window,
                    max_attempts=max_attempts,
                )
            )
        )
        return total or 0

    @staticmethod
    def _pending_analysis_conditions(
        *,
        eligible_verdicts: Sequence[str],
        now: datetime,
        cooldown: timedelta,
        attempt_window: timedelta,
        max_attempts: int,
    ) -> tuple[Any, ...]:
        completed = aliased(MatchAnalysisModel)
        cooling = aliased(MatchAnalysisModel)
        attempted = aliased(MatchAnalysisModel)
        superseding = aliased(MatchAssessmentModel)

        has_completed = (
            select(literal(1))
            .where(
                completed.assessment_id == MatchAssessmentModel.id,
                completed.status == "AI_COMPLETED",
            )
            .exists()
        )
        # Ordering by the same pair the query orders by keeps "newer" total: two
        # assessments written in the same instant still have one winner.
        is_superseded = (
            select(literal(1))
            .where(
                superseding.opportunity_id == MatchAssessmentModel.opportunity_id,
                tuple_(superseding.assessed_at, superseding.id)
                > tuple_(MatchAssessmentModel.assessed_at, MatchAssessmentModel.id),
            )
            .exists()
        )
        in_cooldown = (
            select(literal(1))
            .where(
                cooling.assessment_id == MatchAssessmentModel.id,
                cooling.status.in_(ANALYSIS_ATTEMPT_STATUSES),
                cooling.analyzed_at > now - cooldown,
            )
            .exists()
        )
        attempts = (
            select(func.count())
            .select_from(attempted)
            .where(
                attempted.assessment_id == MatchAssessmentModel.id,
                attempted.status.in_(ANALYSIS_ATTEMPT_STATUSES),
                attempted.analyzed_at > now - attempt_window,
            )
            .scalar_subquery()
        )
        return (
            MatchAssessmentModel.verdict.in_(tuple(eligible_verdicts)),
            ~has_completed,
            ~is_superseded,
            ~in_cooldown,
            attempts < max_attempts,
        )

    def acquire_analysis_claim(
        self,
        assessment_id: UUID,
        *,
        owner: str,
        now: datetime,
        lease: timedelta,
    ) -> bool:
        """Take the lease, or report that a live holder already has it.

        A single statement rather than read-then-write: two processes reaching here at the
        same instant must not both conclude the claim was free. The conflict clause lets an
        expired lease be taken over, so a crashed holder blocks the assessment for at most
        one lease.
        """
        expires_at = now + lease
        statement = (
            postgres_insert(MatchAnalysisClaimModel)
            .values(
                assessment_id=assessment_id,
                owner=owner,
                claimed_at=now,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=[MatchAnalysisClaimModel.assessment_id],
                set_={"owner": owner, "claimed_at": now, "expires_at": expires_at},
                where=MatchAnalysisClaimModel.expires_at <= now,
            )
            .returning(MatchAnalysisClaimModel.assessment_id)
        )
        return self.session.execute(statement).scalar_one_or_none() is not None

    def release_analysis_claim(self, assessment_id: UUID, *, owner: str) -> None:
        """Release only our own lease: a lease already taken over is not ours to drop."""
        self.session.execute(
            delete(MatchAnalysisClaimModel).where(
                MatchAnalysisClaimModel.assessment_id == assessment_id,
                MatchAnalysisClaimModel.owner == owner,
            )
        )

    def add_analysis(self, record: AnalysisRecord) -> MatchAnalysisModel:
        analysis = MatchAnalysisModel(
            assessment_id=record.assessment_id,
            cache_key=record.cache_key,
            status=record.status,
            failure_code=record.failure_code,
            detail=record.detail,
            summary=record.summary,
            strengths=list(record.strengths),
            risks=list(record.risks),
            inferences=list(record.inferences),
            unknowns=list(record.unknowns),
            recommended_review=record.recommended_review,
            model_id=record.model_id,
            prompt_version=record.prompt_version,
            schema_version=record.schema_version,
            analyzed_at=record.analyzed_at,
            total_ms=record.total_ms,
            load_ms=record.load_ms,
            prompt_tokens=record.prompt_tokens,
            prompt_eval_ms=record.prompt_eval_ms,
            output_tokens=record.output_tokens,
            eval_ms=record.eval_ms,
        )
        self.session.add(analysis)
        return analysis

    @staticmethod
    def _assessments() -> Select[tuple[MatchAssessmentModel]]:
        return select(MatchAssessmentModel).options(
            selectinload(MatchAssessmentModel.factors),
            selectinload(MatchAssessmentModel.analyses),
        )
