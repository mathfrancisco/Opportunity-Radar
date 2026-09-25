"""Immutable persistence records for deterministic matching decisions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
    analyses: Mapped[list["MatchAnalysisModel"]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        order_by="MatchAnalysisModel.analyzed_at",
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


class MatchAnalysisModel(Base):
    """Semantic layer of an assessment whose deterministic result already completed.

    Append-only history rather than one mutable row: a degraded attempt is evidence of
    what the system knew at that moment, and retrying must not erase it. The current
    analysis is the most recent row; a completed one is reused instead of re-prompting,
    which is the cache from section 45 surviving a restart.

    The table carries no score, verdict or eligibility on purpose — those live on the
    assessment and the model has no column to write them into.
    """

    __tablename__ = "match_analysis"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AI_PENDING', 'AI_COMPLETED', 'AI_FAILED', 'AI_SKIPPED')",
            name="ck_match_analysis_status",
        ),
        CheckConstraint(
            "status <> 'AI_COMPLETED' OR (summary IS NOT NULL AND model_id IS NOT NULL "
            "AND recommended_review IS NOT NULL)",
            name="ck_match_analysis_completed_payload",
        ),
        CheckConstraint(
            "status <> 'AI_FAILED' OR failure_code IS NOT NULL",
            name="ck_match_analysis_failed_code",
        ),
        CheckConstraint(
            "char_length(cache_key) = 64", name="ck_match_analysis_cache_key"
        ),
        Index("ix_match_analysis_assessment_analyzed", "assessment_id", "analyzed_at"),
        Index("ix_match_analysis_cache_key", "cache_key"),
        Index("ix_match_analysis_key_version", "cache_key", "key_version"),
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
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    risks: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    inferences: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    unknowns: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    recommended_review: Mapped[bool | None] = mapped_column(Boolean)
    model_id: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    # What the call cost, as the server reported it (docs/36-spec-ollama.md, section 9).
    # Null on rows written before it was recorded, and on calls that never reached the
    # model: unavailable, never zero.
    total_ms: Mapped[int | None] = mapped_column(Integer)
    load_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    prompt_eval_ms: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    eval_ms: Mapped[int | None] = mapped_column(Integer)
    # The prompt's size before sending, and the tokens it was estimated at (F16-05).
    prompt_chars: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens_estimate: Mapped[int | None] = mapped_column(Integer)
    # What the call was, not only what it answered (card F16-08). `key_version` NULL marks
    # a row keyed the pre-v2 way, which is kept for the audit and never reused as v2.
    key_version: Mapped[str | None] = mapped_column(String(32))
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    # The payload as sent — posting cut, profile history, retrieved decisions — so an
    # answer can be checked against its input. Local only, under the payload retention.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Model, prompt digest, effective options, calibration, cuts and server identity.
    inference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Similar decided postings the prompt received, as they stood (card F16-11).
    context_refs: Mapped[list[Any] | None] = mapped_column(JSONB)
    # Tokens the prompt was allowed; a real count above it is a suspected truncation.
    prompt_budget: Mapped[int | None] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    assessment: Mapped[MatchAssessmentModel] = relationship(back_populates="analyses")


class MatchAnalysisClaimModel(Base):
    """Exclusive lease over the semantic analysis of a single assessment.

    Mutual exclusion between the worker job and the manual action lives in the database
    rather than in process memory: the two run in different processes, so nothing in a
    single interpreter could keep them from prompting the same assessment twice.

    The lease expires instead of being held forever. A holder killed mid-analysis leaves a
    row behind, and a row that can never be released would silently retire an assessment
    from the queue — the expiry is what makes the claim survive a restart without becoming
    a permanent block.

    One row per assessment: the primary key is the exclusion.
    """

    __tablename__ = "match_analysis_claim"
    __table_args__ = (
        CheckConstraint(
            "expires_at > claimed_at", name="ck_match_analysis_claim_window"
        ),
        Index("ix_match_analysis_claim_expires_at", "expires_at"),
        {"schema": SCHEMA},
    )

    assessment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.match_assessment.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
