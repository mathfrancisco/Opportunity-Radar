"""SQLAlchemy persistence models for the Opportunities context."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
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
    occurrences: Mapped[list["SourceOccurrenceModel"]] = relationship(
        back_populates="opportunity"
    )
    normalization_results: Mapped[list["NormalizationResultModel"]] = relationship(
        back_populates="opportunity"
    )


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
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="occurrences")
    normalization_results: Mapped[list["NormalizationResultModel"]] = relationship(
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
