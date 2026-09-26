"""Persistence adapter for immutable deterministic matching assessments."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import Select, case, delete, func, literal, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.orm import Session, aliased, selectinload

from opportunity_radar.matching.analysis import ANALYSIS_KEY_VERSION, Claim
from opportunity_radar.matching.models import (
    MatchAnalysisClaimModel,
    MatchAnalysisModel,
    MatchAssessmentModel,
    MatchFactorModel,
)
from opportunity_radar.matching.text import TokenCalibration, calibrate
from opportunity_radar.opportunities.models import OpportunityModel

# A degraded attempt is what the retry budget counts. `AI_PENDING` is not an attempt and
# `AI_COMPLETED` ends the budget by removing the assessment from the queue entirely.
ANALYSIS_ATTEMPT_STATUSES = ("AI_FAILED", "AI_SKIPPED")

# The order the operator reads the Inbox in, so a backlog spends the model on what will be
# read first. A verdict outside this list still queues, after all of these.
ANALYSIS_VERDICT_PRIORITY = ("HIGH_PRIORITY", "RECOMMENDED", "REVIEW_REQUIRED", "WATCHLIST")


def _stored_item(item: Any) -> Any:
    return item.as_dict() if isinstance(item, Claim) else item


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
    # Strings under `analysis-v1`; claims (or their stored objects) from `analysis-v2` on.
    strengths: tuple[Any, ...] = ()
    risks: tuple[Any, ...] = ()
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
    prompt_chars: int | None = None
    prompt_tokens_estimate: int | None = None
    # Identity of the call (card F16-08): absent on rows written before it existed.
    key_version: str | None = None
    payload_hash: str | None = None
    payload: dict[str, Any] | None = None
    inference: dict[str, Any] | None = None
    context_refs: tuple[Any, ...] = ()
    prompt_budget: int | None = None


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

    def get_completed_analysis(
        self, assessment_id: UUID, *, cache_key: str | None = None
    ) -> MatchAnalysisModel | None:
        """The reusable analysis: a completed one survives restarts, a degraded one does not.

        With `cache_key`, only a row keyed by that exact `analysis-key-v2` qualifies: the
        assessment's older answer under another prompt, model or payload is history.
        """
        conditions = [
            MatchAnalysisModel.assessment_id == assessment_id,
            MatchAnalysisModel.status == "AI_COMPLETED",
        ]
        if cache_key is not None:
            conditions += [
                MatchAnalysisModel.cache_key == cache_key,
                MatchAnalysisModel.key_version == ANALYSIS_KEY_VERSION,
            ]
        return self.session.scalars(
            select(MatchAnalysisModel)
            .where(*conditions)
            .order_by(MatchAnalysisModel.analyzed_at.desc(), MatchAnalysisModel.id)
            .limit(1)
        ).one_or_none()

    def token_calibration(
        self, model_id: str, prompt_version: str, *, sample: int
    ) -> TokenCalibration:
        """The model's real cost per character under this prompt, from its latest calls.

        Per prompt version because the formatter changes the ratio: a JSON-only `v1`
        prompt and a `v2` prompt carrying prose are different texts to a tokenizer.
        """
        rows = self.session.execute(
            select(
                MatchAnalysisModel.prompt_tokens,
                MatchAnalysisModel.prompt_chars,
                MatchAnalysisModel.prompt_tokens_estimate,
            )
            .where(
                MatchAnalysisModel.model_id == model_id,
                MatchAnalysisModel.prompt_version == prompt_version,
                MatchAnalysisModel.prompt_tokens.is_not(None),
                MatchAnalysisModel.prompt_chars > 0,
            )
            .order_by(MatchAnalysisModel.analyzed_at.desc(), MatchAnalysisModel.id)
            .limit(sample)
        ).all()
        return calibrate([(tokens, chars, estimate) for tokens, chars, estimate in rows])

    def tokens_per_char(self, model_id: str, *, sample: int) -> float | None:
        """Real tokens per character over the model's latest measured analyses."""
        recent = (
            select(MatchAnalysisModel.prompt_tokens, MatchAnalysisModel.prompt_chars)
            .where(
                MatchAnalysisModel.model_id == model_id,
                MatchAnalysisModel.prompt_tokens.is_not(None),
                MatchAnalysisModel.prompt_chars > 0,
            )
            .order_by(MatchAnalysisModel.analyzed_at.desc(), MatchAnalysisModel.id)
            .limit(sample)
            .subquery()
        )
        tokens, chars = self.session.execute(
            select(func.sum(recent.c.prompt_tokens), func.sum(recent.c.prompt_chars))
        ).one()
        return float(tokens) / float(chars) if tokens and chars else None

    def completed_analysis_by_key(
        self, cache_key: str, *, model_digest: str | None = None
    ) -> MatchAnalysisModel | None:
        """The newest completed analysis under a key, whichever assessment it belongs to.

        Only `analysis-key-v2` rows qualify. When the weights behind the tag are known, a
        row recorded against other weights does not: the same tag re-pulled is another
        model. A row that never learned its digest is accepted, since the tag pins the
        quantization and nothing says the weights differ.
        """
        conditions = [
            MatchAnalysisModel.cache_key == cache_key,
            MatchAnalysisModel.status == "AI_COMPLETED",
            MatchAnalysisModel.key_version == ANALYSIS_KEY_VERSION,
        ]
        if model_digest:
            recorded = MatchAnalysisModel.inference["model_digest"].astext
            conditions.append(or_(recorded.is_(None), recorded == model_digest))
        return self.session.scalars(
            select(MatchAnalysisModel)
            .where(*conditions)
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
            # `analysis-v2` items are claims with evidence; JSONB stores them as objects.
            strengths=[_stored_item(item) for item in record.strengths],
            risks=[_stored_item(item) for item in record.risks],
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
            prompt_chars=record.prompt_chars,
            prompt_tokens_estimate=record.prompt_tokens_estimate,
            key_version=record.key_version,
            payload_hash=record.payload_hash,
            payload=deepcopy(record.payload) if record.payload is not None else None,
            inference=deepcopy(record.inference) if record.inference is not None else None,
            context_refs=[dict(item) for item in record.context_refs] or None,
            prompt_budget=record.prompt_budget,
        )
        self.session.add(analysis)
        return analysis

    @staticmethod
    def _assessments() -> Select[tuple[MatchAssessmentModel]]:
        return select(MatchAssessmentModel).options(
            selectinload(MatchAssessmentModel.factors),
            selectinload(MatchAssessmentModel.analyses),
        )
