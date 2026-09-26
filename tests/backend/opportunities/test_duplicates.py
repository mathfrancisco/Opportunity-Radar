"""F20-26: candidate detection (no vectorial signal) and the confirm/reject merge.

Only `title_location_window` runs in Fase 20 (SPEC 43 SS9); `embedding` stays in the
status enum with no generator. Nothing here merges anything by itself — every match is a
`PENDING` row an operator must confirm.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.opportunities.duplicates import (
    DuplicateConflictError,
    DuplicateCycleError,
    confirm_duplicate,
    find_title_location_window_candidates,
    reject_duplicate,
)
from opportunity_radar.opportunities.models import (
    DuplicateCandidateModel,
    OpportunityModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.service import OpportunityVersionConflictError
from opportunity_radar.pipeline.domain import ApplicationStage
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.pipeline.service import PipelineService
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _opportunity(
    *,
    created_at: datetime,
    published_at: datetime | None,
    title: str = "backend engineer",
    company: str = "acme",
    location: str = "sao paulo",
) -> OpportunityModel:
    return OpportunityModel(
        id=uuid4(),
        fingerprint=uuid4().hex + uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Backend Engineer",
        normalized_title=title,
        normalized_company_name=company,
        normalized_location=location,
        company_name=company,
        location_text=location,
        work_mode="UNKNOWN",
        seniority="UNKNOWN",
        contract_type="UNKNOWN",
        lifecycle_status="ACTIVE",
        published_at=published_at,
        created_at=created_at,
        version=1,
    )


def _profile_version(session: Session) -> ProfileVersionModel:
    profile = session.scalar(select(CareerProfileModel).limit(1))
    if profile is None:
        profile = CareerProfileModel(version=1)
        session.add(profile)
        session.flush()
    version = ProfileVersionModel(
        career_profile_id=profile.id,
        number=(
            session.scalar(
                select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                    ProfileVersionModel.career_profile_id == profile.id
                )
            )
            or 0
        )
        + 1,
        status="DRAFT",
    )
    session.add(version)
    session.flush()
    session.add(EmploymentPreferenceModel(profile_version_id=version.id))
    session.flush()
    return version


def _occurrence_chain(session: Session, opportunity_id) -> SourceOccurrenceModel:
    """A minimal source/run/raw-item chain, only to satisfy `SourceOccurrenceModel`'s
    foreign keys — not itself under test here."""
    marker = uuid4().hex[:8]
    source = SourceDefinitionModel(
        source_type="manual", name=f"duplicate-test {marker}", enabled=False
    )
    session.add(source)
    session.flush()
    run = SourceRunModel(
        source_definition_id=source.id,
        execution_trigger="ON_DEMAND",
        status="SUCCEEDED",
        started_at=NOW,
        finished_at=NOW,
        complete=True,
    )
    session.add(run)
    session.flush()
    raw_item = RawItemModel(
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=f"probe-{marker}",
        identity_key=f"external:probe-{marker}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    session.add(raw_item)
    session.flush()
    occurrence = SourceOccurrenceModel(
        opportunity_id=opportunity_id,
        raw_item_id=raw_item.id,
        source_definition_id=source.id,
        external_id=raw_item.external_id,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(occurrence)
    session.commit()
    return occurrence


def _cleanup(session: Session, opportunity_ids: list) -> None:
    session.execute(
        delete(DuplicateCandidateModel).where(
            DuplicateCandidateModel.opportunity_id.in_(opportunity_ids)
            | DuplicateCandidateModel.duplicate_opportunity_id.in_(opportunity_ids)
        )
    )
    session.execute(
        delete(ApplicationProcessModel).where(
            ApplicationProcessModel.opportunity_id.in_(opportunity_ids)
        )
    )
    session.execute(
        delete(RelevanceMarkModel).where(
            RelevanceMarkModel.opportunity_id.in_(opportunity_ids)
        )
    )
    occurrences = session.scalars(
        select(SourceOccurrenceModel).where(
            SourceOccurrenceModel.opportunity_id.in_(opportunity_ids)
        )
    ).all()
    raw_item_ids = [occurrence.raw_item_id for occurrence in occurrences]
    source_definition_ids = [occurrence.source_definition_id for occurrence in occurrences]
    session.execute(
        delete(SourceOccurrenceModel).where(
            SourceOccurrenceModel.opportunity_id.in_(opportunity_ids)
        )
    )
    session.execute(
        delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids))
    )
    if raw_item_ids:
        session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_item_ids)))
    if source_definition_ids:
        session.execute(
            delete(SourceRunModel).where(
                SourceRunModel.source_definition_id.in_(source_definition_ids)
            )
        )
        session.execute(
            delete(SourceDefinitionModel).where(
                SourceDefinitionModel.id.in_(source_definition_ids)
            )
        )
    session.commit()


def test_title_location_window_matches_within_14_days() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=10), published_at=NOW)
        newer = _opportunity(
            created_at=NOW - timedelta(days=1),
            published_at=NOW + timedelta(days=10),
        )
        session.add_all([older, newer])
        session.commit()
        try:
            created = find_title_location_window_candidates(session, newer)
            session.commit()

            assert len(created) == 1
            candidate = created[0]
            assert candidate.rule == "title_location_window"
            assert candidate.status == "PENDING"
            assert {candidate.opportunity_id, candidate.duplicate_opportunity_id} == {
                older.id,
                newer.id,
            }
        finally:
            _cleanup(session, [older.id, newer.id])


def test_title_location_window_ignores_different_company() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        first = _opportunity(created_at=NOW, published_at=NOW, company="acme")
        second = _opportunity(
            created_at=NOW, published_at=NOW + timedelta(days=1), company="other-co"
        )
        session.add_all([first, second])
        session.commit()
        try:
            created = find_title_location_window_candidates(session, second)
            session.commit()
            assert created == []
        finally:
            _cleanup(session, [first.id, second.id])


def test_title_location_window_ignores_publications_outside_14_days() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        first = _opportunity(created_at=NOW, published_at=NOW)
        second = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=15))
        session.add_all([first, second])
        session.commit()
        try:
            created = find_title_location_window_candidates(session, second)
            session.commit()
            assert created == []
        finally:
            _cleanup(session, [first.id, second.id])


def test_confirm_duplicate_merges_and_preserves_provenance() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=5), published_at=NOW)
        newer = _opportunity(
            created_at=NOW, published_at=NOW + timedelta(days=1)
        )
        session.add_all([older, newer])
        session.commit()
        occurrence = _occurrence_chain(session, newer.id)
        try:
            [candidate] = find_title_location_window_candidates(session, newer)
            session.commit()

            confirmed = confirm_duplicate(
                session,
                candidate.id,
                expected_version_survivor=older.version,
                expected_version_absorbed=newer.version,
                decided_by="operator@example.com",
            )

            assert confirmed.status == "CONFIRMED"
            assert confirmed.decided_by == "operator@example.com"
            refreshed_newer = session.get(OpportunityModel, newer.id)
            assert refreshed_newer is not None
            assert refreshed_newer.duplicate_of == older.id
            refreshed_occurrence = session.get(SourceOccurrenceModel, occurrence.id)
            assert refreshed_occurrence is not None
            assert refreshed_occurrence.opportunity_id == older.id
        finally:
            _cleanup(session, [older.id, newer.id])


def test_reject_duplicate_does_not_resuggest_unchanged_pair() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=2), published_at=NOW)
        newer = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=1))
        session.add_all([older, newer])
        session.commit()
        try:
            [candidate] = find_title_location_window_candidates(session, newer)
            session.commit()

            rejected = reject_duplicate(
                session, candidate.id, decided_by="operator@example.com"
            )
            assert rejected.status == "REJECTED"

            re_detected = find_title_location_window_candidates(session, newer)
            session.commit()
            assert re_detected == []
        finally:
            _cleanup(session, [older.id, newer.id])


def test_confirm_duplicate_is_idempotent_on_retry() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=3), published_at=NOW)
        newer = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=1))
        session.add_all([older, newer])
        session.commit()
        try:
            [candidate] = find_title_location_window_candidates(session, newer)
            session.commit()

            first = confirm_duplicate(
                session,
                candidate.id,
                expected_version_survivor=older.version,
                expected_version_absorbed=newer.version,
                decided_by="operator@example.com",
            )
            # A retry with the (now stale) original versions still returns the same
            # resolution instead of raising a version conflict.
            second = confirm_duplicate(
                session,
                candidate.id,
                expected_version_survivor=older.version,
                expected_version_absorbed=newer.version,
                decided_by="operator@example.com",
            )
            assert first.id == second.id
            assert second.status == "CONFIRMED"
        finally:
            _cleanup(session, [older.id, newer.id])


def test_confirm_duplicate_rejects_stale_version() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=3), published_at=NOW)
        newer = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=1))
        session.add_all([older, newer])
        session.commit()
        try:
            [candidate] = find_title_location_window_candidates(session, newer)
            session.commit()

            with pytest.raises(OpportunityVersionConflictError):
                confirm_duplicate(
                    session,
                    candidate.id,
                    expected_version_survivor=older.version + 1,
                    expected_version_absorbed=newer.version,
                    decided_by="operator@example.com",
                )
        finally:
            _cleanup(session, [older.id, newer.id])


def test_two_active_applications_raise_conflict_without_partial_mutation() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=3), published_at=NOW)
        newer = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=1))
        session.add_all([older, newer])
        session.commit()
        profile_version = _profile_version(session)
        PipelineService(session).start(
            older.id, profile_version_id=profile_version.id, stage=ApplicationStage.APPLIED
        )
        PipelineService(session).start(
            newer.id, profile_version_id=profile_version.id, stage=ApplicationStage.APPLIED
        )
        try:
            [candidate] = find_title_location_window_candidates(session, newer)
            session.commit()

            with pytest.raises(DuplicateConflictError):
                confirm_duplicate(
                    session,
                    candidate.id,
                    expected_version_survivor=older.version,
                    expected_version_absorbed=newer.version,
                    decided_by="operator@example.com",
                )

            session.rollback()
            refreshed_candidate = session.get(DuplicateCandidateModel, candidate.id)
            refreshed_newer = session.get(OpportunityModel, newer.id)
            assert refreshed_candidate is not None
            assert refreshed_candidate.status == "PENDING"
            assert refreshed_newer is not None
            assert refreshed_newer.duplicate_of is None
        finally:
            _cleanup(session, [older.id, newer.id])


def test_duplicate_of_cycle_is_rejected() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        a = _opportunity(
            created_at=NOW - timedelta(days=1),
            published_at=NOW,
            title="a-title",
        )
        b = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=1))
        session.add_all([a, b])
        session.commit()
        try:
            # B already points to A (B was absorbed by A in a previous merge).
            b.duplicate_of = a.id
            session.commit()

            # A manufactured candidate row that would try to make A duplicate_of B,
            # reversing the direction and creating a two-node cycle.
            candidate = DuplicateCandidateModel(
                id=uuid4(),
                opportunity_id=min(a.id, b.id),
                duplicate_opportunity_id=max(a.id, b.id),
                rule="title_location_window",
                status="PENDING",
            )
            session.add(candidate)
            session.commit()

            # Force A to look older than B so confirm_duplicate would pick A as survivor
            # and try to set B.duplicate_of = A.id again... instead exercise the reverse:
            # confirm_duplicate always picks the older one as survivor, so make B look
            # older than A while B already has duplicate_of == A.id, which would demand
            # A.duplicate_of = B.id while B.duplicate_of == A.id already -> a cycle.
            b.created_at = NOW - timedelta(days=2)
            session.commit()

            with pytest.raises(DuplicateCycleError):
                confirm_duplicate(
                    session,
                    candidate.id,
                    expected_version_survivor=b.version,
                    expected_version_absorbed=a.version,
                    decided_by="operator@example.com",
                )
        finally:
            _cleanup(session, [a.id, b.id])


def test_confirm_duplicate_keeps_marks_on_the_absorbed_opportunity_without_promoting_them() -> (
    None
):
    """Marks/history are never lost, and an old mark of the absorbed opportunity never
    becomes a "current" mark of the survivor — confirm_duplicate does not touch
    `RelevanceMarkModel` at all, so nothing here is silently promoted or dropped."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        older = _opportunity(created_at=NOW - timedelta(days=4), published_at=NOW)
        newer = _opportunity(created_at=NOW, published_at=NOW + timedelta(days=1))
        session.add_all([older, newer])
        session.commit()
        mark = RelevanceMarkModel(opportunity_id=newer.id, relevant=True, reason="AREA")
        session.add(mark)
        session.commit()
        try:
            [candidate] = find_title_location_window_candidates(session, newer)
            session.commit()

            confirm_duplicate(
                session,
                candidate.id,
                expected_version_survivor=older.version,
                expected_version_absorbed=newer.version,
                decided_by="operator@example.com",
            )

            preserved = session.get(RelevanceMarkModel, mark.id)
            assert preserved is not None
            assert preserved.opportunity_id == newer.id  # still on the absorbed opportunity

            survivor_marks = session.scalars(
                select(RelevanceMarkModel).where(
                    RelevanceMarkModel.opportunity_id == older.id
                )
            ).all()
            assert survivor_marks == []  # never promoted to the survivor
        finally:
            _cleanup(session, [older.id, newer.id])
