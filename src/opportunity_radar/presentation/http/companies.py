"""HTTP contract for the Company Radar bounded context."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import Company
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


class CompanySourceResponse(BaseModel):
    id: UUID
    name: str
    url: str
    status: str
    external_key: str | None
    verification_method: str | None
    evidence: str | None
    last_verified_at: datetime | None


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    domain: str | None
    priority: str
    status: str
    verification_state: str
    aliases: list[CompanyAliasResponse]
    sources: list[CompanySourceResponse]


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


def company_response(company: Company) -> CompanyResponse:
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
            CompanySourceResponse(
                id=source.id,
                name=source.source_type,
                url=source.endpoint,
                status=source.verification_status,
                external_key=source.external_key,
                verification_method=source.verification_method,
                evidence=source.evidence_note,
                last_verified_at=source.last_verified_at,
            )
            for source in sorted(
                company.sources,
                key=lambda item: (
                    SOURCE_ORDER.get(item.verification_status, 99),
                    item.source_type,
                    item.endpoint,
                ),
            )
        ],
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
    return CompanyPageResponse(
        items=[company_response(company) for company in companies],
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
    return company_response(company)


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
