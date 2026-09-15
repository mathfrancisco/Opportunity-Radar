"""HTTP API for canonical opportunities, normalization, and provenance."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import (
    NormalizationError,
    OpportunityStatus,
    WorkMode,
)
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityCompensationModel,
    OpportunityModel,
    OpportunitySkillModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.opportunities.service import (
    NormalizationBatch,
    OpportunityNotFoundError,
    OpportunityService,
    OpportunityVersionConflictError,
    RawItemNotFoundError,
)
from opportunity_radar.presentation.http.dependencies import get_session

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


class SourceOccurrenceResponse(BaseModel):
    id: UUID
    raw_item_id: UUID
    source_definition_id: UUID
    external_id: str | None
    source_url: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    source_published_at: datetime | None
    source_updated_at: datetime | None


class NormalizationResultResponse(BaseModel):
    id: UUID
    raw_item_id: UUID
    opportunity_id: UUID | None
    source_occurrence_id: UUID | None
    status: str
    normalizer_version: str
    identity_decision: str | None
    reasons: list[Any]
    error_summary: str | None
    processed_at: datetime


class CompensationResponse(BaseModel):
    minimum: Decimal | None
    maximum: Decimal | None
    currency: str | None
    period: str
    gross_net: str
    evidence_text: str | None
    evidence_source: str | None
    normalizer_version: str
    source_occurrence_id: UUID | None
    raw_item_id: UUID


class OpportunitySkillResponse(BaseModel):
    canonical_name: str
    display_name: str
    requirement: str
    evidence: list[Any]
    taxonomy_version: str
    normalizer_version: str


class OpportunityResponse(BaseModel):
    id: UUID
    fingerprint: str
    fingerprint_version: str
    title: str
    company_id: UUID | None
    company_name: str | None
    location: str | None
    work_mode: str
    seniority: str
    contract_type: str
    description: str | None
    lifecycle_status: str
    published_at: datetime | None
    source_updated_at: datetime | None
    version: int
    compensations: list[CompensationResponse]
    skills: list[OpportunitySkillResponse]
    occurrences: list[SourceOccurrenceResponse]


class OpportunityDetailResponse(OpportunityResponse):
    normalization_results: list[NormalizationResultResponse]


class OpportunityPageResponse(BaseModel):
    items: list[OpportunityResponse]
    page: int
    page_size: int
    total: int


class NormalizeResponse(BaseModel):
    result: NormalizationResultResponse
    opportunity: OpportunityResponse | None
    occurrence: SourceOccurrenceResponse | None


class NormalizePendingResponse(BaseModel):
    processed: int
    succeeded: int
    review_required: int
    failed: int


class OpportunityStatusBody(BaseModel):
    status: OpportunityStatus
    expected_version: int = Field(ge=1)


@router.post("/normalizations/pending", response_model=NormalizePendingResponse)
def normalize_pending(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> NormalizePendingResponse:
    batch = OpportunityService(session).normalize_pending(limit)
    return _batch_response(batch)


@router.post("/normalizations/{raw_item_id}", response_model=NormalizeResponse)
def normalize_raw_item(
    raw_item_id: UUID,
    session: Session = Depends(get_session),
) -> NormalizeResponse:
    try:
        result = OpportunityService(session).normalize(raw_item_id)
    except RawItemNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "raw_item_not_found", "message": "Raw item not found."},
        ) from error
    return NormalizeResponse(
        result=_normalization_response(result),
        opportunity=(
            _opportunity_response(result.opportunity)
            if result.opportunity is not None
            else None
        ),
        occurrence=(
            _occurrence_response(result.source_occurrence)
            if result.source_occurrence is not None
            else None
        ),
    )


@router.get("", response_model=OpportunityPageResponse)
def list_opportunities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    lifecycle_status: OpportunityStatus | None = None,
    work_mode: WorkMode | None = None,
    company_id: UUID | None = None,
    session: Session = Depends(get_session),
) -> OpportunityPageResponse:
    items, total = OpportunityRepository(session).list(
        offset=(page - 1) * page_size,
        limit=page_size,
        lifecycle_status=lifecycle_status.value if lifecycle_status else None,
        work_mode=work_mode.value if work_mode else None,
        company_id=company_id,
    )
    return OpportunityPageResponse(
        items=[_opportunity_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
def get_opportunity(
    opportunity_id: UUID,
    session: Session = Depends(get_session),
) -> OpportunityDetailResponse:
    opportunity = OpportunityRepository(session).get(opportunity_id)
    if opportunity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "opportunity_not_found",
                "message": "Opportunity not found.",
            },
        )
    basic = _opportunity_response(opportunity)
    return OpportunityDetailResponse(
        **basic.model_dump(),
        normalization_results=[
            _normalization_response(item)
            for item in opportunity.normalization_results
        ],
    )


@router.patch("/{opportunity_id}/status", response_model=OpportunityResponse)
def update_opportunity_status(
    opportunity_id: UUID,
    body: OpportunityStatusBody,
    session: Session = Depends(get_session),
) -> OpportunityResponse:
    try:
        opportunity = OpportunityService(session).transition(
            opportunity_id,
            target=body.status,
            expected_version=body.expected_version,
        )
    except OpportunityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "opportunity_not_found",
                "message": "Opportunity not found.",
            },
        ) from error
    except OpportunityVersionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_conflict", "message": str(error)},
        ) from error
    except NormalizationError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_status_transition", "message": str(error)},
        ) from error
    return _opportunity_response(opportunity)


def _opportunity_response(opportunity: OpportunityModel) -> OpportunityResponse:
    return OpportunityResponse(
        id=opportunity.id,
        fingerprint=opportunity.fingerprint,
        fingerprint_version=opportunity.fingerprint_version,
        title=opportunity.canonical_title,
        company_id=opportunity.canonical_company_id,
        company_name=opportunity.company_name,
        location=opportunity.location_text,
        work_mode=opportunity.work_mode,
        seniority=opportunity.seniority,
        contract_type=opportunity.contract_type,
        description=opportunity.description,
        lifecycle_status=opportunity.lifecycle_status,
        published_at=opportunity.published_at,
        source_updated_at=opportunity.source_updated_at,
        version=opportunity.version,
        compensations=[
            _compensation_response(item)
            for item in sorted(
                opportunity.compensations,
                key=lambda value: (value.evidence_source or "", str(value.id)),
            )
        ],
        skills=[
            _skill_response(item)
            for item in sorted(
                opportunity.skills,
                key=lambda value: (value.canonical_name, str(value.id)),
            )
        ],
        occurrences=[
            _occurrence_response(item)
            for item in sorted(
                opportunity.occurrences,
                key=lambda value: (value.first_seen_at, str(value.id)),
            )
        ],
    )


def _compensation_response(
    compensation: OpportunityCompensationModel,
) -> CompensationResponse:
    return CompensationResponse(
        minimum=compensation.amount_min,
        maximum=compensation.amount_max,
        currency=compensation.currency,
        period=compensation.period,
        gross_net=compensation.gross_net,
        evidence_text=compensation.evidence_text,
        evidence_source=compensation.evidence_source,
        normalizer_version=compensation.normalizer_version,
        source_occurrence_id=compensation.source_occurrence_id,
        raw_item_id=compensation.raw_item_id,
    )


def _skill_response(skill: OpportunitySkillModel) -> OpportunitySkillResponse:
    return OpportunitySkillResponse(
        canonical_name=skill.canonical_name,
        display_name=skill.display_name,
        requirement=skill.requirement,
        evidence=skill.evidence,
        taxonomy_version=skill.taxonomy_version,
        normalizer_version=skill.normalizer_version,
    )


def _occurrence_response(
    occurrence: SourceOccurrenceModel,
) -> SourceOccurrenceResponse:
    return SourceOccurrenceResponse(
        id=occurrence.id,
        raw_item_id=occurrence.raw_item_id,
        source_definition_id=occurrence.source_definition_id,
        external_id=occurrence.external_id,
        source_url=occurrence.source_url,
        first_seen_at=occurrence.first_seen_at,
        last_seen_at=occurrence.last_seen_at,
        source_published_at=occurrence.source_published_at,
        source_updated_at=occurrence.source_updated_at,
    )


def _normalization_response(
    result: NormalizationResultModel,
) -> NormalizationResultResponse:
    return NormalizationResultResponse(
        id=result.id,
        raw_item_id=result.raw_item_id,
        opportunity_id=result.opportunity_id,
        source_occurrence_id=result.source_occurrence_id,
        status=result.status,
        normalizer_version=result.normalizer_version,
        identity_decision=result.identity_decision,
        reasons=result.reasons,
        error_summary=result.error_summary,
        processed_at=result.processed_at,
    )


def _batch_response(batch: NormalizationBatch) -> NormalizePendingResponse:
    return NormalizePendingResponse(
        processed=batch.processed,
        succeeded=batch.succeeded,
        review_required=batch.review_required,
        failed=batch.failed,
    )
