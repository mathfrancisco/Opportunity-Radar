"""HTTP contract for the Company Radar bounded context."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.proposals import is_outdated, proposal_key
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.companies.registration import (
    CompanyIdentityConflictError,
    CompanyNotFoundError,
    CompanyRegistration,
    CompanyRegistrationError,
    CompanySourceNotFoundError,
    CompanyVersionConflictError,
)
from opportunity_radar.companies.repository import CompanyRepository
from opportunity_radar.presentation.http.dependencies import get_session

router = APIRouter(prefix="/companies", tags=["companies"])

SOURCE_ORDER = {
    "api_json_confirmed": 0,
    "ats_identified": 1,
    "careers_confirmed": 2,
    "research_recorded": 3,
    "backlog": 4,
}


class CompanyAliasResponse(BaseModel):
    id: UUID
    alias: str


class CompanySourceRevisionResponse(BaseModel):
    version: int
    changed_at: datetime
    changes: dict[str, Any]
    evidence_note: str


class ProposedSourceResponse(BaseModel):
    """The source proposed from an ATS record, as it reads today."""

    source_id: UUID
    source_type: str
    external_key: str | None
    enabled: bool
    evidence_status: str
    terms_reviewed: bool
    collector_local_tested: bool
    version: int
    # True when the record was corrected after the proposal and the proposal did not follow.
    outdated: bool


class CompanySourceResponse(BaseModel):
    id: UUID
    name: str
    url: str
    status: str
    external_key: str | None
    verification_method: str | None
    evidence: str | None
    last_verified_at: datetime | None
    version: int
    revisions: list[CompanySourceRevisionResponse]
    proposal: ProposedSourceResponse | None = None


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    domain: str | None
    priority: str
    status: str
    verification_state: str
    aliases: list[CompanyAliasResponse]
    sources: list[CompanySourceResponse]
    created_at: datetime
    updated_at: datetime
    version: int


class CompanyBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=253)
    priority: Literal["high", "normal", "low"] = "normal"
    radar_status: Literal["active", "paused"] = "active"
    aliases: list[str] = Field(default_factory=list, max_length=50)


class CompanyUpdateBody(CompanyBody):
    expected_version: int = Field(ge=1)


class CompanyRegistrationResponse(BaseModel):
    outcome: Literal["created", "matched"]
    aliases_added: int
    company: CompanyResponse


class CompanySourceBody(BaseModel):
    source_type: str = Field(min_length=1, max_length=50)
    endpoint: str = Field(min_length=1, max_length=2048)
    external_key: str = Field(min_length=1, max_length=255)
    evidence_note: str = Field(min_length=1, max_length=4000)


class CompanySourceUpdateBody(CompanySourceBody):
    expected_version: int = Field(ge=1)


class CompanySourceCorrectionResponse(BaseModel):
    # `updated`: the proposal was inert and now reads the corrected board.
    # `outdated`: the proposal was reviewed, tested or enabled and was left as it was.
    proposal_outcome: Literal["none", "updated", "outdated"]
    source: CompanySourceResponse


class CompanyPageResponse(BaseModel):
    items: list[CompanyResponse]
    page: int
    page_size: int
    total: int


class SourceProposalResponse(BaseModel):
    result: str
    source_id: UUID | None
    evidence: str | None
    enabled: bool = False


def proposals_for(
    session: Session, companies: list[Company]
) -> dict[UUID, SourceDefinitionModel]:
    """The source proposed from each ATS record, fetched once for a whole page."""
    record_ids = [source.id for company in companies for source in company.sources]
    if not record_ids:
        return {}
    proposals = session.scalars(
        select(SourceDefinitionModel)
        .where(SourceDefinitionModel.company_source_id.in_(record_ids))
        .order_by(SourceDefinitionModel.created_at)
    )
    found: dict[UUID, SourceDefinitionModel] = {}
    for proposal in proposals:
        if proposal.company_source_id is not None:
            found.setdefault(proposal.company_source_id, proposal)
    return found


def company_response(
    company: Company, proposals: dict[UUID, SourceDefinitionModel] | None = None
) -> CompanyResponse:
    return CompanyResponse(
        id=company.id,
        name=company.canonical_name,
        domain=company.domain,
        priority=company.priority,
        status=company.radar_status,
        verification_state=company.verification_state,
        aliases=[
            CompanyAliasResponse(id=alias.id, alias=alias.alias)
            for alias in company.aliases
        ],
        sources=[
            company_source_response(source, (proposals or {}).get(source.id))
            for source in sorted(
                company.sources,
                key=lambda item: (
                    SOURCE_ORDER.get(item.verification_status, 99),
                    item.source_type,
                    item.endpoint,
                ),
            )
        ],
        created_at=company.created_at,
        updated_at=company.updated_at,
        version=company.version,
    )


def company_source_response(
    source: CompanySource, proposal: SourceDefinitionModel | None = None
) -> CompanySourceResponse:
    return CompanySourceResponse(
        id=source.id,
        name=source.source_type,
        url=source.endpoint,
        status=source.verification_status,
        external_key=source.external_key,
        verification_method=source.verification_method,
        evidence=source.evidence_note,
        last_verified_at=source.last_verified_at,
        version=source.version,
        revisions=[
            CompanySourceRevisionResponse(
                version=revision.version,
                changed_at=revision.changed_at,
                changes=revision.changes,
                evidence_note=revision.evidence_note,
            )
            for revision in source.revisions
        ],
        proposal=(
            ProposedSourceResponse(
                source_id=proposal.id,
                source_type=proposal.source_type,
                external_key=proposal_key(proposal),
                enabled=proposal.enabled,
                evidence_status=proposal.evidence_status,
                terms_reviewed=proposal.terms_reviewed,
                collector_local_tested=proposal.collector_local_tested,
                version=proposal.version,
                outdated=is_outdated(proposal, source),
            )
            if proposal is not None
            else None
        ),
    )


@router.post(
    "",
    response_model=CompanyRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_company(
    body: CompanyBody, session: Session = Depends(get_session)
) -> CompanyRegistrationResponse:
    repository = CompanyRepository(session)
    try:
        result = CompanyRegistration(repository).register(
            name=body.name,
            domain=body.domain,
            priority=body.priority,
            radar_status=body.radar_status,
            aliases=tuple(body.aliases),
        )
    except CompanyRegistrationError as error:
        _raise_registration_error(error)
    company = repository.get(result.company.id)
    assert company is not None
    return CompanyRegistrationResponse(
        outcome=result.outcome,
        aliases_added=result.aliases_added,
        company=company_response(company, proposals_for(session, [company])),
    )


@router.get("", response_model=CompanyPageResponse)
def list_companies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    q: str | None = Query(default=None, min_length=1, max_length=255),
    priority: str | None = Query(default=None, max_length=20),
    radar_status: str | None = Query(default=None, max_length=20),
    session: Session = Depends(get_session),
) -> CompanyPageResponse:
    companies, total = CompanyRepository(session).list(
        offset=(page - 1) * page_size,
        limit=page_size,
        search=q,
        priority=priority,
        radar_status=radar_status,
    )
    proposals = proposals_for(session, companies)
    return CompanyPageResponse(
        items=[company_response(company, proposals) for company in companies],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: UUID,
    session: Session = Depends(get_session),
) -> CompanyResponse:
    company = CompanyRepository(session).get(company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "company_not_found", "message": "Company not found."},
        )
    return company_response(company, proposals_for(session, [company]))


@router.patch("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID,
    body: CompanyUpdateBody,
    session: Session = Depends(get_session),
) -> CompanyResponse:
    repository = CompanyRepository(session)
    try:
        CompanyRegistration(repository).update(
            company_id,
            expected_version=body.expected_version,
            name=body.name,
            domain=body.domain,
            priority=body.priority,
            radar_status=body.radar_status,
            aliases=tuple(body.aliases),
        )
    except (
        CompanyNotFoundError,
        CompanyVersionConflictError,
        CompanyRegistrationError,
    ) as error:
        _raise_registration_error(error)
    company = repository.get(company_id)
    assert company is not None
    return company_response(company, proposals_for(session, [company]))


@router.post(
    "/{company_id}/sources",
    response_model=CompanySourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_company_source(
    company_id: UUID,
    body: CompanySourceBody,
    session: Session = Depends(get_session),
) -> CompanySourceResponse:
    repository = CompanyRepository(session)
    try:
        source = CompanyRegistration(repository).add_source(
            company_id, **body.model_dump()
        )
    except (CompanyNotFoundError, CompanyRegistrationError) as error:
        _raise_registration_error(error)
    return company_source_response(source)


@router.patch(
    "/{company_id}/sources/{source_id}", response_model=CompanySourceCorrectionResponse
)
def update_company_source(
    company_id: UUID,
    source_id: UUID,
    body: CompanySourceUpdateBody,
    session: Session = Depends(get_session),
) -> CompanySourceCorrectionResponse:
    repository = CompanyRepository(session)
    try:
        source, follow_up = CompanyRegistration(repository).update_source(
            company_id, source_id, **body.model_dump()
        )
    except (
        CompanySourceNotFoundError,
        CompanyVersionConflictError,
        CompanyRegistrationError,
    ) as error:
        _raise_registration_error(error)
    return CompanySourceCorrectionResponse(
        proposal_outcome=follow_up.outcome,
        source=company_source_response(source, follow_up.proposal),
    )


def _raise_registration_error(error: Exception) -> NoReturn:
    if isinstance(error, CompanyNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "company_not_found", "message": "Company not found."},
        ) from error
    if isinstance(error, CompanySourceNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "company_source_not_found",
                "message": "Company source not found.",
            },
        ) from error
    if isinstance(error, CompanyVersionConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_conflict", "message": str(error)},
        ) from error
    if isinstance(error, CompanyIdentityConflictError):
        detail: dict[str, str] = {"code": "identity_conflict", "message": str(error)}
        if error.field is not None:
            detail["field"] = error.field
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from error
    if isinstance(error, CompanyRegistrationError):
        detail = {"code": "invalid_company", "message": str(error)}
        if error.field is not None:
            detail["field"] = error.field
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail
        ) from error
    raise error


@router.post("/{company_id}/detect-source", response_model=SourceProposalResponse)
def detect_source(
    company_id: UUID, session: Session = Depends(get_session)
) -> SourceProposalResponse:
    proposal, result = AcquisitionService(session).propose_company_source(company_id)
    if proposal is None:
        return SourceProposalResponse(result=result, source_id=None, evidence=None)
    evidence = proposal.configuration.get("discovery_evidence")
    return SourceProposalResponse(
        result=result,
        source_id=proposal.id,
        evidence=evidence if isinstance(evidence, str) else None,
        enabled=proposal.enabled,
    )
