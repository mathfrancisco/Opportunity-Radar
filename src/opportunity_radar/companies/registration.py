"""Company and ATS registration by an operator, under the importer's identity rules.

The importer is not the only writer of the catalogue any more: a company quoted in a job,
a corrected name or a board the research missed can now be entered from the interface.
This module is that entry. It reuses the importer's normalization and reconciliation
instead of carrying a second definition of "the same company", and it is stricter than
the importer in one place: an operator typing a domain that already belongs to another
company is told so, because a silent merge by domain is not something a person asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.domain import AcquisitionError
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.proposals import (
    ProposalChangedError,
    ProposalFollowUp,
    follow_correction,
)
from opportunity_radar.companies.domain import (
    AmbiguousCompanyIdentityError,
    CompanyCandidate,
    normalize_domain,
    normalize_name,
)
from opportunity_radar.companies.models import (
    Company,
    CompanyAlias,
    CompanySource,
    CompanySourceRevision,
)
from opportunity_radar.companies.repository import CompanyRepository
from opportunity_radar.companies.service import CompanyService

PRIORITIES = ("high", "normal", "low")
RADAR_STATUSES = ("active", "paused")
# The ATS types a proposal can be made from; anything else has no collector to feed.
SUPPORTED_ATS = ("ashby", "lever", "greenhouse")


class CompanyRegistrationError(ValueError):
    """A request the catalogue refuses, attributed to the field that caused it."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class CompanyIdentityConflictError(CompanyRegistrationError):
    """The request would give one identity to two companies, or two to one."""


class CompanyVersionConflictError(ValueError):
    pass


class CompanyNotFoundError(LookupError):
    pass


class CompanySourceNotFoundError(LookupError):
    pass


@dataclass(slots=True)
class RegistrationResult:
    company: Company
    # `matched`: the name was already known, so the existing company answered and the
    # typed name became an alias of it instead of a second company.
    outcome: Literal["created", "matched"]
    aliases_added: int


