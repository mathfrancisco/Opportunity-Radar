"""Database-backed proof that candidacies keep their history and their invariants."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.pipeline.domain import (
    ApplicationStage,
    ApplicationVersionConflictError,
    DuplicateActiveApplicationError,
    InvalidStageTransitionError,
    InvalidStartStageError,
)
from opportunity_radar.pipeline.models import ApplicationProcessModel, StageHistoryModel
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


def _fixtures(session: Session) -> tuple[OpportunityModel, ProfileVersionModel]:
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
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Pipeline role",
        normalized_title="pipeline role",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
    )
    session.add_all([version, opportunity])
    session.flush()
    # A version without its preference row cannot be loaded as a domain object, and the
    # pipeline service loads the profile before starting an application.
    session.add(EmploymentPreferenceModel(profile_version_id=version.id))
    session.commit()
    return opportunity, version


def test_starting_recording_and_closing_keeps_the_whole_history() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity, version = _fixtures(session)
        service = PipelineService(session)

        application = service.start(
            opportunity.id,
            profile_version_id=version.id,
            notes="Vaga veio pelo radar.",
        )
        assert application.current_stage == ApplicationStage.INTERESTED.value
        assert application.status == "ACTIVE"
        assert application.applied_at is None
        assert len(application.history) == 1
        assert application.history[0].from_stage is None

        # The service returns the same identity the session already holds, so the version
        # has to be read before the move to mean anything.
        version_before = application.version
        applied = service.transition(
            application.id,
            target=ApplicationStage.APPLIED,
            expected_version=version_before,
            reason="submitted",
        )
        assert applied.applied_at is not None
        assert applied.version == version_before + 1

        interviewing = service.transition(
            applied.id,
            target=ApplicationStage.INTERVIEW,
            expected_version=applied.version,
        )
        closed = service.transition(
            interviewing.id,
            target=ApplicationStage.REJECTED,
            expected_version=interviewing.version,
            notes="Escolheram outro candidato.",
        )

        assert closed.status == "CLOSED"
        assert closed.outcome == "REJECTED"
        assert closed.closed_at is not None
        # The applied timestamp is not rewritten by later moves.
        assert closed.applied_at == applied.applied_at

        history = [entry.to_stage for entry in closed.history]
        assert history == ["INTERESTED", "APPLIED", "INTERVIEW", "REJECTED"]
        assert [entry.from_stage for entry in closed.history] == [
            None,
            "INTERESTED",
            "APPLIED",
            "INTERVIEW",
        ]


def test_history_rows_cannot_be_edited() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity, version = _fixtures(session)
        application = PipelineService(session).start(
            opportunity.id, profile_version_id=version.id
        )
        entry = application.history[0]

        with pytest.raises(DBAPIError, match="immutable"):
            session.execute(
                StageHistoryModel.__table__.update()
                .where(StageHistoryModel.id == entry.id)
                .values(notes="rewritten")
            )
            session.flush()
        session.rollback()


def test_only_one_active_application_per_opportunity_and_profile() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity, version = _fixtures(session)
        service = PipelineService(session)
        first = service.start(opportunity.id, profile_version_id=version.id)

        with pytest.raises(DuplicateActiveApplicationError):
            service.start(opportunity.id, profile_version_id=version.id)

        service.transition(
            first.id,
            target=ApplicationStage.WITHDRAWN,
            expected_version=first.version,
        )
        # Closing frees the slot: applying again next cycle is a new application, not an
        # edit of the old one.
        again = service.start(opportunity.id, profile_version_id=version.id)
        assert again.id != first.id
        assert (
            session.scalar(
                select(func.count(ApplicationProcessModel.id)).where(
                    ApplicationProcessModel.opportunity_id == opportunity.id
                )
            )
            == 2
        )


def test_illegal_moves_and_stale_versions_are_refused() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity, version = _fixtures(session)
        service = PipelineService(session)
        application = service.start(opportunity.id, profile_version_id=version.id)

        with pytest.raises(InvalidStageTransitionError):
            service.transition(
                application.id,
                target=ApplicationStage.OFFER,
                expected_version=application.version,
            )

        with pytest.raises(ApplicationVersionConflictError):
            service.transition(
                application.id,
                target=ApplicationStage.APPLIED,
                expected_version=application.version + 5,
            )

        with pytest.raises(InvalidStartStageError):
            service.start(
                opportunity.id,
                profile_version_id=version.id,
                stage=ApplicationStage.OFFER,
            )


def test_next_action_is_editable_and_cleared_when_the_application_closes() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity, version = _fixtures(session)
        service = PipelineService(session)
        application = service.start(opportunity.id, profile_version_id=version.id)
        due = datetime.now(UTC) + timedelta(days=2)

        with_action = service.set_next_action(
            application.id,
            expected_version=application.version,
            next_action="Enviar follow-up ao recrutador",
            next_action_at=due,
            notes="Contato pelo LinkedIn.",
        )
        assert with_action.next_action == "Enviar follow-up ao recrutador"
        assert with_action.next_action_at is not None
        assert with_action.notes == "Contato pelo LinkedIn."

        closed = service.transition(
            with_action.id,
            target=ApplicationStage.WITHDRAWN,
            expected_version=with_action.version,
        )
        # A closed application owes nothing, so it leaves the follow-up count.
        assert closed.next_action is None
        assert closed.next_action_at is None
        assert closed.notes == "Contato pelo LinkedIn."
