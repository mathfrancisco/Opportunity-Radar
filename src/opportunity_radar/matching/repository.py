"""Persistence adapter for immutable deterministic matching assessments."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.matching.models import MatchAssessmentModel, MatchFactorModel


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

    @staticmethod
    def _assessments() -> Select[tuple[MatchAssessmentModel]]:
        return select(MatchAssessmentModel).options(
            selectinload(MatchAssessmentModel.factors)
        )
