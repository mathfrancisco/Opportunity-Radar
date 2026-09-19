"""HTTP contract for candidacies and their stage history."""

from __future__ import annotations

from datetime import datetime
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from opportunity_radar.pipeline.domain import (
    ALLOWED_TRANSITIONS,
    MAX_NEXT_ACTION_LENGTH,
    MAX_NOTE_LENGTH,
    ApplicationNotFoundError,
    ApplicationStage,
    ApplicationStatus,
    ApplicationVersionConflictError,
    DuplicateActiveApplicationError,
    InvalidStageTransitionError,
    InvalidStartStageError,
    PipelineError,
)
from opportunity_radar.pipeline.models import ApplicationProcessModel, StageHistoryModel
from opportunity_radar.pipeline.service import (
    ApplicationOpportunityNotFoundError,
    PipelineService,
)
from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.domain import ProfileNotFoundError

router = APIRouter(prefix="/applications", tags=["pipeline"])


class StartApplicationBody(BaseModel):
    opportunity_id: UUID
    profile_version_id: UUID | None = None
    stage: ApplicationStage = ApplicationStage.INTERESTED
    next_action: str | None = Field(default=None, max_length=MAX_NEXT_ACTION_LENGTH)
    next_action_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class TransitionBody(BaseModel):
    stage: ApplicationStage
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class NextActionBody(BaseModel):
    expected_version: int = Field(ge=1)
    next_action: str | None = Field(default=None, max_length=MAX_NEXT_ACTION_LENGTH)
    next_action_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class StageHistoryResponse(BaseModel):
    id: UUID
    from_stage: str | None
    to_stage: str
    reason: str | None
    source: str
    notes: str | None
    occurred_at: datetime


class ApplicationResponse(BaseModel):
    id: UUID
    opportunity_id: UUID
    profile_version_id: UUID
    current_stage: str
    status: str
    outcome: str | None
    next_action: str | None
    next_action_at: datetime | None
    notes: str | None
    applied_at: datetime | None
    started_at: datetime
    closed_at: datetime | None
    version: int
    #: Where this application may go next, so the interface never offers an illegal move.
    allowed_transitions: list[str]
    history: list[StageHistoryResponse]


class ApplicationPageResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    offset: int
    limit: int


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def start_application(
    body: StartApplicationBody,
    session: Session = Depends(get_session),
) -> ApplicationResponse:
    try:
        application = PipelineService(session).start(
            body.opportunity_id,
            profile_version_id=body.profile_version_id,
            stage=body.stage,
            next_action=body.next_action,
            next_action_at=body.next_action_at,
            notes=body.notes,
        )
    except ApplicationOpportunityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "opportunity_not_found",
                "message": "Opportunity not found.",
            },
        ) from error
    except ProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "profile_not_found", "message": str(error)},
        ) from error
    except PipelineError as error:
        _raise_pipeline_error(error)
    return _application_response(application)


@router.get("", response_model=ApplicationPageResponse)
def list_applications(
    opportunity_id: UUID | None = None,
    profile_version_id: UUID | None = None,
    application_status: ApplicationStatus | None = None,
    stage: ApplicationStage | None = None,
    due_before: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> ApplicationPageResponse:
    items, total = PipelineService(session).list(
        opportunity_id=opportunity_id,
        profile_version_id=profile_version_id,
        status=application_status.value if application_status else None,
        stage=stage.value if stage else None,
        due_before=due_before,
        offset=offset,
        limit=limit,
    )
    return ApplicationPageResponse(
        items=[_application_response(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(
    application_id: UUID,
    session: Session = Depends(get_session),
) -> ApplicationResponse:
    try:
        return _application_response(PipelineService(session).get(application_id))
    except ApplicationNotFoundError as error:
        _raise_pipeline_error(error)


@router.post("/{application_id}/transitions", response_model=ApplicationResponse)
def transition_application(
    application_id: UUID,
    body: TransitionBody,
    session: Session = Depends(get_session),
) -> ApplicationResponse:
    try:
        application = PipelineService(session).transition(
            application_id,
            target=body.stage,
            expected_version=body.expected_version,
            reason=body.reason,
            notes=body.notes,
        )
    except PipelineError as error:
        _raise_pipeline_error(error)
    return _application_response(application)


@router.patch("/{application_id}/next-action", response_model=ApplicationResponse)
def set_next_action(
    application_id: UUID,
    body: NextActionBody,
    session: Session = Depends(get_session),
) -> ApplicationResponse:
    try:
        application = PipelineService(session).set_next_action(
            application_id,
            expected_version=body.expected_version,
            next_action=body.next_action,
            next_action_at=body.next_action_at,
            notes=body.notes,
        )
    except PipelineError as error:
        _raise_pipeline_error(error)
    return _application_response(application)


def _application_response(application: ApplicationProcessModel) -> ApplicationResponse:
    stage = ApplicationStage(application.current_stage)
    return ApplicationResponse(
        id=application.id,
        opportunity_id=application.opportunity_id,
        profile_version_id=application.profile_version_id,
        current_stage=application.current_stage,
        status=application.status,
        outcome=application.outcome,
        next_action=application.next_action,
        next_action_at=application.next_action_at,
        notes=application.notes,
        applied_at=application.applied_at,
        started_at=application.started_at,
        closed_at=application.closed_at,
        version=application.version,
        allowed_transitions=sorted(item.value for item in ALLOWED_TRANSITIONS[stage]),
        history=[
            _history_response(entry)
            for entry in sorted(
                application.history, key=lambda item: (item.occurred_at, item.id)
            )
        ],
    )


def _history_response(entry: StageHistoryModel) -> StageHistoryResponse:
    return StageHistoryResponse(
        id=entry.id,
        from_stage=entry.from_stage,
        to_stage=entry.to_stage,
        reason=entry.reason,
        source=entry.source,
        notes=entry.notes,
        occurred_at=entry.occurred_at,
    )


def _raise_pipeline_error(error: PipelineError) -> NoReturn:
    if isinstance(error, ApplicationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "application_not_found",
                "message": "Application not found.",
            },
        ) from error
    if isinstance(error, DuplicateActiveApplicationError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_active_application", "message": str(error)},
        ) from error
    if isinstance(error, ApplicationVersionConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_conflict", "message": str(error)},
        ) from error
    if isinstance(error, (InvalidStageTransitionError, InvalidStartStageError)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_stage_transition", "message": str(error)},
        ) from error
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "pipeline_error", "message": str(error)},
    ) from error
