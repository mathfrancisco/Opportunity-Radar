"""Persistence for applications and their immutable stage history.

Tables follow section 19 of docs/11-modelagem-dados.md, which places them in the `crm`
schema created by the first migration. The module is named after the bounded context in
docs/06, so the code says pipeline and the database says crm on purpose.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opportunity_radar.platform.database import Base

SCHEMA = "crm"

_STAGES = (
    "'INTERESTED', 'APPLIED', 'SCREENING', 'INTERVIEW', 'TECHNICAL', 'FINAL', "
    "'OFFER', 'REJECTED', 'WITHDRAWN', 'CLOSED'"
)
_OUTCOMES = "'REJECTED', 'WITHDRAWN', 'CLOSED'"


class ApplicationProcessModel(Base):
    """One candidacy. Mutable by design — the audit trail lives in the history table."""

    __tablename__ = "application_process"
    __table_args__ = (
        CheckConstraint(f"current_stage IN ({_STAGES})", name="ck_application_stage"),
        CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="ck_application_status"),
        CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_OUTCOMES})", name="ck_application_outcome"
        ),
        CheckConstraint(
            "(status = 'CLOSED') = (closed_at IS NOT NULL)",
            name="ck_application_closed_at",
        ),
        CheckConstraint(
            "(status = 'CLOSED') = (outcome IS NOT NULL)",
            name="ck_application_closed_outcome",
        ),
        CheckConstraint("version > 0", name="ck_application_version"),
        # One active application per opportunity and profile version, section 60 of the
        # roadmap. A closed one does not block starting again, which is what reapplying
        # in a later cycle means.
        Index(
            "uq_application_active",
            "opportunity_id",
            "profile_version_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_application_stage_updated", "current_stage", "updated_at"),
        Index("ix_application_next_action_at", "next_action_at"),
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
    profile_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_stage: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    outcome: Mapped[str | None] = mapped_column(String(16))
    next_action: Mapped[str | None] = mapped_column(String(500))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    history: Mapped[list["StageHistoryModel"]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="StageHistoryModel.occurred_at",
    )


class StageHistoryModel(Base):
    """Append-only record of how the application reached its current stage.

    The current stage is derivable from the last entry, but it is also stored on the
    application: the history answers "how did we get here", the column answers "where are
    we" without replaying anything.
    """

    __tablename__ = "stage_history"
    __table_args__ = (
        CheckConstraint(f"to_stage IN ({_STAGES})", name="ck_stage_history_to_stage"),
        CheckConstraint(
            f"from_stage IS NULL OR from_stage IN ({_STAGES})",
            name="ck_stage_history_from_stage",
        ),
        CheckConstraint(
            "from_stage IS NULL OR from_stage <> to_stage",
            name="ck_stage_history_moves",
        ),
        CheckConstraint(
            "source IN ('MANUAL', 'SYSTEM')", name="ck_stage_history_source"
        ),
        Index("ix_stage_history_application", "application_id", "occurred_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    application_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.application_process.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Null on the first entry: the application did not come from anywhere.
    from_stage: Mapped[str | None] = mapped_column(String(16))
    to_stage: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="MANUAL")
    notes: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    application: Mapped[ApplicationProcessModel] = relationship(back_populates="history")
