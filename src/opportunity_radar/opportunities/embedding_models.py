"""Persistence of the opportunity embeddings (card F16-09).

Kept apart from `models.py` because nothing here is part of the opportunity itself: both
tables are derived, can be dropped and rebuilt by the worker, and never decide anything.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CHAR, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from opportunity_radar.opportunities.models import SCHEMA
from opportunity_radar.platform.database import Base
from opportunity_radar.platform.vector import Vector

#: The size of the `vector` column in migration 20260925_0024. The configured model must
#: produce vectors of exactly this size; another size is a migration and a full reindex.
EMBEDDING_COLUMN_DIMENSIONS = 1024


class OpportunityEmbeddingModel(Base):
    """The vector of one opportunity, and the identity of what produced it.

    A consumer only reads a row whose `model` and `text_version` are the configured ones
    and whose `content_version` is the opportunity's current version; anything else is a
    different vector space or a posting that no longer exists in that form.
    """

    __tablename__ = "opportunity_embedding"
    __table_args__ = {"schema": SCHEMA}

    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    text_version: Mapped[str] = mapped_column(String(64), nullable=False)
    text_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_COLUMN_DIMENSIONS), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OpportunityEmbeddingFailureModel(Base):
    """The last classified failure to embed one opportunity under a given identity.

    One row per opportunity. The attempt count only accumulates while the identity
    (model, text version, content version) stays the same: a new version of the posting
    or another model is a new question and starts from zero.
    """

    __tablename__ = "opportunity_embedding_failure"
    __table_args__ = {"schema": SCHEMA}

    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_version: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    text_version: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_code: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = [
    "EMBEDDING_COLUMN_DIMENSIONS",
    "OpportunityEmbeddingFailureModel",
    "OpportunityEmbeddingModel",
]
