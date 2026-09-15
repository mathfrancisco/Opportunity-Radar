"""Pure, deterministic normalization rules for collected opportunities."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
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


class CompensationPeriod(StrEnum):
    YEAR = "YEAR"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    HOUR = "HOUR"
    UNKNOWN = "UNKNOWN"


class GrossNet(StrEnum):
    GROSS = "GROSS"
    NET = "NET"
    UNKNOWN = "UNKNOWN"


class SkillClassification(StrEnum):
    REQUIRED = "REQUIRED"
    PREFERRED = "PREFERRED"
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


SKILL_TAXONOMY_VERSION = "skills-v1"
_MAX_DATABASE_AMOUNT = Decimal("999999999999.99")
_AMBIGUOUS_SKILL_ALIASES = frozenset({"go", "react"})


@dataclass(frozen=True, slots=True)
class Compensation:
    """Source-declared monetary range, kept separate from any inferred value."""

    minimum: Decimal | None
    maximum: Decimal | None
    currency: str | None
    period: CompensationPeriod | None
    gross_net: GrossNet | None
    evidence: str
    evidence_source: str

    def __post_init__(self) -> None:
        if any(
            value is not None and not isinstance(value, Decimal)
            for value in (self.minimum, self.maximum)
        ):
            raise NormalizationError("compensation amounts must use Decimal")
        if self.minimum is None and self.maximum is None:
            raise NormalizationError("compensation requires a minimum or maximum")
        if self.minimum is not None and self.minimum < 0:
            raise NormalizationError("compensation minimum must not be negative")
        if self.maximum is not None and self.maximum < 0:
            raise NormalizationError("compensation maximum must not be negative")
        for amount in (self.minimum, self.maximum):
            if amount is None:
                continue
            if amount > _MAX_DATABASE_AMOUNT:
                raise NormalizationError("compensation amount exceeds database precision")
            if amount.quantize(Decimal("0.01")) != amount:
                raise NormalizationError("compensation amount supports at most two decimals")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise NormalizationError("compensation minimum must not exceed maximum")
        if self.currency is not None and not re.fullmatch(
            r"[A-Z]{3}", self.currency
        ):
            raise NormalizationError("compensation currency must be an ISO 4217 code")
        if not _clean_text(self.evidence):
            raise NormalizationError("compensation requires source evidence")
        if not _clean_text(self.evidence_source):
            raise NormalizationError("compensation requires an evidence source")


@dataclass(frozen=True, slots=True)
class SkillTaxonomyEntry:
    canonical_id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtractedSkill:
    canonical_id: str
    evidence_text: str
    classification: SkillClassification
    taxonomy_version: str = SKILL_TAXONOMY_VERSION

    def __post_init__(self) -> None:
        if not self.canonical_id or not _clean_text(self.evidence_text):
            raise NormalizationError("extracted skill requires an id and evidence")


SKILL_TAXONOMY: tuple[SkillTaxonomyEntry, ...] = (
    SkillTaxonomyEntry("python", ("python",)),
    SkillTaxonomyEntry("typescript", ("typescript",)),
    SkillTaxonomyEntry("javascript", ("javascript",)),
    SkillTaxonomyEntry("react", ("react", "react.js", "reactjs")),
    SkillTaxonomyEntry("nextjs", ("next.js", "nextjs")),
    SkillTaxonomyEntry("nodejs", ("node.js", "nodejs")),
    SkillTaxonomyEntry("fastapi", ("fastapi",)),
    SkillTaxonomyEntry("django", ("django",)),
    SkillTaxonomyEntry("flask", ("flask",)),
    SkillTaxonomyEntry("java", ("java",)),
    SkillTaxonomyEntry("kotlin", ("kotlin",)),
    SkillTaxonomyEntry("go", ("golang", "go")),
    SkillTaxonomyEntry("rust", ("rust",)),
    SkillTaxonomyEntry("csharp", ("c#", "csharp", "c-sharp")),
    SkillTaxonomyEntry("dotnet", (".net", "dotnet", ".net core")),
    SkillTaxonomyEntry("sql", ("sql",)),
    SkillTaxonomyEntry("postgresql", ("postgresql", "postgres")),
    SkillTaxonomyEntry("mysql", ("mysql",)),
    SkillTaxonomyEntry("mongodb", ("mongodb", "mongo db")),
    SkillTaxonomyEntry("redis", ("redis",)),
    SkillTaxonomyEntry("docker", ("docker",)),
    SkillTaxonomyEntry("kubernetes", ("kubernetes", "k8s")),
    SkillTaxonomyEntry("aws", ("aws", "amazon web services")),
    SkillTaxonomyEntry("azure", ("azure",)),
    SkillTaxonomyEntry("gcp", ("gcp", "google cloud platform")),
    SkillTaxonomyEntry("terraform", ("terraform",)),
    SkillTaxonomyEntry("graphql", ("graphql",)),
)


@dataclass(frozen=True, slots=True)
class NormalizationInput:
    """The stable ``collected_item_v1`` contract consumed by normalization."""

    raw_item_id: UUID
    source_definition_id: UUID
    source_type: str
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
        if not _clean_text(self.source_type):
            raise NormalizationError("normalization input requires a source type")
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
    compensation: Compensation | None = None
    skills: tuple[ExtractedSkill, ...] = ()
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


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    serialized = str(value).strip()
    if isinstance(value, str):
        serialized = _normalize_decimal_separators(serialized)
    try:
        result = Decimal(serialized)
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _normalize_decimal_separators(value: str) -> str:
    compact = value.replace(" ", "")
    if "," in compact and "." in compact:
        if compact.rfind(",") > compact.rfind("."):
            return compact.replace(".", "").replace(",", ".")
        return compact.replace(",", "")
    if "," in compact:
        groups = compact.split(",")
        if len(groups) == 2 and len(groups[1]) in {1, 2}:
            return ".".join(groups)
        return "".join(groups)
    if "." in compact:
        groups = compact.split(".")
        if len(groups) > 2 or (len(groups) == 2 and len(groups[1]) == 3):
            return "".join(groups)
    return compact


def _first_present(value: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None


def _compensation_from_range(value: Any, evidence_source: str) -> Compensation | None:
    if not isinstance(value, Mapping):
        return None
    minimum = _decimal(_first_present(value, ("min", "minValue")))
    maximum = _decimal(_first_present(value, ("max", "maxValue")))
    if minimum is None and maximum is None:
        return None
    currency = _first_present(value, ("currency", "currencyCode"))
    normalized_currency = (
        currency.strip().upper()
        if isinstance(currency, str) and re.fullmatch(r"[A-Za-z]{3}", currency.strip())
        else None
    )
    period = _period_from_text(
        _first_present(value, ("interval", "period", "unit"))
    )
    gross_net = _gross_net_from_text(value.get("grossNet") or value.get("type"))
    return Compensation(
        minimum=minimum,
        maximum=maximum,
        currency=normalized_currency,
        period=period,
        gross_net=gross_net,
        evidence=json.dumps(dict(value), ensure_ascii=False, sort_keys=True),
        evidence_source=evidence_source,
    )


def _period_from_text(value: Any) -> CompensationPeriod | None:
    if not isinstance(value, str):
        return None
    text = value.casefold()
    matches = {
        period
        for period, patterns in {
            CompensationPeriod.YEAR: (r"\byear", r"\bannual", r"\bannum"),
            CompensationPeriod.MONTH: (r"\bmonth", r"\bmonthly"),
            CompensationPeriod.WEEK: (r"\bweek", r"\bweekly"),
            CompensationPeriod.DAY: (r"\bday", r"\bdaily"),
            CompensationPeriod.HOUR: (r"\bhour", r"\bhourly"),
        }.items()
        if any(re.search(pattern, text) for pattern in patterns)
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _gross_net_from_text(value: Any) -> GrossNet | None:
    if not isinstance(value, str):
        return None
    text = value.casefold()
    gross = bool(re.search(r"\bgross\b|\bbruto\b", text))
    net = bool(re.search(r"\bnet\b|\bl[ií]quido\b", text))
    if gross == net:
        return None
    return GrossNet.GROSS if gross else GrossNet.NET


_TEXT_COMPENSATION = re.compile(
    r"(?P<currency>\b(?:USD|BRL|EUR|GBP|CAD|AUD)\b)?\s*"
    r"(?P<currency_symbol>[$€£])?\s*"
    r"(?P<first>\d[\d,.]*\s*[kK]?)"
    r"(?:\s*(?:-|–|to|a|até)\s*"
    r"(?:(?:USD|BRL|EUR|GBP|CAD|AUD)\s*)?[$€£]?\s*"
    r"(?P<second>\d[\d,.]*\s*[kK]?))?"
    r"(?:\s*(?P<currency_after>\b(?:USD|BRL|EUR|GBP|CAD|AUD)\b))?"
    r"(?:\s*(?:per|/|por)\s*(?P<period>year|yearly|annual|month|monthly|week|weekly|day|daily|hour|hourly))?",
    re.IGNORECASE,
)


def _text_compensation(
    value: str | None, *, evidence_source: str
) -> Compensation | None:
    text = _clean_text(value)
    if text is None:
        return None
    for match in _TEXT_COMPENSATION.finditer(text):
        first = _money_amount(match.group("first"))
        second = _money_amount(match.group("second"))
        if first is None:
            continue
        # A bare number in a description is not compensation evidence.
        nearby = text[max(0, match.start() - 48) : match.end() + 48]
        currency_symbol = match.group("currency_symbol")
        if not (
            match.group("currency")
            or match.group("currency_after")
            or currency_symbol
            or re.search(
                r"\b(?:salary|compensation|pay|remunera[çc][ãa]o)\b", nearby, re.I
            )
        ):
            continue
        currency = (
            match.group("currency")
            or match.group("currency_after")
            or {"€": "EUR", "£": "GBP"}.get(currency_symbol or "")
            or ""
        ).upper()
        try:
            return Compensation(
                minimum=first,
                maximum=second,
                currency=currency or None,
                period=_period_from_text(nearby),
                gross_net=_gross_net_from_text(nearby),
                evidence=match.group(0).strip(),
                evidence_source=evidence_source,
            )
        except NormalizationError:
            continue
    return None


def _money_amount(value: str | None) -> Decimal | None:
    if value is None:
        return None
    normalized = value.replace(" ", "")
    multiplier = (
        Decimal("1000") if normalized.casefold().endswith("k") else Decimal("1")
    )
    amount = _decimal(normalized.rstrip("kK"))
    return amount * multiplier if amount is not None else None


def extract_compensation(
    metadata: Mapping[str, Any],
    description: str | None,
    *,
    source_type: str = "unknown",
) -> Compensation | None:
    """Prefer source-structured compensation, then explicit source text."""
    lever = _compensation_from_range(
        metadata.get("salaryRange"), f"{source_type}.salaryRange"
    )
    if lever is not None:
        return lever

    ashby = metadata.get("compensation")
    if not isinstance(ashby, Mapping) and isinstance(
        metadata.get("summaryComponents"), (list, tuple)
    ):
        ashby = metadata
    if isinstance(ashby, Mapping):
        components = ashby.get("summaryComponents")
        if isinstance(components, (list, tuple)):
            for component in components:
                if not isinstance(component, Mapping):
                    continue
                component_type = (
                    component.get("type")
                    or component.get("name")
                    or component.get("componentType")
                    or component.get("compensationType")
                )
                if (
                    isinstance(component_type, str)
                    and component_type.casefold() == "salary"
                ):
                    value = component.get("compensationRange", component)
                    result = _compensation_from_range(
                        value, f"{source_type}.compensation.summaryComponents.Salary"
                    )
                    if result is not None:
                        return result

    salary = metadata.get("salary")
    remotive = _text_compensation(
        salary if isinstance(salary, str) else None,
        evidence_source=f"{source_type}.salary",
    )
    return (
        remotive
        if remotive is not None
        else _text_compensation(description, evidence_source="description")
    )


def _skill_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias.casefold())
    dotted_variant = r"(?!\.js\b)" if alias.casefold() == "react" else ""
    return re.compile(
        rf"(?<![\w+#]){escaped}(?![\w+#]){dotted_variant}", re.IGNORECASE
    )


def _classify_skill(text: str, occurrence: re.Match[str]) -> SkillClassification:
    context = text[max(0, occurrence.start() - 200) : occurrence.start()]
    required = list(
        re.finditer(
            r"\b(?:required|requirements?|must(?:\s+have)?|mandatory|obrigat[óo]ri[oa])\b",
            context,
            re.I,
        )
    )
    preferred = list(
        re.finditer(
            r"\b(?:preferred|nice to have|bonus|differential|desej[áa]vel)\b",
            context,
            re.I,
        )
    )
    if not required and not preferred:
        return SkillClassification.UNKNOWN
    if not preferred or (required and required[-1].start() > preferred[-1].start()):
        return SkillClassification.REQUIRED
    return SkillClassification.PREFERRED


def _skill_evidence(text: str, occurrence: re.Match[str]) -> str:
    start = max(
        text.rfind("\n", 0, occurrence.start()),
        text.rfind(".", 0, occurrence.start()),
        text.rfind(";", 0, occurrence.start()),
    )
    end_candidates = [
        position
        for position in (
            text.find("\n", occurrence.end()),
            text.find(".", occurrence.end()),
            text.find(";", occurrence.end()),
        )
        if position >= 0
    ]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    return text[start + 1 : end].strip()[:500]


def _is_unambiguous_skill_use(
    alias: str,
    text: str,
    occurrence: re.Match[str],
    *,
    structured: bool,
    title: bool,
) -> bool:
    if alias.casefold() not in _AMBIGUOUS_SKILL_ALIASES or structured:
        return True
    expected_case = {"go": "Go", "react": "React"}[alias.casefold()]
    if occurrence.group(0) != expected_case:
        return False
    if title:
        if alias.casefold() == "go" and re.search(
            r"\bgo[- ]to[- ]market\b", text, re.IGNORECASE
        ):
            return False
        return bool(
            re.search(
                r"\b(?:developer|engineer|architect|programmer|desenvolvedor|"
                r"engenheiro|arquiteto|programador)\b",
                text,
                re.IGNORECASE,
            )
        )
    context = text[max(0, occurrence.start() - 80) : occurrence.end() + 80]
    return bool(
        re.search(
            r"(?:experience|proficiency|knowledge)\s+(?:with|in|of)|"
            r"(?:required|preferred|skills?|stack)\s*:?|"
            r"(?:experi[eê]ncia|profici[eê]ncia|conhecimento)\s+(?:com|em|de)|"
            r"(?:obrigat[óo]ri[oa]|desej[áa]vel|compet[eê]ncias?|stack)\s*:?",
            context,
            re.IGNORECASE,
        )
    )


def extract_skills(
    title: str | None, description: str | None, metadata: Mapping[str, Any]
) -> tuple[ExtractedSkill, ...]:
    """Extract only taxonomy aliases with word boundaries and direct evidence."""
    metadata_texts: list[str] = []
    for key in ("tags", "skills"):
        value = metadata.get(key)
        if isinstance(value, str):
            metadata_texts.append(value)
        elif isinstance(value, (list, tuple)):
            metadata_texts.extend(item for item in value if isinstance(item, str))
    texts: list[tuple[str, bool, bool]] = []
    for index, value in enumerate((title, description)):
        cleaned = _clean_text(value)
        if cleaned is not None:
            texts.append((cleaned, False, index == 0))
    for value in metadata_texts:
        cleaned = _clean_text(value)
        if cleaned is not None:
            texts.append((cleaned, True, False))
    matches: dict[str, list[tuple[SkillClassification, str]]] = {}
    for text, structured, title_text in texts:
        for entry in SKILL_TAXONOMY:
            for alias in entry.aliases:
                occurrence = _skill_pattern(alias).search(text)
                if occurrence is not None:
                    if not _is_unambiguous_skill_use(
                        alias,
                        text,
                        occurrence,
                        structured=structured,
                        title=title_text,
                    ):
                        continue
                    matches.setdefault(entry.canonical_id, []).append(
                        (_classify_skill(text, occurrence), _skill_evidence(text, occurrence))
                    )
                    break
    extracted: list[ExtractedSkill] = []
    for canonical_id, occurrences in matches.items():
        classifications = {
            classification
            for classification, _ in occurrences
            if classification is not SkillClassification.UNKNOWN
        }
        classification = (
            next(iter(classifications))
            if len(classifications) == 1
            else SkillClassification.UNKNOWN
        )
        evidence = next(
            (
                evidence_text
                for occurrence_classification, evidence_text in occurrences
                if occurrence_classification is classification
            ),
            occurrences[0][1],
        )
        extracted.append(
            ExtractedSkill(
                canonical_id=canonical_id,
                evidence_text=evidence,
                classification=classification,
            )
        )
    return tuple(extracted)


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


def normalize_candidate(value: NormalizationInput) -> CanonicalCandidate:
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
        compensation=extract_compensation(
            value.metadata,
            value.description,
            source_type=value.source_type,
        ),
        skills=extract_skills(original_title, value.description, value.metadata),
    )


def build_candidate(value: NormalizationInput) -> CanonicalCandidate:
    """Compatibility entry point for the original normalization slice."""
    return normalize_candidate(value)
