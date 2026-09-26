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
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
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
    """Confirming this pair would create or extend a `duplicate_of` cycle.

    Covers a direct two-node cycle (A absorbed into B, then B into A), a longer chain
    that would loop back, and confirming a pair where either side is already merged
    into a different opportunity — `duplicate_of` is permanent once set, so only two
    still-root opportunities can ever be merged by `confirm_duplicate`.
    """


@dataclass(frozen=True, slots=True)
class _OrderedPair:
    lower_id: UUID
    higher_id: UUID


def _ordered_pair(first: UUID, second: UUID) -> _OrderedPair:
    return _OrderedPair(first, second) if first < second else _OrderedPair(second, first)


def resolve_survivor(
    first: OpportunityModel, second: OpportunityModel
) -> tuple[OpportunityModel, OpportunityModel]:
    """Resolve survivor consistently: oldest row, then lower UUID on a timestamp tie."""
    if (first.created_at, first.id) <= (second.created_at, second.id):
        return first, second
    return second, first


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
        lower_opportunity = opportunity if opportunity.id == pair.lower_id else match
        higher_opportunity = match if lower_opportunity is opportunity else opportunity
        existing = session.scalar(
            select(DuplicateCandidateModel).where(
                DuplicateCandidateModel.opportunity_id == pair.lower_id,
                DuplicateCandidateModel.duplicate_opportunity_id == pair.higher_id,
            )
        )
        if existing is not None:
            if existing.status == "REJECTED" and (
                existing.rejected_version_opportunity != lower_opportunity.version
                or existing.rejected_version_duplicate_opportunity
                != higher_opportunity.version
            ):
                # A material change (either side's `version` moved) on a previously
                # rejected pair: the rejection was contextualized by those versions, so
                # it no longer suppresses this pair. Resurrect the same row instead of
                # inserting a duplicate, so history (who rejected it, when) is kept.
                existing.status = "PENDING"
                existing.decided_by = None
                existing.decided_at = None
                existing.rejected_version_opportunity = None
                existing.rejected_version_duplicate_opportunity = None
                created.append(existing)
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

    survivor, absorbed = resolve_survivor(first, second)
    if (
        survivor.version != expected_version_survivor
        or absorbed.version != expected_version_absorbed
    ):
        raise OpportunityVersionConflictError(
            "opportunity version is stale for confirm_duplicate"
        )

    if absorbed.id == survivor.id:
        raise DuplicateCycleError("cannot merge an opportunity into itself")
    # `duplicate_of` is permanent once set (F20-26's merge contract): an opportunity is
    # merged at most once. Requiring both sides to still be roots here is what blocks
    # every multi-hop shape — A absorbed into B then B into A, a longer chain that would
    # loop back, and re-merging a side that was already absorbed by a *different* pair
    # in the meantime — without needing to walk the `duplicate_of` chain by hand.
    if survivor.duplicate_of is not None:
        raise DuplicateCycleError(
            "survivor is already absorbed into another opportunity; "
            "resolve against its current root instead"
        )
    if absorbed.duplicate_of is not None:
        raise DuplicateCycleError(
            "the opportunity to absorb is already merged into another opportunity"
        )

    survivor_active = _has_active_application(session, survivor.id)
    absorbed_active = _has_active_application(session, absorbed.id)
    if survivor_active and absorbed_active:
        raise DuplicateConflictError(
            "both opportunities have an active application; resolve manually"
        )
    moved_applications = 0
    if absorbed_active and not survivor_active:
        application_result = cast(
            CursorResult[Any],
            session.execute(
                update(ApplicationProcessModel)
                .where(
                    ApplicationProcessModel.opportunity_id == absorbed.id,
                    ApplicationProcessModel.status == "ACTIVE",
                )
                .values(opportunity_id=survivor.id)
            ),
        )
        moved_applications = application_result.rowcount or 0

    occurrence_result = cast(
        CursorResult[Any],
        session.execute(
            update(SourceOccurrenceModel)
            .where(SourceOccurrenceModel.opportunity_id == absorbed.id)
            .values(opportunity_id=survivor.id)
        ),
    )
    moved_occurrences = occurrence_result.rowcount or 0

    if moved_applications or moved_occurrences:
        survivor.version += 1
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
    """Record the pair as `REJECTED`, contextualized by both opportunities' `version`.

    Idempotent on repeat rejection. The pair stays suppressed only while neither
    opportunity's `version` changes afterwards — `find_title_location_window_candidates`
    compares the current versions against what is stored here and resurfaces the pair
    once either side has a material change, instead of suppressing it forever.
    """
    candidate = session.get(DuplicateCandidateModel, candidate_id)
    if candidate is None:
        raise DuplicateCandidateNotFoundError(str(candidate_id))
    if candidate.status == "REJECTED":
        return candidate
    if candidate.status == "CONFIRMED":
        raise ValueError("cannot reject an already-confirmed duplicate candidate")
    lower = session.get(OpportunityModel, candidate.opportunity_id)
    higher = session.get(OpportunityModel, candidate.duplicate_opportunity_id)
    if lower is None or higher is None:
        raise DuplicateCandidateNotFoundError(str(candidate_id))
    candidate.status = "REJECTED"
    candidate.decided_by = decided_by
    candidate.decided_at = datetime.now(UTC)
    candidate.rejected_version_opportunity = lower.version
    candidate.rejected_version_duplicate_opportunity = higher.version
    session.commit()
    session.refresh(candidate)
    return candidate
