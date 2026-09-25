"""SQLAlchemy persistence models for the Opportunities context."""

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
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from opportunity_radar.acquisition.models import RawItemPayloadModel
from opportunity_radar.platform.database import Base

SCHEMA = "opportunities"


class OpportunityModel(Base):
    __tablename__ = "opportunity"
    __table_args__ = (
        UniqueConstraint(
            "fingerprint_version",
            "fingerprint",
            name="uq_opportunity_fingerprint_version_value",
        ),
        CheckConstraint(
            "work_mode IN ('REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN')",
            name="ck_opportunity_work_mode",
        ),
        CheckConstraint(
            "seniority IN ('INTERN', 'JUNIOR', 'MID', 'SENIOR', 'LEAD', "
            "'STAFF', 'MANAGER', 'DIRECTOR', 'UNKNOWN')",
            name="ck_opportunity_seniority",
        ),
        CheckConstraint(
            "contract_type IN ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY', "
            "'INTERNSHIP', 'UNKNOWN')",
            name="ck_opportunity_contract_type",
        ),
        CheckConstraint(
            "lifecycle_status IN ('DISCOVERED', 'ACTIVE', 'STALE', 'CLOSED', "
            "'ARCHIVED', 'REJECTED')",
            name="ck_opportunity_lifecycle_status",
        ),
        CheckConstraint("version > 0", name="ck_opportunity_version_positive"),
        Index(
            "ix_opportunity_company_status",
            "canonical_company_id",
            "lifecycle_status",
        ),
        Index("ix_opportunity_published", "published_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_version: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_company_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("company_radar.company.id", ondelete="SET NULL"),
    )
    company_name: Mapped[str | None] = mapped_column(String(255))
    normalized_company_name: Mapped[str | None] = mapped_column(String(255))
    location_text: Mapped[str | None] = mapped_column(String(512))
    normalized_location: Mapped[str | None] = mapped_column(String(512))
    work_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    seniority: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    contract_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN"
    )
    description: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="DISCOVERED"
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Evidence for the last automatic close/reopen: the two consecutive complete run ids
    #: that closed it, or the run id that brought it back. `None` until either happens.
    closure_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurrences: Mapped[list["SourceOccurrenceModel"]] = relationship(
        back_populates="opportunity"
    )
    normalization_results: Mapped[list["NormalizationResultModel"]] = relationship(
        back_populates="opportunity"
    )
    compensations: Mapped[list["OpportunityCompensationModel"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    skills: Mapped[list["OpportunitySkillModel"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class RelevanceMarkModel(Base):
    """One operator judgement of an opportunity, append-only.

    The current mark is the most recent row for the `opportunity_id`. Never updated or
    deleted, so precision can be recomputed against any past profile version. F17-01;
    out of scope: this table never feeds the score or the verdict.
    """

    __tablename__ = "relevance_mark"
    __table_args__ = (
        CheckConstraint(
            "reason IS NULL OR reason IN "
            "('AREA', 'SENIORITY', 'LOCATION', 'COMPANY', 'COMPENSATION', 'OTHER')",
            name="ck_relevance_mark_reason",
        ),
        Index("ix_relevance_mark_opportunity_marked_at", "opportunity_id", "marked_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    profile_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="SET NULL"),
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opportunity: Mapped[OpportunityModel] = relationship()


class SourceOccurrenceModel(Base):
    __tablename__ = "source_occurrence"
    __table_args__ = (
        UniqueConstraint("raw_item_id", name="uq_source_occurrence_raw_item"),
        Index(
            "uq_source_occurrence_source_external",
            "source_definition_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "uq_source_occurrence_source_url_fallback",
            "source_definition_id",
            "normalized_source_url",
            unique=True,
            postgresql_where=text(
                "external_id IS NULL AND normalized_source_url IS NOT NULL"
            ),
        ),
        Index("ix_source_occurrence_source_url", "source_url"),
        Index("ix_source_occurrence_normalized_url", "normalized_source_url"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(512))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    normalized_source_url: Mapped[str | None] = mapped_column(String(2048))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The run that last saw this occurrence, seeded by every normalization that touches
    #: it. Closure compares this against the two most recent complete runs of the source.
    last_seen_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_run.id", ondelete="SET NULL"),
    )
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When retention expired the raw body this occurrence came from, and `None` while it
    #: is still there. Read as a column rather than through the payload relationship so a
    #: list of occurrences never drags every raw payload into memory to answer it.
    payload_expired_at: Mapped[datetime | None] = column_property(
        select(RawItemPayloadModel.expired_at)
        .where(RawItemPayloadModel.raw_item_id == raw_item_id)
        .correlate_except(RawItemPayloadModel)
        .scalar_subquery()
    )
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="occurrences")
    normalization_results: Mapped[list["NormalizationResultModel"]] = relationship(
        back_populates="source_occurrence"
    )
    compensation_evidence: Mapped[list["OpportunityCompensationModel"]] = relationship(
        back_populates="source_occurrence"
    )


class NormalizationResultModel(Base):
    __tablename__ = "normalization_result"
    __table_args__ = (
        UniqueConstraint(
            "raw_item_id",
            "normalizer_version",
            name="uq_normalization_result_raw_version",
        ),
        CheckConstraint(
            "status IN ('SUCCEEDED', 'REVIEW_REQUIRED', 'FAILED')",
            name="ck_normalization_result_status",
        ),
        CheckConstraint(
            "identity_decision IN ('NEW', 'MERGED', 'REFRESHED', 'REVIEW')",
            name="ck_normalization_result_identity_decision",
        ),
        CheckConstraint(
            "(status = 'FAILED' AND error_summary IS NOT NULL "
            "AND identity_decision IS NULL AND opportunity_id IS NULL "
            "AND source_occurrence_id IS NULL) "
            "OR (status IN ('SUCCEEDED', 'REVIEW_REQUIRED') "
            "AND error_summary IS NULL AND identity_decision IS NOT NULL "
            "AND opportunity_id IS NOT NULL "
            "AND source_occurrence_id IS NOT NULL)",
            name="ck_normalization_result_outcome",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opportunity_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
    )
    source_occurrence_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.source_occurrence.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_decision: Mapped[str | None] = mapped_column(String(16))
    reasons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opportunity: Mapped[OpportunityModel | None] = relationship(
        back_populates="normalization_results"
    )
    source_occurrence: Mapped[SourceOccurrenceModel | None] = relationship(
        back_populates="normalization_results"
    )


class OpportunityCompensationModel(Base):
    __tablename__ = "opportunity_compensation"
    __table_args__ = (
        UniqueConstraint(
            "source_occurrence_id",
            name="uq_opportunity_compensation_source_occurrence",
        ),
        CheckConstraint(
            "amount_min IS NOT NULL OR amount_max IS NOT NULL",
            name="ck_opportunity_compensation_amount_present",
        ),
        CheckConstraint(
            "amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max",
            name="ck_opportunity_compensation_range",
        ),
        CheckConstraint(
            "period IN ('YEAR', 'MONTH', 'WEEK', 'DAY', 'HOUR', 'UNKNOWN')",
            name="ck_opportunity_compensation_period",
        ),
        CheckConstraint(
            "gross_net IN ('GROSS', 'NET', 'UNKNOWN')",
            name="ck_opportunity_compensation_gross_net",
        ),
        Index("ix_opportunity_compensation_currency_period", "currency", "period"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    gross_net: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN"
    )
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_source: Mapped[str | None] = mapped_column(String(512))
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_occurrence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.source_occurrence.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="compensations")
    source_occurrence: Mapped[SourceOccurrenceModel] = relationship(
        back_populates="compensation_evidence"
    )


class OpportunitySkillModel(Base):
    __tablename__ = "opportunity_skill"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "canonical_name",
            "taxonomy_version",
            name="uq_opportunity_skill_opportunity_name_taxonomy",
        ),
        CheckConstraint(
            "requirement IN ('REQUIRED', 'PREFERRED', 'UNKNOWN')",
            name="ck_opportunity_skill_requirement",
        ),
        Index("ix_opportunity_skill_requirement", "requirement"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    requirement: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN"
    )
    evidence: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="skills")
