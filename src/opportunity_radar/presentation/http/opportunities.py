"""HTTP API for canonical opportunities, normalization, and provenance."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import (
    NormalizationError,
    OpportunityStatus,
    RecencyBasis,
    WorkMode,
    recency_reference,
)
from opportunity_radar.opportunities.duplicates import (
    DuplicateCandidateNotFoundError,
    DuplicateConflictError,
    DuplicateCycleError,
    confirm_duplicate,
    reject_duplicate,
    resolve_survivor,
)
from opportunity_radar.opportunities.models import (
    DuplicateCandidateModel,
    NormalizationResultModel,
    OpportunityCompensationModel,
    OpportunityModel,
    OpportunitySkillModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.opportunities.service import (
    NormalizationBatch,
    OpportunityNotFoundError,
    OpportunityService,
    OpportunityVersionConflictError,
    RawItemNotFoundError,
    SourceRunNotFoundError,
)
from opportunity_radar.opportunities.suggestions import (
    OpportunitySuggestionModel,
    SuggestionAlreadyDecidedError,
    SuggestionNotFoundError,
    accept_suggestion,
    reject_suggestion,
)
from opportunity_radar.presentation.http.auth import RequestIdentity, authenticated_identity
from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

_RELEVANCE_REASONS = (
    "AREA",
    "SENIORITY",
    "LOCATION",
    "COMPANY",
    "COMPENSATION",
    "OTHER",
)

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
    #: Whether the raw body behind this occurrence can still be reprocessed. The envelope
    #: above stays either way, so `False` means "no longer reprocessable", not "lost".
    payload_retained: bool
    payload_expired_at: datetime | None


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


class RelevanceMarkResponse(BaseModel):
    id: UUID
    relevant: bool
    reason: str | None
    note: str | None
    profile_version_id: UUID | None
    marked_at: datetime


class DuplicateCandidateResponse(BaseModel):
    id: UUID
    opportunity_id: UUID
    duplicate_opportunity_id: UUID
    survivor_opportunity_id: UUID
    absorbed_opportunity_id: UUID
    rule: str
    score: Decimal | None
    status: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


class DuplicateCandidatePageResponse(BaseModel):
    items: list[DuplicateCandidateResponse]


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
    role_family: str
    role_family_evidence: dict[str, str] | None
    role_family_version: str | None
    published_at: datetime | None
    source_updated_at: datetime | None
    #: Cards F20-61/F48-16: `published_at ?? source_updated_at ?? first_seen_at`
    #: (never a fabricated real date).
    recency_effective_date: datetime | None
    #: `True` when `recency_effective_date` is not the source's `published_at`.
    date_is_estimated: bool
    #: `published`, `updated` or `first_seen` (persisted `recency_basis`).
    recency_basis: str
    valid_through: datetime | None
    recency_exempt_program: bool
    #: When this opportunity was first persisted. Exposed so the duplicate-candidate
    #: comparison UI (F20-26) can tell which side of a pair `confirm_duplicate` will
    #: treat as the survivor (the older `created_at`) before it calls confirm.
    created_at: datetime
    version: int
    compensations: list[CompensationResponse]
    skills: list[OpportunitySkillResponse]
    occurrences: list[SourceOccurrenceResponse]
    relevance_mark: RelevanceMarkResponse | None = None


class SiblingLocationResponse(BaseModel):
    """Card F48-10: another posting of the same company, title and source."""

    opportunity_id: UUID
    location: str | None
    source_url: str | None


class OpportunityDetailResponse(OpportunityResponse):
    normalization_results: list[NormalizationResultResponse]
    sibling_locations: list[SiblingLocationResponse] = []


class OpportunityPageResponse(BaseModel):
    items: list[OpportunityResponse]
    page: int
    page_size: int
    total: int


class NormalizeResponse(BaseModel):
    result: NormalizationResultResponse
    opportunity: OpportunityResponse | None
    occurrence: SourceOccurrenceResponse | None


class RunNormalizationItemResponse(BaseModel):
    raw_item_id: UUID
    canonical_url: str | None
    result: NormalizationResultResponse
    opportunity: OpportunityResponse | None


class RunNormalizationResponse(BaseModel):
    source_run_id: UUID
    items: list[RunNormalizationItemResponse]


class NormalizePendingResponse(BaseModel):
    processed: int
    succeeded: int
    review_required: int
    failed: int


class OpportunityStatusBody(BaseModel):
    status: OpportunityStatus
    expected_version: int = Field(ge=1)


class RelevanceMarkBody(BaseModel):
    relevant: bool
    reason: str | None = None
    note: str | None = None

    def validated_reason(self) -> str | None:
        if self.reason is None:
            return None
        if self.reason not in _RELEVANCE_REASONS:
            raise ValueError(f"invalid reason: {self.reason}")
        return self.reason


class ConfirmDuplicateBody(BaseModel):
    expected_version_survivor: int = Field(ge=1)
    expected_version_absorbed: int = Field(ge=1)
    decided_by: str = Field(min_length=1, max_length=255)


class RejectDuplicateBody(BaseModel):
    decided_by: str = Field(min_length=1, max_length=255)


class FieldSuggestionResponse(BaseModel):
    id: UUID
    opportunity_id: UUID
    opportunity_version: int
    field: str
    value: str
    evidence: str
    model: str
    prompt_version: str
    status: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime


class FieldSuggestionPageResponse(BaseModel):
    items: list[FieldSuggestionResponse]


class DecideSuggestionBody(BaseModel):
    decided_by: str = Field(min_length=1, max_length=255)


@router.post("/normalizations/pending", response_model=NormalizePendingResponse)
def normalize_pending(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> NormalizePendingResponse:
    batch = OpportunityService(session).normalize_pending(limit)
    return _batch_response(batch)


@router.post("/normalizations/runs/{source_run_id}", response_model=RunNormalizationResponse)
def normalize_run(
    source_run_id: UUID,
    session: Session = Depends(get_session),
) -> RunNormalizationResponse:
    try:
        outcomes = OpportunityService(session).normalize_run(source_run_id)
    except SourceRunNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "source_run_not_found", "message": "Source run not found."},
        ) from error
    return RunNormalizationResponse(
        source_run_id=source_run_id,
        items=[
            RunNormalizationItemResponse(
                raw_item_id=raw_item.id,
                canonical_url=raw_item.canonical_url,
                result=_normalization_response(result),
                opportunity=(
                    _opportunity_response(result.opportunity, session=session)
                    if result.opportunity is not None
                    else None
                ),
            )
            for raw_item, result in outcomes
        ],
    )


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
            _opportunity_response(result.opportunity, session=session)
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
    #: Card F20-61: the server's own default, absent this parameter, is filtered.
    #: The client's "mostrar tudo" toggle passes `only_recent=false`.
    only_recent: bool = Query(default=True),
    session: Session = Depends(get_session),
    identity: RequestIdentity = Depends(authenticated_identity),
) -> OpportunityPageResponse:
    items, total = OpportunityRepository(session).list(
        offset=(page - 1) * page_size,
        limit=page_size,
        lifecycle_status=lifecycle_status.value if lifecycle_status else None,
        work_mode=work_mode.value if work_mode else None,
        company_id=company_id,
        only_recent=only_recent,
    )
    return OpportunityPageResponse(
        items=[
            _opportunity_response(item, session=session, owner_sub=identity.sub)
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{opportunity_id}", response_model=OpportunityDetailResponse)
def get_opportunity(
    opportunity_id: UUID,
    session: Session = Depends(get_session),
    identity: RequestIdentity = Depends(authenticated_identity),
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
    basic = _opportunity_response(opportunity, session=session, owner_sub=identity.sub)
    return OpportunityDetailResponse(
        **basic.model_dump(),
        normalization_results=[
            _normalization_response(item) for item in opportunity.normalization_results
        ],
        sibling_locations=[
            SiblingLocationResponse(
                opportunity_id=sibling.id,
                location=sibling.location_text,
                source_url=url,
            )
            for sibling, url in OpportunityRepository(session).posting_group_siblings(opportunity)
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
    return _opportunity_response(opportunity, session=session)


@router.post("/{opportunity_id}/relevance", response_model=RelevanceMarkResponse)
def mark_relevance(
    opportunity_id: UUID,
    body: RelevanceMarkBody,
    session: Session = Depends(get_session),
    identity: RequestIdentity = Depends(authenticated_identity),
) -> RelevanceMarkResponse:
    try:
        reason = body.validated_reason()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_reason", "message": str(error)},
        ) from error
    try:
        profile_version_id = ProfileService(session, identity.sub).get_active().id
    except ProfileNotFoundError:
        profile_version_id = None
    try:
        mark = OpportunityService(session).mark_relevance(
            opportunity_id,
            relevant=body.relevant,
            reason=reason,
            note=body.note,
            profile_version_id=profile_version_id,
            owner_sub=identity.sub,
        )
    except OpportunityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "opportunity_not_found",
                "message": "Opportunity not found.",
            },
        ) from error
    return _relevance_mark_response(mark)


@router.get(
    "/{opportunity_id}/duplicate-candidates",
    response_model=DuplicateCandidatePageResponse,
)
def list_duplicate_candidates(
    opportunity_id: UUID,
    session: Session = Depends(get_session),
) -> DuplicateCandidatePageResponse:
    rows = session.scalars(
        select(DuplicateCandidateModel).where(
            (DuplicateCandidateModel.opportunity_id == opportunity_id)
            | (DuplicateCandidateModel.duplicate_opportunity_id == opportunity_id)
        )
    ).all()
    return DuplicateCandidatePageResponse(
        items=[_duplicate_candidate_response(session, row) for row in rows]
    )


@router.post(
    "/duplicate-candidates/{candidate_id}/confirm",
    response_model=DuplicateCandidateResponse,
)
def confirm_duplicate_candidate(
    candidate_id: UUID,
    body: ConfirmDuplicateBody,
    session: Session = Depends(get_session),
) -> DuplicateCandidateResponse:
    try:
        candidate = confirm_duplicate(
            session,
            candidate_id,
            expected_version_survivor=body.expected_version_survivor,
            expected_version_absorbed=body.expected_version_absorbed,
            decided_by=body.decided_by,
        )
    except DuplicateCandidateNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "duplicate_candidate_not_found",
                "message": "Duplicate candidate not found.",
            },
        ) from error
    except OpportunityVersionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_conflict", "message": str(error)},
        ) from error
    except DuplicateConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_conflict", "message": str(error)},
        ) from error
    except DuplicateCycleError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "duplicate_cycle", "message": str(error)},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_duplicate_transition", "message": str(error)},
        ) from error
    return _duplicate_candidate_response(session, candidate)


@router.post(
    "/duplicate-candidates/{candidate_id}/reject",
    response_model=DuplicateCandidateResponse,
)
def reject_duplicate_candidate(
    candidate_id: UUID,
    body: RejectDuplicateBody,
    session: Session = Depends(get_session),
) -> DuplicateCandidateResponse:
    try:
        candidate = reject_duplicate(session, candidate_id, decided_by=body.decided_by)
    except DuplicateCandidateNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "duplicate_candidate_not_found",
                "message": "Duplicate candidate not found.",
            },
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_duplicate_transition", "message": str(error)},
        ) from error
    return _duplicate_candidate_response(session, candidate)


@router.get(
    "/{opportunity_id}/field-suggestions",
    response_model=FieldSuggestionPageResponse,
)
def list_field_suggestions(
    opportunity_id: UUID,
    session: Session = Depends(get_session),
) -> FieldSuggestionPageResponse:
    rows = session.scalars(
        select(OpportunitySuggestionModel)
        .where(OpportunitySuggestionModel.opportunity_id == opportunity_id)
        .order_by(OpportunitySuggestionModel.created_at)
    ).all()
    return FieldSuggestionPageResponse(items=[_field_suggestion_response(row) for row in rows])


@router.post(
    "/field-suggestions/{suggestion_id}/accept",
    response_model=FieldSuggestionResponse,
)
def accept_field_suggestion(
    suggestion_id: UUID,
    body: DecideSuggestionBody,
    session: Session = Depends(get_session),
) -> FieldSuggestionResponse:
    try:
        suggestion = accept_suggestion(session, suggestion_id, decided_by=body.decided_by)
    except SuggestionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "field_suggestion_not_found", "message": "Field suggestion not found."},
        ) from error
    except OpportunityVersionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_conflict", "message": str(error)},
        ) from error
    except SuggestionAlreadyDecidedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_suggestion_transition", "message": str(error)},
        ) from error
    return _field_suggestion_response(suggestion)


@router.post(
    "/field-suggestions/{suggestion_id}/reject",
    response_model=FieldSuggestionResponse,
)
def reject_field_suggestion(
    suggestion_id: UUID,
    body: DecideSuggestionBody,
    session: Session = Depends(get_session),
) -> FieldSuggestionResponse:
    try:
        suggestion = reject_suggestion(session, suggestion_id, decided_by=body.decided_by)
    except SuggestionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "field_suggestion_not_found", "message": "Field suggestion not found."},
        ) from error
    except SuggestionAlreadyDecidedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_suggestion_transition", "message": str(error)},
        ) from error
    return _field_suggestion_response(suggestion)


def _field_suggestion_response(
    suggestion: OpportunitySuggestionModel,
) -> FieldSuggestionResponse:
    return FieldSuggestionResponse(
        id=suggestion.id,
        opportunity_id=suggestion.opportunity_id,
        opportunity_version=suggestion.opportunity_version,
        field=suggestion.field,
        value=suggestion.value,
        evidence=suggestion.evidence,
        model=suggestion.model,
        prompt_version=suggestion.prompt_version,
        status=suggestion.status,
        decided_by=suggestion.decided_by,
        decided_at=suggestion.decided_at,
        created_at=suggestion.created_at,
    )


def _duplicate_candidate_response(
    session: Session, candidate: DuplicateCandidateModel
) -> DuplicateCandidateResponse:
    first = session.get(OpportunityModel, candidate.opportunity_id)
    second = session.get(OpportunityModel, candidate.duplicate_opportunity_id)
    if first is None or second is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "duplicate_candidate_opportunity_not_found",
                "message": "Opportunity for duplicate candidate not found.",
            },
        )
    survivor, absorbed = resolve_survivor(first, second)
    return DuplicateCandidateResponse(
        id=candidate.id,
        opportunity_id=candidate.opportunity_id,
        duplicate_opportunity_id=candidate.duplicate_opportunity_id,
        survivor_opportunity_id=survivor.id,
        absorbed_opportunity_id=absorbed.id,
        rule=candidate.rule,
        score=candidate.score,
        status=candidate.status,
        decided_by=candidate.decided_by,
        decided_at=candidate.decided_at,
        created_at=candidate.created_at,
    )


def _relevance_mark_response(mark: RelevanceMarkModel) -> RelevanceMarkResponse:
    return RelevanceMarkResponse(
        id=mark.id,
        relevant=mark.relevant,
        reason=mark.reason,
        note=mark.note,
        profile_version_id=mark.profile_version_id,
        marked_at=mark.marked_at,
    )


def _opportunity_response(
    opportunity: OpportunityModel,
    *,
    session: Session | None = None,
    owner_sub: str | None = None,
) -> OpportunityResponse:
    current_mark = None
    if session is not None and owner_sub is not None:
        current_mark = OpportunityRepository(session).current_relevance_mark(
            opportunity.id, owner_sub=owner_sub
        )
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
        role_family=opportunity.role_family,
        role_family_evidence=opportunity.role_family_evidence,
        role_family_version=opportunity.role_family_version,
        published_at=opportunity.published_at,
        source_updated_at=opportunity.source_updated_at,
        recency_effective_date=recency_reference(
            published_at=opportunity.published_at,
            source_updated_at=opportunity.source_updated_at,
            first_seen_at=opportunity.first_seen_at,
        )[0],
        date_is_estimated=opportunity.recency_basis != RecencyBasis.PUBLISHED.value,
        recency_basis=opportunity.recency_basis,
        valid_through=opportunity.valid_through,
        recency_exempt_program=opportunity.recency_exempt_program,
        created_at=opportunity.created_at,
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
        relevance_mark=(
            _relevance_mark_response(current_mark) if current_mark is not None else None
        ),
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
        payload_retained=occurrence.payload_expired_at is None,
        payload_expired_at=occurrence.payload_expired_at,
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