class CompanyRegistration:
    def __init__(self, repository: CompanyRepository) -> None:
        self.repository = repository
        self.session = repository.session

    def register(
        self,
        *,
        name: str,
        domain: str | None,
        priority: str,
        radar_status: str,
        aliases: tuple[str, ...],
    ) -> RegistrationResult:
        _check_vocabulary(priority, radar_status)
        candidate = CompanyCandidate(
            name=name.strip(),
            domain=_domain_or_refuse(domain),
            aliases=aliases,
            priority=priority,
        )
        if not candidate.normalized_name:
            raise CompanyRegistrationError("company name cannot be empty", field="name")
        names = (candidate.normalized_name, *candidate.normalized_aliases)
        matches = self.repository.by_identity_names(names)
        if len(matches) > 1:
            raise CompanyIdentityConflictError(
                "the name and aliases match more than one company: "
                + ", ".join(sorted(company.canonical_name for company in matches)),
                field="aliases",
            )
        owner = (
            self.repository.by_domain(candidate.normalized_domain)
            if candidate.normalized_domain
            else None
        )
        if owner is not None and (not matches or owner.id != matches[0].id):
            raise CompanyIdentityConflictError(
                f"domain {candidate.normalized_domain} already belongs to "
                f"{owner.canonical_name}",
                field="domain",
            )
        try:
            result = CompanyService(self.repository).reconcile(candidate)
        except AmbiguousCompanyIdentityError as error:
            raise CompanyIdentityConflictError(str(error), field="domain") from error
        company = result.company
        if company is None:
            raise CompanyRegistrationError("company name cannot be empty", field="name")
        if result.created:
            company.radar_status = radar_status
        self._commit()
        return RegistrationResult(
            company=company,
            outcome="created" if result.created else "matched",
            aliases_added=result.aliases_added,
        )

    def update(
        self,
        company_id: UUID,
        *,
        expected_version: int,
        name: str,
        domain: str | None,
        priority: str,
        radar_status: str,
        aliases: tuple[str, ...],
    ) -> Company:
        company = self.repository.get(company_id)
        if company is None:
            raise CompanyNotFoundError(company_id)
        if company.version != expected_version:
            raise CompanyVersionConflictError(
                "company was changed; refresh it before updating"
            )
        _check_vocabulary(priority, radar_status)
        display_name = name.strip()
        normalized = normalize_name(display_name)
        if not normalized:
            raise CompanyRegistrationError("company name cannot be empty", field="name")
        normalized_domain = normalize_domain(_domain_or_refuse(domain))

        # A renamed company keeps answering to its old name, so the next import or the
        # next job that quotes it still lands here instead of creating a stranger.
        wanted_aliases = [typed.strip() for typed in aliases if typed.strip()]
        if normalized != company.normalized_name:
            wanted_aliases.append(company.canonical_name)
        desired: dict[str, str] = {}
        for typed in wanted_aliases:
            key = normalize_name(typed)
            if key and key != normalized and key not in desired:
                desired[key] = typed

        for key, field in ((normalized, "name"), *((key, "aliases") for key in desired)):
            others = [
                other
                for other in self.repository.by_identity_names((key,))
                if other.id != company.id
            ]
            if others:
                raise CompanyIdentityConflictError(
                    f"'{key}' already identifies {others[0].canonical_name}",
                    field=field,
                )
        if normalized_domain:
            owner = self.repository.by_domain(normalized_domain)
            if owner is not None and owner.id != company.id:
                raise CompanyIdentityConflictError(
                    f"domain {normalized_domain} already belongs to {owner.canonical_name}",
                    field="domain",
                )

        claimed = self.session.scalar(
            update(Company)
            .where(Company.id == company_id, Company.version == expected_version)
            .values(version=Company.version + 1)
            .returning(Company.id)
        )
        if claimed is None:
            self.session.rollback()
            raise CompanyVersionConflictError(
                "company was changed; refresh it before updating"
            )
        self.session.refresh(company)
        company.canonical_name = display_name
        company.normalized_name = normalized
        company.domain = normalized_domain
        company.priority = priority
        company.radar_status = radar_status
        for stored in list(company.aliases):
            if stored.normalized_alias not in desired:
                company.aliases.remove(stored)
        existing = {stored.normalized_alias for stored in company.aliases}
        for key, typed in desired.items():
            if key not in existing:
                company.aliases.append(CompanyAlias(alias=typed, normalized_alias=key))
        self._commit()
        return company

    def add_source(
        self,
        company_id: UUID,
        *,
        source_type: str,
        endpoint: str,
        external_key: str,
        evidence_note: str,
    ) -> CompanySource:
        company = self.repository.get(company_id)
        if company is None:
            raise CompanyNotFoundError(company_id)
        values = _source_values(source_type, endpoint, external_key, evidence_note)
        source = CompanySource(
            source_type=values["source_type"],
            endpoint=values["endpoint"],
            external_key=values["external_key"],
            evidence_note=values["evidence_note"],
            verification_status="ats_identified",
            verification_method="manual",
            last_verified_at=datetime.now(UTC),
            version=1,
        )
        source.revisions.append(
            CompanySourceRevision(
                version=1,
                changes={
                    field: {"from": None, "to": value}
                    for field, value in values.items()
                    if field != "evidence_note"
                },
                evidence_note=values["evidence_note"],
            )
        )
        company.sources.append(source)
        self._commit(duplicate="this company already has that ATS at that endpoint")
        return source

    def update_source(
        self,
        company_id: UUID,
        source_id: UUID,
        *,
        expected_version: int,
        source_type: str,
        endpoint: str,
        external_key: str,
        evidence_note: str,
    ) -> tuple[CompanySource, ProposalFollowUp]:
        source = self.repository.get_source(company_id, source_id)
        if source is None:
            raise CompanySourceNotFoundError(source_id)
        if source.version != expected_version:
            raise CompanyVersionConflictError(
                "company source was changed; refresh it before updating"
            )
        values = _source_values(source_type, endpoint, external_key, evidence_note)
        changes = {
            field: {"from": getattr(source, field), "to": value}
            for field, value in values.items()
            if field != "evidence_note" and getattr(source, field) != value
        }
        if not changes:
            raise CompanyRegistrationError(
                "nothing to correct: type, endpoint and external key are unchanged",
                field="external_key",
            )
        claimed = self.session.scalar(
            update(CompanySource)
            .where(CompanySource.id == source_id, CompanySource.version == expected_version)
            .values(version=CompanySource.version + 1)
            .returning(CompanySource.version)
        )
        if claimed is None:
            self.session.rollback()
            raise CompanyVersionConflictError(
                "company source was changed; refresh it before updating"
            )
        self.session.refresh(source)
        source.source_type = values["source_type"]
        source.endpoint = values["endpoint"]
        source.external_key = values["external_key"]
        source.evidence_note = values["evidence_note"]
        source.verification_method = "manual"
        source.last_verified_at = datetime.now(UTC)
        source.revisions.append(
            CompanySourceRevision(
                version=claimed,
                changes=changes,
                evidence_note=values["evidence_note"],
            )
        )
        self.session.flush()
        # The source proposed from this record either follows the correction in this same
        # transaction, or is reported as outdated; it is never left silently disagreeing.
        try:
            follow_up = follow_correction(self.session, source)
        except ProposalChangedError as error:
            self.session.rollback()
            raise CompanyVersionConflictError(
                "the source proposed from this record changed; refresh it and correct again"
            ) from error
        self._commit(duplicate="this company already has that ATS at that endpoint")
        return source, follow_up

    def _commit(self, *, duplicate: str | None = None) -> None:
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise CompanyIdentityConflictError(
                duplicate or "the change collides with an existing company identity"
            ) from error


