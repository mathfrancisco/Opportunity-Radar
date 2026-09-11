from __future__ import annotations

from dataclasses import dataclass

from opportunity_radar.companies.domain import (
    AmbiguousCompanyIdentityError,
    CompanyCandidate,
    normalize_name,
)
from opportunity_radar.companies.models import Company, CompanyAlias, CompanySource
from opportunity_radar.companies.repository import CompanyRepository


@dataclass(slots=True)
class ReconciliationResult:
    company: Company | None
    created: bool = False
    aliases_added: int = 0
    sources_added: int = 0
    issue: str | None = None


class CompanyService:
    def __init__(self, repository: CompanyRepository) -> None:
        self.repository = repository

    def reconcile(self, candidate: CompanyCandidate) -> ReconciliationResult:
        if not candidate.name.strip() or not candidate.normalized_name:
            return ReconciliationResult(company=None, issue="invalid_name")
        matches = self.repository.find_candidates(candidate)
        if len(matches) > 1:
            raise AmbiguousCompanyIdentityError(
                f"multiple companies match '{candidate.name}'"
            )
        if matches:
            company = matches[0]
            normalized_domain = candidate.normalized_domain
            if normalized_domain and company.domain is None:
                company.domain = normalized_domain
            elif normalized_domain and company.domain != normalized_domain:
                raise AmbiguousCompanyIdentityError(
                    f"company '{candidate.name}' conflicts with domain '{company.domain}'"
                )
            added = self._add_aliases(company, candidate)
            return ReconciliationResult(
                company=company,
                aliases_added=added,
                sources_added=self._add_sources(company, candidate),
            )
        company = Company(
            canonical_name=candidate.name.strip(),
            normalized_name=candidate.normalized_name,
            domain=candidate.normalized_domain,
            priority=candidate.priority,
        )
        self.repository.session.add(company)
        self.repository.session.flush()
        return ReconciliationResult(
            company=company,
            created=True,
            aliases_added=self._add_aliases(company, candidate),
            sources_added=self._add_sources(company, candidate),
        )

    @staticmethod
    def _add_aliases(company: Company, candidate: CompanyCandidate) -> int:
        existing = {alias.normalized_alias for alias in company.aliases}
        added = 0
        aliases = (candidate.name, *candidate.aliases)
        for alias in aliases:
            normalized_alias = normalize_name(alias)
            if not normalized_alias or normalized_alias == company.normalized_name:
                continue
            if normalized_alias not in existing:
                company.aliases.append(
                    CompanyAlias(alias=alias.strip(), normalized_alias=normalized_alias)
                )
                existing.add(normalized_alias)
                added += 1
        return added

    @staticmethod
    def _add_sources(company: Company, candidate: CompanyCandidate) -> int:
        existing = {(source.source_type, source.endpoint) for source in company.sources}
        added = 0
        for source in candidate.sources:
            identity = (source.source_type.casefold().strip(), source.endpoint.strip())
            if not all(identity) or identity in existing:
                continue
            company.sources.append(
                CompanySource(source_type=identity[0], endpoint=identity[1])
            )
            existing.add(identity)
            added += 1
        return added
