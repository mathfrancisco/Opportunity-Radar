from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.companies.domain import CompanyCandidate, normalize_name
from opportunity_radar.companies.models import Company, CompanyAlias, CompanyImportBatch


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_candidates(self, candidate: CompanyCandidate) -> list[Company]:
        identity_aliases = (candidate.normalized_name, *candidate.normalized_aliases)
        clauses = [
            Company.normalized_name.in_(identity_aliases),
            CompanyAlias.normalized_alias.in_(identity_aliases),
        ]
        statement: Select[tuple[Company]] = (
            select(Company)
            .outerjoin(CompanyAlias)
            .where(or_(*clauses))
            .options(selectinload(Company.aliases))
        )
        matches = list(self.session.scalars(statement).unique())
        if candidate.normalized_domain:
            by_domain = self.session.scalar(
                select(Company)
                .where(Company.domain == candidate.normalized_domain)
                .options(selectinload(Company.aliases))
            )
            if by_domain is not None and all(
                company.id != by_domain.id for company in matches
            ):
                matches.append(by_domain)
        return matches

    def list(
        self,
        *,
        offset: int,
        limit: int,
        search: str | None,
        priority: str | None,
        radar_status: str | None,
    ) -> tuple[list[Company], int]:
        filters = []
        if search:
            term = f"%{normalize_name(search)}%"
            filters.append(
                or_(
                    Company.normalized_name.like(term),
                    Company.aliases.any(CompanyAlias.normalized_alias.like(term)),
                )
            )
        if priority:
            filters.append(Company.priority == priority)
        if radar_status:
            filters.append(Company.radar_status == radar_status)
        statement = (
            select(Company)
            .where(*filters)
            .options(selectinload(Company.aliases), selectinload(Company.sources))
        )
        companies = list(
            self.session.scalars(
                statement.order_by(Company.canonical_name).offset(offset).limit(limit)
            )
        )
        total = self.session.scalar(select(func.count(Company.id)).where(*filters)) or 0
        return companies, total

    def get(self, company_id: UUID) -> Company | None:
        statement = select(Company).where(Company.id == company_id).options(
            selectinload(Company.aliases), selectinload(Company.sources)
        )
        return self.session.scalar(statement)

    def completed_batch(self, file_hash: str) -> CompanyImportBatch | None:
        return self.session.scalar(
            select(CompanyImportBatch).where(
                CompanyImportBatch.file_hash == file_hash,
                CompanyImportBatch.status == "completed",
            )
        )

    def batch_by_hash(self, file_hash: str) -> CompanyImportBatch | None:
        return self.session.scalar(
            select(CompanyImportBatch)
            .where(CompanyImportBatch.file_hash == file_hash)
            .options(selectinload(CompanyImportBatch.issues))
        )