def _check_vocabulary(priority: str, radar_status: str) -> None:
    if priority not in PRIORITIES:
        raise CompanyRegistrationError(
            f"priority must be one of {', '.join(PRIORITIES)}", field="priority"
        )
    if radar_status not in RADAR_STATUSES:
        raise CompanyRegistrationError(
            f"radar status must be one of {', '.join(RADAR_STATUSES)}",
            field="radar_status",
        )


def _domain_or_refuse(domain: str | None) -> str | None:
    """An empty domain is absent; a typed one that does not parse is refused, not dropped."""
    if domain is None or not domain.strip():
        return None
    if normalize_domain(domain) is None:
        raise CompanyRegistrationError(
            f"'{domain.strip()}' is not a domain", field="domain"
        )
    return domain


def _source_values(
    source_type: str, endpoint: str, external_key: str, evidence_note: str
) -> dict[str, str]:
    ats = source_type.strip().casefold()
    if ats not in SUPPORTED_ATS:
        raise CompanyRegistrationError(
            f"ATS type not supported: {source_type}; "
            f"supported types are {', '.join(SUPPORTED_ATS)}",
            field="source_type",
        )
    key = external_key.strip()
    validators = {
        "ashby": AshbyCollector.validate_board_identifier,
        "lever": LeverCollector.validate_site_slug,
        "greenhouse": GreenhouseCollector.validate_board_token,
    }
    try:
        validators[ats](key)
    except AcquisitionError as error:
        raise CompanyRegistrationError(error.summary, field="external_key") from error
    url = endpoint.strip()
    if not url.startswith(("https://", "http://")):
        raise CompanyRegistrationError(
            "endpoint must be the http(s) address where the board was seen",
            field="endpoint",
        )
    note = evidence_note.strip()
    if not note:
        # The note is what a reviewer reads before homologating the proposed source.
        raise CompanyRegistrationError(
            "an evidence note is required: say where and how the board was confirmed",
            field="evidence_note",
        )
    return {
        "source_type": ats,
        "endpoint": url,
        "external_key": key,
        "evidence_note": note,
    }
