"""HTTP contract for the Company Radar bounded context."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.companies.repository import CompanyRepository
from opportunity_radar.presentation.http.dependencies import get_session

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyAliasResponse(BaseModel):
    id: UUID
    alias: str


class CompanySourceResponse(BaseModel):
    id: UUID
    name: str
    url: str
    status: str
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
                last_verified_at=source.last_verified_at,
            )
            for source in company.sources
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
