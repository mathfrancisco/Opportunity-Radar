"""SQLAlchemy persistence models for the Acquisition context."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opportunity_radar.platform.database import Base


class SourceDefinitionModel(Base):
    __tablename__ = "source_definition"
    __table_args__ = (
        CheckConstraint("priority >= 0", name="ck_source_definition_priority"),
        CheckConstraint(
            "evidence_status IN ('unverified', 'confirmed', 'ats_identified', "
            "'careers_page', 'dynamic_review', 'redirect_review', 'access_pending')",
            name="ck_source_definition_evidence_status",
        ),
        Index("ix_source_definition_company_source", "company_source_id"),
        UniqueConstraint("source_type", "name", name="uq_source_definition_type_name"),
        {"schema": "acquisition"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_source_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("company_radar.company_source.id", ondelete="SET NULL"),
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    rate_limit_policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    evidence_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terms_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    collector_local_tested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    last_health_status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    runs: Mapped[list["SourceRunModel"]] = relationship(
        back_populates="source_definition"
    )
    checkpoint: Mapped["SourceCheckpointModel | None"] = relationship(
        back_populates="source_definition", uselist=False, cascade="all, delete-orphan"
    )


class SourceRunModel(Base):
    __tablename__ = "source_run"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL', "
            "'FAILED', 'CANCELLED')",
            name="ck_source_run_status",
        ),
        CheckConstraint(
            "items_seen >= 0 AND items_persisted >= 0 AND items_skipped >= 0 "
            "AND items_invalid >= 0 AND http_requests >= 0 AND retry_count >= 0",
            name="ck_source_run_counters",
        ),
        Index("ix_source_run_source_started", "source_definition_id", "started_at"),
        Index(
            "uq_source_run_active",
            "source_definition_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'RUNNING')"),
        ),
        {"schema": "acquisition"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_persisted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(Text)
    checkpoint_before: Mapped[str | None] = mapped_column(Text)
    checkpoint_after: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(255))
    source_definition: Mapped[SourceDefinitionModel] = relationship(back_populates="runs")
    raw_items: Mapped[list["RawItemModel"]] = relationship(
        back_populates="source_run"
    )


class RawItemModel(Base):
    """Append-only evidence received from a collector."""

    __tablename__ = "raw_item"
    __table_args__ = (
        UniqueConstraint(
            "source_definition_id",
            "identity_key",
            "payload_hash",
            name="uq_raw_item_source_identity_hash",
        ),
        Index("ix_raw_item_source_run", "source_run_id"),
        {"schema": "acquisition"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_run.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(512))
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    identity_key: Mapped[str] = mapped_column(String(2048), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    parser_version: Mapped[str | None] = mapped_column(String(128))
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    source_run: Mapped[SourceRunModel] = relationship(back_populates="raw_items")


class SourceCheckpointModel(Base):
    __tablename__ = "source_checkpoint"
    __table_args__ = ({"schema": "acquisition"},)

    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
        primary_key=True,
    )
    checkpoint_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="cursor"
    )
    cursor: Mapped[str | None] = mapped_column(Text)
    updated_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    etag: Mapped[str | None] = mapped_column(Text)
    last_modified: Mapped[str | None] = mapped_column(Text)
    promoted_by_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_run.id", ondelete="RESTRICT"),
    )
    promoted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_definition: Mapped[SourceDefinitionModel] = relationship(
        back_populates="checkpoint"
    )


@event.listens_for(RawItemModel, "before_update")
def prevent_raw_item_mutation(_: object, __: object, ___: object) -> None:
    """Raw evidence is append-only; a changed payload creates a new row."""
    raise ValueError("RawItem is immutable")
