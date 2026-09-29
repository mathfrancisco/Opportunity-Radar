"""Persistence models for observed worker-job execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from opportunity_radar.platform.database import Base


class WorkerJobStateModel(Base):
    __tablename__ = "worker_job_state"
    __table_args__ = {"schema": "platform"}

    job_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_duration_ms: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)


class WorkerPassHistoryModel(Base):
    """One row per pass of a worker job: what the single-row state above overwrites."""

    __tablename__ = "worker_pass_history"
    __table_args__ = (
        Index("ix_worker_pass_history_job_started", "job_name", "started_at"),
        {"schema": "platform"},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_name: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool | None] = mapped_column(Boolean)
    #: Sources whose schedule was DUE in this pass (collection job only).
    due_sources: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
