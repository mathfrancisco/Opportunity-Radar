from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opportunity_radar.platform.database import Base

SCHEMA = "company_radar"


class Company(Base):
    __tablename__ = "company"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_company_normalized_name"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(253), unique=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    radar_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    verification_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    aliases: Mapped[list[CompanyAlias]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    sources: Mapped[list[CompanySource]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanyAlias(Base):
    __tablename__ = "company_alias"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "normalized_alias",
            name="uq_company_alias_company_normalized",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.company.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company: Mapped[Company] = relationship(back_populates="aliases")


class CompanySource(Base):
    __tablename__ = "company_source"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_type",
            "endpoint",
            name="uq_company_source_company_type_endpoint",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_company_source_confidence",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.company.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    external_key: Mapped[str | None] = mapped_column(String(255))
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unverified"
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    verification_method: Mapped[str | None] = mapped_column(String(50))
    evidence_note: Mapped[str | None] = mapped_column(Text)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship(back_populates="sources")


class CompanyImportBatch(Base):
    __tablename__ = "company_import_batch"
    __table_args__ = (
        UniqueConstraint("file_hash", name="uq_company_import_batch_file_hash"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    report: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issues: Mapped[list[CompanyImportIssue]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class CompanyImportIssue(Base):
    __tablename__ = "company_import_issue"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(f"{SCHEMA}.company_import_batch.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    batch: Mapped[CompanyImportBatch] = relationship(back_populates="issues")
