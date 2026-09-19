"""Application service for the candidacy pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.pipeline.domain import (
    MAX_NEXT_ACTION_LENGTH,
    MAX_NOTE_LENGTH,
    ApplicationNotFoundError,
    ApplicationStage,
    ApplicationStatus,
    ApplicationVersionConflictError,
    DuplicateActiveApplicationError,
    normalized_text,
    status_for,
    validate_start,
    validate_transition,
)
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.pipeline.repository import PipelineRepository
from opportunity_radar.profile.service import ProfileService


class ApplicationOpportunityNotFoundError(LookupError):
    pass


class PipelineService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PipelineRepository(session)

    def start(
        self,
        opportunity_id: UUID,
        *,
        profile_version_id: UUID | None = None,
        stage: ApplicationStage = ApplicationStage.INTERESTED,
        next_action: str | None = None,
        next_action_at: datetime | None = None,
        notes: str | None = None,
    ) -> ApplicationProcessModel:
        """Start tracking a candidacy. The opportunity is untouched: it keeps its own
        lifecycle, and closing the application later will not close the posting."""
        validate_start(stage)
        opportunity = OpportunityRepository(self.session).get(opportunity_id)
        if opportunity is None:
            raise ApplicationOpportunityNotFoundError(str(opportunity_id))
        profile = (
            ProfileService(self.session).get_version(profile_version_id)
            if profile_version_id is not None
            else ProfileService(self.session).get_active()
        )
        existing = self.repository.get_active(
            opportunity_id=opportunity_id, profile_version_id=profile.id
        )
        if existing is not None:
            raise DuplicateActiveApplicationError(
                "this opportunity already has an active application for this profile"
            )

        started_at = datetime.now(UTC)
        normalized_notes = normalized_text(notes, MAX_NOTE_LENGTH)
        application = self.repository.add(
            opportunity_id=opportunity_id,
            profile_version_id=profile.id,
            stage=stage.value,
            status=status_for(stage).value,
            outcome=None,
            started_at=started_at,
            closed_at=None,
            applied_at=started_at if stage is ApplicationStage.APPLIED else None,
            next_action=normalized_text(next_action, MAX_NEXT_ACTION_LENGTH),
            next_action_at=next_action_at,
            notes=normalized_notes,
            history_notes=normalized_notes,
        )
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise DuplicateActiveApplicationError(
                "this opportunity already has an active application for this profile"
            ) from error
        loaded = self.repository.get(application.id)
        assert loaded is not None
        return loaded

    def transition(
        self,
        application_id: UUID,
        *,
        target: ApplicationStage,
        expected_version: int,
        reason: str | None = None,
        notes: str | None = None,
    ) -> ApplicationProcessModel:
        """Move to a new stage, appending history. The previous entries are never edited."""
        application = self.get(application_id)
        self._guard_version(application, expected_version)
        source = ApplicationStage(application.current_stage)
        validate_transition(source, target)

        occurred_at = datetime.now(UTC)
        self.repository.add_history(
            application,
            from_stage=source.value,
            to_stage=target.value,
            reason=normalized_text(reason, 64),
            notes=normalized_text(notes, MAX_NOTE_LENGTH),
            occurred_at=occurred_at,
        )
        application.current_stage = target.value
        status = status_for(target)
        closed = status is ApplicationStatus.CLOSED
        application.status = status.value
        application.closed_at = occurred_at if closed else None
        application.outcome = target.value if closed else None
        if target is ApplicationStage.APPLIED and application.applied_at is None:
            application.applied_at = occurred_at
        if closed:
            # A closed application owes nothing: keeping a due date would leave it in the
            # follow-up count forever.
            application.next_action = None
            application.next_action_at = None
        application.version += 1
        self.session.commit()
        loaded = self.repository.get(application.id)
        assert loaded is not None
        return loaded

    def set_next_action(
        self,
        application_id: UUID,
        *,
        expected_version: int,
        next_action: str | None = None,
        next_action_at: datetime | None = None,
        notes: str | None = None,
    ) -> ApplicationProcessModel:
        application = self.get(application_id)
        self._guard_version(application, expected_version)
        application.next_action = normalized_text(next_action, MAX_NEXT_ACTION_LENGTH)
        application.next_action_at = next_action_at
        if notes is not None:
            application.notes = normalized_text(notes, MAX_NOTE_LENGTH)
        application.version += 1
        self.session.commit()
        loaded = self.repository.get(application.id)
        assert loaded is not None
        return loaded

    def get(self, application_id: UUID) -> ApplicationProcessModel:
        application = self.repository.get(application_id)
        if application is None:
            raise ApplicationNotFoundError(str(application_id))
        return application

    def list(
        self,
        *,
        opportunity_id: UUID | None = None,
        profile_version_id: UUID | None = None,
        status: str | None = None,
        stage: str | None = None,
        due_before: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApplicationProcessModel], int]:
        return self.repository.list(
            opportunity_id=opportunity_id,
            profile_version_id=profile_version_id,
            status=status,
            stage=stage,
            due_before=due_before,
            offset=offset,
            limit=limit,
        )

    @staticmethod
    def _guard_version(application: ApplicationProcessModel, expected: int) -> None:
        if application.version != expected:
            raise ApplicationVersionConflictError(
                f"application is at version {application.version}, not {expected}"
            )


__all__ = ["ApplicationOpportunityNotFoundError", "PipelineService"]
