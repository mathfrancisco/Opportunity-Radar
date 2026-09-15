"""Pure, deterministic normalization rules for collected opportunities."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from opportunity_radar.companies.domain import normalize_name


class WorkMode(StrEnum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    UNKNOWN = "UNKNOWN"


class Seniority(StrEnum):
    INTERN = "INTERN"
    JUNIOR = "JUNIOR"
    MID = "MID"
    SENIOR = "SENIOR"
    STAFF = "STAFF"
    LEAD = "LEAD"
    MANAGER = "MANAGER"
    DIRECTOR = "DIRECTOR"
    UNKNOWN = "UNKNOWN"


class ContractType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    TEMPORARY = "TEMPORARY"
    UNKNOWN = "UNKNOWN"


class OpportunityStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"
    REJECTED = "REJECTED"

    def can_transition_to(self, status: OpportunityStatus) -> bool:
        return status in {
            OpportunityStatus.DISCOVERED: {
                OpportunityStatus.ACTIVE,
                OpportunityStatus.CLOSED,
                OpportunityStatus.REJECTED,
                OpportunityStatus.ARCHIVED,
            },
            OpportunityStatus.ACTIVE: {
                OpportunityStatus.STALE,
                OpportunityStatus.CLOSED,
                OpportunityStatus.ARCHIVED,
            },
            OpportunityStatus.STALE: {
                OpportunityStatus.ACTIVE,
                OpportunityStatus.CLOSED,
                OpportunityStatus.ARCHIVED,
            },
            OpportunityStatus.CLOSED: {
                OpportunityStatus.ACTIVE,
                OpportunityStatus.ARCHIVED,
            },
            OpportunityStatus.REJECTED: {OpportunityStatus.ARCHIVED},
            OpportunityStatus.ARCHIVED: set(),
        }[self]

    def require_transition_to(self, status: OpportunityStatus) -> None:
        if not self.can_transition_to(status):
            raise NormalizationError(f"invalid opportunity status transition: {self} -> {status}")


class NormalizationError(ValueError):
    """Raised when a collected item cannot form a canonical candidate."""


@dataclass(frozen=True, slots=True)
class NormalizationInput:
    """The stable ``collected_item_v1`` contract consumed by normalization."""

    raw_item_id: UUID
    source_definition_id: UUID
    external_id: str | None = None
    url: str | None = None
    title: str | None = None
    company_name: str | None = None
    location_text: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    company_id: UUID | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _clean_text(self.title):
            raise NormalizationError("normalization input requires a title")
        if not _clean_text(self.external_id) and not _clean_text(self.url):
            raise NormalizationError("normalization input requires an external_id or url")


@dataclass(frozen=True, slots=True)
class CanonicalCandidate:
    original_title: str
    normalized_title: str
    company_id: UUID | None
    company_name: str | None
    normalized_company_name: str | None
    source_url: str | None
    normalized_url: str | None
    location_text: str | None
    normalized_location: str | None
    work_mode: WorkMode
    seniority: Seniority
    contract_type: ContractType
    description: str | None
    published_at: datetime | None
    source_updated_at: datetime | None
    fingerprint: str
    fingerprint_version: str = "v1"


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = unicodedata.normalize("NFKC", value).strip()
    return cleaned or None


def normalize_title(value: str | None) -> str | None:
    """Return the title comparison key while retaining ``+`` and ``#`` semantics."""
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    key = "".join(
        character if character.isalnum() or character in "+#" else " "
        for character in cleaned.casefold()
    )
    return re.sub(r"\s+", " ", key).strip() or None


def normalize_company_name(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    return normalize_name(cleaned) if cleaned else None


def normalize_location(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    return re.sub(r"\s+", " ", cleaned.casefold()).strip() or None


def normalize_url(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    try:
        parsed = urlsplit(cleaned)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return None
    hostname = parsed.hostname.casefold()
    netloc = hostname
    if port is not None:
        netloc = f"{hostname}:{port}"
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not (
                key.casefold().startswith("utm_")
                or key.casefold() in {"ref", "source"}
            )
        ),
        doseq=True,
    )
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))


def _evidence_texts(
    *values: str | None,
    metadata: Mapping[str, Any],
    metadata_keys: frozenset[str],
) -> tuple[str, ...]:
    evidence = [value for value in values if _clean_text(value)]

    def visit(value: Any) -> None:
        if isinstance(value, str):
            if _clean_text(value):
                evidence.append(value)
        elif isinstance(value, Mapping):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for nested in value:
                visit(nested)

    for key, value in metadata.items():
        if key.casefold() in metadata_keys:
            visit(value)
    return tuple(normalize_location(value) or "" for value in evidence)


def _infer_unique(
    evidence: tuple[str, ...], patterns: Mapping[Any, tuple[str, ...]], unknown: StrEnum
) -> StrEnum:
    matches = {
        value
        for value, expressions in patterns.items()
        if any(
            re.search(expression, text)
            for text in evidence
            for expression in expressions
        )
    }
    return next(iter(matches)) if len(matches) == 1 else unknown


