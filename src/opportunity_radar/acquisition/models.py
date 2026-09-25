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
    last_http_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
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
            "execution_trigger IN ('ON_DEMAND', 'SCHEDULED')",
            name="ck_source_run_execution_trigger",
        ),
        CheckConstraint(
            "items_seen >= 0 AND items_persisted >= 0 AND items_skipped >= 0 "
            "AND items_invalid >= 0 AND http_requests >= 0 AND retry_count >= 0 "
            "AND rate_limit_events >= 0",
            name="ck_source_run_counters",
        ),
        CheckConstraint(
            "credits_used >= 0",
            name="ck_source_run_credits_used",
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
    execution_trigger: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="ON_DEMAND",
        server_default=text("'ON_DEMAND'"),
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
    rate_limit_events: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    #: Provider credits spent by this run (e.g. Tavily's usage.credits). A different unit
    #: from http_requests/retry_count, which count HTTP calls regardless of what a source
    #: charges per call (F20-43).
    credits_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(Text)
    checkpoint_before: Mapped[str | None] = mapped_column(Text)
    checkpoint_after: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(255))
    #: What the source's own API announced the board holds, when it said so.
    items_announced: Mapped[int | None] = mapped_column(Integer)
    #: Whether this run read the whole board. Only a complete run may close a job that
    #: stopped appearing (see `opportunity_radar.acquisition.domain.evaluate_completeness`).
    complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
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
    # Joined rather than lazy: every reader of an envelope that still has its content
    # wants the content, and the pair is what the normalizer was always given.
    payload_record: Mapped["RawItemPayloadModel | None"] = relationship(
        back_populates="raw_item",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )

    @property
    def payload(self) -> dict[str, Any] | None:
        """The collected content, or `None` once retention has expired it.

        Absent content is a state of the evidence, not a failure to read it: the envelope
        above — source, run, identity and hash — is what proves the acquisition happened,
        and it outlives the body.
        """
        record = self.payload_record
        return None if record is None else record.payload

    @property
    def payload_retained(self) -> bool:
        record = self.payload_record
        return record is not None and record.payload is not None

    @property
    def payload_expired_at(self) -> datetime | None:
        record = self.payload_record
        return None if record is None else record.expired_at


class RawItemPayloadModel(Base):
    """The body of one raw item, kept apart from the envelope that must never expire."""

    __tablename__ = "raw_item_payload"
    __table_args__ = (
        CheckConstraint(
            "(payload IS NOT NULL AND expired_at IS NULL) "
            "OR (payload IS NULL AND expired_at IS NOT NULL)",
            name="ck_raw_item_payload_expiry",
        ),
        {"schema": "acquisition"},
    )

    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # `none_as_null` so that clearing the body writes SQL NULL rather than a JSON `null`:
    # an expired payload must be absent, not a document whose content happens to be null.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    stored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_policy_version: Mapped[str | None] = mapped_column(String(32))
    raw_item: Mapped[RawItemModel] = relationship(back_populates="payload_record")


class PayloadRetentionEventModel(Base):
    """Append-only record of every expiry, so a missing body is always accounted for."""

    __tablename__ = "payload_retention_event"
    __table_args__ = (
        UniqueConstraint("raw_item_id", name="uq_payload_retention_event_raw_item"),
        Index("ix_payload_retention_event_expired_at", "expired_at"),
        {"schema": "acquisition"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    expired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    retention_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
        nullable=False,
    )


class SourceAlertIncidentModel(Base):
    """One episode of a source being down, from the alert to its recovery.

    The incident is the unit an operator reads and the unit deduplication is written
    against: while one is open, further failures of the same source add nothing to send.
    """

    __tablename__ = "source_alert_incident"
    __table_args__ = (
        CheckConstraint(
            "alert_delivery IN ('PENDING', 'WEBHOOK', 'LOG_ONLY', 'FAILED')",
            name="ck_source_alert_incident_delivery",
        ),
        CheckConstraint(
            "recovery_delivery IS NULL OR recovery_delivery IN "
            "('WEBHOOK', 'LOG_ONLY', 'FAILED')",
            name="ck_source_alert_incident_recovery_delivery",
        ),
        CheckConstraint(
            "consecutive_failures > 0", name="ck_source_alert_incident_failures"
        ),
        Index(
            "uq_source_alert_incident_open",
            "source_definition_id",
            unique=True,
            postgresql_where=text("recovered_at IS NULL"),
        ),
        Index("ix_source_alert_incident_source_opened", "source_definition_id", "opened_at"),
        {"schema": "acquisition"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opened_by_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("acquisition.source_run.id", ondelete="SET NULL")
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(Text)
    alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alert_delivery: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_by_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("acquisition.source_run.id", ondelete="SET NULL")
    )
    recovery_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_delivery: Mapped[str | None] = mapped_column(String(16))
    correlation_id: Mapped[str | None] = mapped_column(String(255))


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


class SourceProbeModel(Base):
    """One live test of a source's collector against its public endpoint.

    A probe proves the collector understands the endpoint; it never keeps what it read.
    Every attempt is written, passed or failed, because a confirmed evidence status has
    to point at the attempt that produced it, and a failed one is what explains why a
    source is still unverified.
    """

    __tablename__ = "source_probe"
    __table_args__ = (
        CheckConstraint(
            "requested_by IN ('interface', 'script')",
            name="ck_source_probe_requested_by",
        ),
        CheckConstraint(
            "status IN ('RUNNING', 'PASSED', 'FAILED')",
            name="ck_source_probe_status",
        ),
        Index("ix_source_probe_source_started", "source_definition_id", "started_at"),
        {"schema": "acquisition"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    http_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    # True only when this attempt is what wrote the confirmed evidence: a probe that passed
    # after the source changed under it recorded nothing.
    evidence_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
