"""Candidate detection and human-confirmed merge for republished postings (F20-26).

The fingerprint deliberately includes the publication day so a republication is not
silently merged into the original; the side effect is that the same vacancy posted on a
company board and on a broad source, days apart, becomes two opportunities. This module
finds those pairs and lets an operator confirm or reject them — nothing here merges
anything on its own.

Fase 20 scope (SPEC 43 SS9): only the `title_location_window` rule runs. `embedding`
stays in the status enum for a later phase with no generator here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import (
    DuplicateCandidateModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.pipeline.models import ApplicationProcessModel

#: A confirmed pair is never suggested again outside this window (SPEC 43 SS9).
TITLE_LOCATION_WINDOW_DAYS = 14


class DuplicateCandidateNotFoundError(LookupError):
    pass


class DuplicateConflictError(Exception):
    """Both opportunities in the pair have an active application.

    The merge stops here rather than pick one side or close the other one for the
    operator; a human resolves the conflict first.
    """


class DuplicateCycleError(ValueError):
    """Confirming this pair would make `duplicate_of` point back on itself."""


@dataclass(frozen=True, slots=True)
class _OrderedPair:
    lower_id: UUID
    higher_id: UUID


def _ordered_pair(first: UUID, second: UUID) -> _OrderedPair:
    return _OrderedPair(first, second) if first < second else _OrderedPair(second, first)


def find_title_location_window_candidates(
    session: Session, opportunity: OpportunityModel
) -> list[DuplicateCandidateModel]:
    """Same canonical company, title and location, published within 14 days.

    Never merges anything: every match becomes a `PENDING` row, skipping pairs already
    recorded (in any status — a rejected pair is not re-suggested unchanged).
    """
    if opportunity.duplicate_of is not None:
        return []
    if not (
        opportunity.normalized_title
        and opportunity.normalized_location
        and opportunity.normalized_company_name
        and opportunity.published_at is not None
    ):
        return []

    window_start = opportunity.published_at - timedelta(days=TITLE_LOCATION_WINDOW_DAYS)
    window_end = opportunity.published_at + timedelta(days=TITLE_LOCATION_WINDOW_DAYS)
    matches = session.scalars(
        select(OpportunityModel).where(
            OpportunityModel.id != opportunity.id,
            OpportunityModel.duplicate_of.is_(None),
            OpportunityModel.normalized_company_name
            == opportunity.normalized_company_name,
            OpportunityModel.normalized_title == opportunity.normalized_title,
            OpportunityModel.normalized_location == opportunity.normalized_location,
            OpportunityModel.published_at.is_not(None),
            OpportunityModel.published_at >= window_start,
            OpportunityModel.published_at <= window_end,
        )
    ).all()

    created: list[DuplicateCandidateModel] = []
    for match in matches:
        pair = _ordered_pair(opportunity.id, match.id)
        existing = session.scalar(
            select(DuplicateCandidateModel).where(
                DuplicateCandidateModel.opportunity_id == pair.lower_id,
                DuplicateCandidateModel.duplicate_opportunity_id == pair.higher_id,
            )
        )
        if existing is not None:
            continue
        candidate = DuplicateCandidateModel(
            opportunity_id=pair.lower_id,
            duplicate_opportunity_id=pair.higher_id,
            rule="title_location_window",
            status="PENDING",
        )
        session.add(candidate)
        created.append(candidate)
    return created


def _has_active_application(session: Session, opportunity_id: UUID) -> bool:
    return (
        session.scalar(
            select(ApplicationProcessModel.id).where(
                ApplicationProcessModel.opportunity_id == opportunity_id,
                ApplicationProcessModel.status == "ACTIVE",
            )
        )
        is not None
    )


def confirm_duplicate(
    session: Session,
    candidate_id: UUID,
    *,
    expected_version_survivor: int,
    expected_version_absorbed: int,
    decided_by: str,
) -> DuplicateCandidateModel:
    """Merge the pair into the older opportunity.

    Idempotent: confirming an already-`CONFIRMED` candidate returns the same resolution
    without re-checking versions or mutating anything again. A stale version on the
    first confirmation raises `OpportunityVersionConflictError` from the caller's own
    version-conflict vocabulary — this module raises the plain `ValueError` subclasses
    below and lets the caller translate them, matching `OpportunityService.transition`.
    """
    from opportunity_radar.opportunities.service import OpportunityVersionConflictError

    candidate = session.get(DuplicateCandidateModel, candidate_id)
    if candidate is None:
        raise DuplicateCandidateNotFoundError(str(candidate_id))
    if candidate.status == "CONFIRMED":
        return candidate
    if candidate.status == "REJECTED":
        raise ValueError("cannot confirm a rejected duplicate candidate")

    first = session.get(OpportunityModel, candidate.opportunity_id)
    second = session.get(OpportunityModel, candidate.duplicate_opportunity_id)
    if first is None or second is None:
        raise DuplicateCandidateNotFoundError(str(candidate_id))

    survivor, absorbed = (first, second) if first.created_at <= second.created_at else (
        second,
        first,
    )
    if (
        survivor.version != expected_version_survivor
        or absorbed.version != expected_version_absorbed
    ):
        raise OpportunityVersionConflictError(
            "opportunity version is stale for confirm_duplicate"
        )

    if survivor.duplicate_of == absorbed.id or absorbed.id == survivor.id:
        raise DuplicateCycleError("confirming this pair would create a duplicate_of cycle")

    survivor_active = _has_active_application(session, survivor.id)
    absorbed_active = _has_active_application(session, absorbed.id)
    if survivor_active and absorbed_active:
        raise DuplicateConflictError(
            "both opportunities have an active application; resolve manually"
        )
    if absorbed_active and not survivor_active:
        session.execute(
            update(ApplicationProcessModel)
            .where(
                ApplicationProcessModel.opportunity_id == absorbed.id,
                ApplicationProcessModel.status == "ACTIVE",
            )
            .values(opportunity_id=survivor.id)
        )

    session.execute(
        update(SourceOccurrenceModel)
        .where(SourceOccurrenceModel.opportunity_id == absorbed.id)
        .values(opportunity_id=survivor.id)
    )

    absorbed.duplicate_of = survivor.id
    absorbed.version = absorbed.version + 1
    candidate.status = "CONFIRMED"
    candidate.decided_by = decided_by
    candidate.decided_at = datetime.now(UTC)
    session.commit()
    session.refresh(candidate)
    return candidate


def reject_duplicate(
    session: Session, candidate_id: UUID, *, decided_by: str
) -> DuplicateCandidateModel:
    """Record the pair as `REJECTED`. Idempotent on repeat rejection."""
    candidate = session.get(DuplicateCandidateModel, candidate_id)
    if candidate is None:
        raise DuplicateCandidateNotFoundError(str(candidate_id))
    if candidate.status == "REJECTED":
        return candidate
    if candidate.status == "CONFIRMED":
        raise ValueError("cannot reject an already-confirmed duplicate candidate")
    candidate.status = "REJECTED"
    candidate.decided_by = decided_by
    candidate.decided_at = datetime.now(UTC)
    session.commit()
    session.refresh(candidate)
    return candidate
