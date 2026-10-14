"""SQLAlchemy persistence models for the Dashboard context."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from opportunity_radar.platform.database import Base


class SavedSearchModel(Base):
    __tablename__ = "saved_search"
    __table_args__ = (Index("ix_saved_search_owner_sub", "owner_sub"), {"schema": "dashboard"})

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    #: Set exclusively from the validated server-side Clerk identity.
    owner_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    term: Mapped[str | None] = mapped_column(String)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
