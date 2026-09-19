"""Immutable persistence records for deterministic matching decisions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opportunity_radar.platform.database import Base

SCHEMA = "matching"


class MatchAssessmentModel(Base):
    """A reproducible assessment, keyed by all deterministic input versions."""

    __tablename__ = "match_assessment"
    __table_args__ = (
        UniqueConstraint("input_hash", name="uq_match_assessment_input_hash"),
        CheckConstraint(
            "char_length(input_hash) = 64", name="ck_match_assessment_input_hash"
        ),
        CheckConstraint(
            "opportunity_version > 0", name="ck_match_assessment_opportunity_version"
        ),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_match_assessment_score"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_match_assessment_confidence"
        ),
        CheckConstraint(
            "eligibility IN ('ELIGIBLE', 'INELIGIBLE', 'UNKNOWN')",
            name="ck_match_assessment_eligibility",
        ),
        CheckConstraint("status IN ('COMPLETED')", name="ck_match_assessment_status"),
        CheckConstraint(
            "verdict IN ('HIGH_PRIORITY', 'RECOMMENDED', 'WATCHLIST', 'LOW_MATCH', "
            "'INELIGIBLE', 'REVIEW_REQUIRED')",
            name="ck_match_assessment_verdict",
        ),
        Index(
            "ix_match_assessment_opportunity_profile_created",
            "opportunity_id",
            "profile_version_id",
            "created_at",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("opportunities.opportunity.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opportunity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(64), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    opportunity_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    eligibility: Mapped[str] = mapped_column(String(16), nullable=False)
    eligibility_details: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="COMPLETED")
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    factors: Mapped[list["MatchFactorModel"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


class MatchFactorModel(Base):
    """An immutable, individually explainable contribution to an assessment."""

    __tablename__ = "match_factor"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id", "factor_code", name="uq_match_factor_assessment_code"
        ),
        CheckConstraint("weight >= 0 AND weight <= 1", name="ck_match_factor_weight"),
        CheckConstraint(
            "raw_score IS NULL OR (raw_score >= 0 AND raw_score <= 1)",
            name="ck_match_factor_raw_score",
        ),
        CheckConstraint(
            "contribution >= 0 AND contribution <= 100",
            name="ck_match_factor_contribution",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_match_factor_confidence"
        ),
        CheckConstraint(
            "status IN ('KNOWN', 'UNKNOWN', 'NOT_APPLICABLE')",
            name="ck_match_factor_status",
        ),
        CheckConstraint(
            "missing_policy IN ('NEUTRAL', 'PENALIZE', 'EXCLUDE_AND_RENORMALIZE', "
            "'REQUIRE_REVIEW')",
            name="ck_match_factor_missing_policy",
        ),
        Index("ix_match_factor_assessment", "assessment_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    assessment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.match_assessment.id", ondelete="CASCADE"),
        nullable=False,
    )
    factor_code: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    raw_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    contribution: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    missing_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assessment: Mapped[MatchAssessmentModel] = relationship(back_populates="factors")