def infer_work_mode(
    title: str | None, location_text: str | None, metadata: Mapping[str, Any]
) -> WorkMode:
    remote_flag = any(
        key.casefold() in {"isremote", "is_remote", "remote"} and value is True
        for key, value in metadata.items()
    )
    explicit_flag = "remote" if remote_flag else None
    result = _infer_unique(
        _evidence_texts(
            title,
            location_text,
            explicit_flag,
            metadata=metadata,
            metadata_keys=frozenset(
                {"workplacetype", "workplace_type", "remote_scope", "categories"}
            ),
        ),
        {
            WorkMode.REMOTE: (r"\bremote\b", r"\bremoto\b", r"\bremota\b"),
            WorkMode.HYBRID: (r"\bhybrid\b", r"\bh[ií]brid[oa]\b"),
            WorkMode.ONSITE: (r"\bon[ -]?site\b", r"\bpresencial\b"),
        },
        WorkMode.UNKNOWN,
    )
    return WorkMode(result)


def infer_seniority(
    title: str | None, location_text: str | None, metadata: Mapping[str, Any]
) -> Seniority:
    del location_text
    result = _infer_unique(
        _evidence_texts(
            title,
            metadata=metadata,
            metadata_keys=frozenset(
                {"seniority", "level", "experience_level", "experiencelevel"}
            ),
        ),
        {
            Seniority.INTERN: (r"\bintern(ship)?\b", r"\best[aá]gi[oa]\b"),
            Seniority.JUNIOR: (r"\bjunior\b", r"\bjr\.?\b"),
            Seniority.MID: (r"\bmid(?:[- ]level)?\b", r"\bmiddle\b", r"\bpleno\b"),
            Seniority.SENIOR: (r"\bsenior\b", r"\bsr\.?\b"),
            Seniority.STAFF: (r"\bstaff\b",),
            Seniority.LEAD: (r"\blead\b", r"\bl[ií]der\b"),
            Seniority.MANAGER: (r"\bmanager\b", r"\bgerente\b"),
            Seniority.DIRECTOR: (r"\bdirector\b", r"\bdiretor\b"),
        },
        Seniority.UNKNOWN,
    )
    return Seniority(result)


def infer_contract_type(
    title: str | None, location_text: str | None, metadata: Mapping[str, Any]
) -> ContractType:
    del location_text
    result = _infer_unique(
        _evidence_texts(
            title,
            metadata=metadata,
            metadata_keys=frozenset(
                {
                    "employmenttype",
                    "employment_type",
                    "commitment",
                    "job_type",
                    "contract_type",
                    "categories",
                }
            ),
        ),
        {
            ContractType.FULL_TIME: (r"\bfull[ -]?time\b", r"\btempo integral\b"),
            ContractType.PART_TIME: (r"\bpart[ -]?time\b", r"\bmeio per[ií]odo\b"),
            ContractType.CONTRACT: (r"\bcontract(or)?\b", r"\bcontractual\b"),
            ContractType.INTERNSHIP: (r"\binternship\b", r"\best[aá]gio\b"),
            ContractType.TEMPORARY: (r"\btemporary\b", r"\btemp\b", r"\btempor[áa]ri[oa]\b"),
        },
        ContractType.UNKNOWN,
    )
    return ContractType(result)


def opportunity_fingerprint(
    *,
    company_id: UUID | None,
    normalized_company_name: str | None,
    normalized_title: str,
    normalized_location: str | None,
    work_mode: WorkMode,
    contract_type: ContractType,
    published_at: datetime | None,
    identity_fallback: str | None = None,
) -> str:
    """Build a versioned exact-match key; publication day prevents stale merges."""
    company_key = (
        str(company_id)
        if company_id
        else normalized_company_name or f"source:{identity_fallback or 'unknown'}"
    )
    published_day = published_at.date().isoformat() if published_at else "unknown"
    material = "\x1f".join(
        (
            "v1",
            company_key,
            normalized_title,
            normalized_location or "unknown",
            work_mode.value,
            contract_type.value,
            published_day,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_candidate(value: NormalizationInput) -> CanonicalCandidate:
    """Normalize one collected item without guessing omitted source fields."""
    original_title = _clean_text(value.title)
    normalized_title = normalize_title(value.title)
    if original_title is None or normalized_title is None:
        raise NormalizationError("normalization input requires a usable title")
    company_name = _clean_text(value.company_name)
    location_text = _clean_text(value.location_text)
    source_url = _clean_text(value.url)
    normalized_company_name = normalize_company_name(company_name)
    normalized_location = normalize_location(location_text)
    normalized_url = normalize_url(source_url)
    work_mode = infer_work_mode(original_title, location_text, value.metadata)
    seniority = infer_seniority(original_title, location_text, value.metadata)
    contract_type = infer_contract_type(original_title, location_text, value.metadata)
    return CanonicalCandidate(
        original_title=original_title,
        normalized_title=normalized_title,
        company_id=value.company_id,
        company_name=company_name,
        normalized_company_name=normalized_company_name,
        source_url=source_url,
        normalized_url=normalized_url,
        location_text=location_text,
        normalized_location=normalized_location,
        work_mode=work_mode,
        seniority=seniority,
        contract_type=contract_type,
        description=_clean_text(value.description),
        published_at=value.published_at,
        source_updated_at=value.updated_at,
        fingerprint=opportunity_fingerprint(
            company_id=value.company_id,
            normalized_company_name=normalized_company_name,
            normalized_title=normalized_title,
            normalized_location=normalized_location,
            work_mode=work_mode,
            contract_type=contract_type,
            published_at=value.published_at,
            identity_fallback=(
                f"{value.source_definition_id}:"
                f"{_clean_text(value.external_id) or normalized_url or value.raw_item_id}"
            ),
        ),
    )
