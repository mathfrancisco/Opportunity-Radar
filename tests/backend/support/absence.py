"""Absence is clock based (R55-D5): tests that need a posting to count as absent age it."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import SourceOccurrenceModel


def age_occurrences(
    session: Session,
    source_ids: Iterable[UUID],
    *,
    external_ids: Iterable[str] | None = None,
    hours: int = 25,
) -> None:
    """Move `last_seen_at` of the sources' occurrences back by `hours`, then commit."""
    statement = update(SourceOccurrenceModel).where(
        SourceOccurrenceModel.source_definition_id.in_(list(source_ids))
    )
    if external_ids is not None:
        statement = statement.where(SourceOccurrenceModel.external_id.in_(list(external_ids)))
    session.execute(
        statement.values(last_seen_at=SourceOccurrenceModel.last_seen_at - timedelta(hours=hours))
    )
    session.commit()
