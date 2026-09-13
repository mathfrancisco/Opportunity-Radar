"""HTTP contract for source configuration and manual acquisition runs."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from datetime import datetime
from typing import Any, Literal, NoReturn, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionMode,
    CollectionRequest,
    ManualInput,
    ManualInputKind,
)
from opportunity_radar.acquisition.models import (
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.service import AcquisitionService, SourceNotFoundError
from opportunity_radar.presentation.http.dependencies import get_session

router = APIRouter(tags=["acquisition"])

EvidenceStatus = Literal[
    "unverified",
    "confirmed",
    "ats_identified",
    "careers_page",
    "dynamic_review",
    "redirect_review",
    "access_pending",
]


class SourceDefinitionBody(BaseModel):
    source_type: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    company_source_id: UUID | None = None
    enabled: bool = False
    schedule: str | None = Field(default=None, max_length=255)
    priority: int = Field(default=100, ge=0)
    rate_limit_policy: dict[str, Any] = Field(default_factory=dict)
    configuration: dict[str, Any] = Field(default_factory=dict)
    evidence_status: EvidenceStatus = "unverified"
    reviewed_at: datetime | None = None
    terms_reviewed: bool = False
    collector_local_tested: bool = False


class SourceDefinitionResponse(SourceDefinitionBody):
    id: UUID
    last_health_status: str | None
    last_http_attempt_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class SourcePageResponse(BaseModel):
    items: list[SourceDefinitionResponse]
    page: int
    page_size: int
    total: int


class SourceControlsBody(BaseModel):
    enabled: bool
    terms_reviewed: bool
    collector_local_tested: bool
    reviewed_at: datetime | None = None
    expected_version: int = Field(ge=1)


class ManualInputBody(BaseModel):
    kind: ManualInputKind
    value: str = Field(min_length=1, max_length=2048)
    content_base64: str | None = Field(default=None, max_length=7_000_000)
    content_type: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateRunBody(BaseModel):
    mode: CollectionMode | None = None
    inputs: list[ManualInputBody] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1)
    correlation_id: str | None = Field(default=None, max_length=255)


class SourceRunResponse(BaseModel):
    id: UUID
    source_definition_id: UUID
    source_name: str | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    items_seen: int
    items_persisted: int
    items_skipped: int
    items_invalid: int
    http_requests: int
    retry_count: int
    rate_limit_events: int
    error_code: str | None
    error_summary: str | None
    checkpoint_before: str | None
    checkpoint_after: str | None
    correlation_id: str | None


class SourceRunPageResponse(BaseModel):
    items: list[SourceRunResponse]
    page: int
    page_size: int
    total: int


@router.post(
    "/sources",
    response_model=SourceDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    body: SourceDefinitionBody, session: Session = Depends(get_session)
) -> SourceDefinitionResponse:
    try:
        source = AcquisitionService(session).create_source(**body.model_dump())
    except AcquisitionError as error:
        _raise_acquisition_error(error)
    return _source_response(source)


@router.get("/sources", response_model=SourcePageResponse)
def list_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    session: Session = Depends(get_session),
) -> SourcePageResponse:
    sources, total = AcquisitionService(session).list_sources(
        offset=(page - 1) * page_size, limit=page_size
    )
    return SourcePageResponse(
        items=[_source_response(source) for source in sources],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/sources/{source_id}", response_model=SourceDefinitionResponse)
def get_source(
    source_id: UUID,
    session: Session = Depends(get_session),
) -> SourceDefinitionResponse:
    source = AcquisitionService(session).get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "source_definition_not_found",
                "message": "Source definition not found.",
            },
        )
    return _source_response(source)


@router.patch("/sources/{source_id}", response_model=SourceDefinitionResponse)
def update_source_controls(
    source_id: UUID,
    body: SourceControlsBody,
    session: Session = Depends(get_session),
) -> SourceDefinitionResponse:
    try:
        source = AcquisitionService(session).update_source_controls(
            source_id, **body.model_dump()
        )
    except AcquisitionError as error:
        _raise_acquisition_error(error)
    return _source_response(source)


@router.post(
    "/sources/{source_id}/runs",
    response_model=SourceRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_source(
    source_id: UUID,
    body: CreateRunBody,
    session: Session = Depends(get_session),
) -> SourceRunResponse:
    try:
        manual_inputs = tuple(_manual_input(item) for item in body.inputs)
        mode = body.mode or (
            CollectionMode.MANUAL if manual_inputs else CollectionMode.DISCOVERY
        )
        request = CollectionRequest(
            source_definition_id=source_id,
            mode=mode,
            manual_inputs=manual_inputs,
            max_items=body.max_items,
            correlation_id=body.correlation_id,
        )
        run = await AcquisitionService(session).execute(source_id, request)
    except AcquisitionError as error:
        _raise_acquisition_error(error)
    except ValueError as error:
        _raise_acquisition_error(
            AcquisitionError(
                code=AcquisitionErrorCode.MANUAL_INPUT_INVALID,
                summary=str(error),
            )
        )
    return _run_response(run)


@router.get("/source-runs", response_model=SourceRunPageResponse)
def list_source_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    source_id: UUID | None = None,
    session: Session = Depends(get_session),
) -> SourceRunPageResponse:
    runs, total = AcquisitionService(session).list_runs(
        offset=(page - 1) * page_size,
        limit=page_size,
        source_id=source_id,
    )
    return SourceRunPageResponse(
        items=[_run_response(run) for run in runs],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/source-runs/{run_id}", response_model=SourceRunResponse)
def get_source_run(
    run_id: UUID,
    session: Session = Depends(get_session),
) -> SourceRunResponse:
    run = AcquisitionService(session).get_run(run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="source run not found",
        )
    return _run_response(run)


def _manual_input(body: ManualInputBody) -> ManualInput:
    content: bytes | None = None
    if body.kind is ManualInputKind.FILE:
        if body.content_base64 is None:
            raise ValueError("FILE input requires content_base64")
        try:
            content = b64decode(body.content_base64, validate=True)
        except Base64Error as error:
            raise ValueError("content_base64 must be valid base64") from error
    elif body.content_base64 is not None:
        raise ValueError("content_base64 is only accepted for FILE input")
    return ManualInput(
        kind=body.kind,
        value=body.value,
        content=content,
        content_type=body.content_type,
        metadata=body.metadata,
    )


def _source_response(source: SourceDefinitionModel) -> SourceDefinitionResponse:
    return SourceDefinitionResponse(
        id=source.id,
        source_type=source.source_type,
        name=source.name,
        company_source_id=source.company_source_id,
        enabled=source.enabled,
        schedule=source.schedule,
        priority=source.priority,
        rate_limit_policy=source.rate_limit_policy,
        configuration=source.configuration,
        evidence_status=cast(EvidenceStatus, source.evidence_status),
        reviewed_at=source.reviewed_at,
        terms_reviewed=source.terms_reviewed,
        collector_local_tested=source.collector_local_tested,
        last_health_status=source.last_health_status,
        last_http_attempt_at=source.last_http_attempt_at,
        created_at=source.created_at,
        updated_at=source.updated_at,
        version=source.version,
    )


def _run_response(run: SourceRunModel) -> SourceRunResponse:
    return SourceRunResponse(
        id=run.id,
        source_definition_id=run.source_definition_id,
        source_name=run.source_definition.name if run.source_definition else None,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        items_seen=run.items_seen,
        items_persisted=run.items_persisted,
        items_skipped=run.items_skipped,
        items_invalid=run.items_invalid,
        http_requests=run.http_requests,
        retry_count=run.retry_count,
        rate_limit_events=run.rate_limit_events,
        error_code=run.error_code,
        error_summary=run.error_summary,
        checkpoint_before=run.checkpoint_before,
        checkpoint_after=run.checkpoint_after,
        correlation_id=run.correlation_id,
    )


def _raise_acquisition_error(error: AcquisitionError) -> NoReturn:
    if isinstance(error, SourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code.value, "message": error.summary},
    ) from error
