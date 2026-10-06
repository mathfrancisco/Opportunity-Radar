"""Pure, deterministic normalization rules for collected opportunities."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from opportunity_radar.companies.domain import normalize_name
from opportunity_radar.opportunities.regions import (
    REGIONS_VERSION,
    resolve_allowed_countries,
)
from opportunity_radar.opportunities.role_family import (
    ROLE_FAMILY_VERSION,
    RoleFamily,
    classify_role_family,
    departments_from_metadata,
)


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


SKILL_TAXONOMY_VERSION = "skills-v4"
_MAX_DATABASE_AMOUNT = Decimal("999999999999.99")
_AMBIGUOUS_SKILL_ALIASES = frozenset({"go", "react"})
#: Aliases that are an ordinary word when lower-case ("a rag"): in prose they only match
#: as the acronym. Structured tags and skill lists are not prose, so any case matches.
_UPPERCASE_PROSE_ALIASES = frozenset({"rag"})


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


_LLM_ALIASES = (
    "llm",
    "llms",
    "large language model",
    "large language models",
    "modelos de linguagem",
)
_RAG_ALIASES = ("rag", "retrieval-augmented generation", "retrieval augmented generation")

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
    # Added by F20-02 curation (`docs/pesquisas/curadoria-skills-v2.md`) from
    # `scripts/unmatched_skill_terms.py` over the reference-machine acervo.
    # F50-05: the bare "ai" and "ml" aliases are gone (40% of the catalogue matched "AI"
    # in "AI-powered company" prose). `ai` is now specific terms only, and it includes the
    # `llm` and `rag` aliases, so a posting that matches either also matches `ai`.
    SkillTaxonomyEntry(
        "ai",
        (
            "artificial intelligence",
            "inteligência artificial",
            "machine learning",
            "aprendizado de máquina",
            "aprendizagem de máquina",
            "generative ai",
            "gen ai",
            "genai",
            "ia generativa",
            "agentic ai",
            "agentic",
            "ai agent",
            "ai agents",
            "ai engineer",
            "ai engineers",
            "ai engineering",
            "ml engineer",
            "ml engineers",
            "ai/ml",
            "ml/ai",
            *_LLM_ALIASES,
            *_RAG_ALIASES,
        ),
    ),
    # F50-05: skills of the active profile that the taxonomy lacked. Ids are the
    # casefolded profile name, because the profile side matches ids by exact equality.
    SkillTaxonomyEntry("llm", _LLM_ALIASES),
    SkillTaxonomyEntry("rag", _RAG_ALIASES),
    SkillTaxonomyEntry("spring boot", ("spring boot", "springboot", "spring-boot")),
    SkillTaxonomyEntry("nestjs", ("nestjs", "nest.js")),
    SkillTaxonomyEntry("vue", ("vue", "vue.js", "vuejs")),
    SkillTaxonomyEntry("react native", ("react native", "react-native", "reactnative")),
    # F20-02 follow-up (rotulagem humana): the bare "ci" alias was removed because
    # 82% of its real-corpus occurrences come from the company name "CI&T", not
    # from CI/CD content (docs/44-roadmap-fase-20/rotulagem/f20-02-curadoria-skills-v2.md).
    SkillTaxonomyEntry(
        "cicd",
        ("ci/cd", "continuous integration", "continuous deployment"),
    ),
    SkillTaxonomyEntry("observability", ("observability",)),
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
    #: Explicit application-window deadline (card F20-61), threaded from
    #: `CollectedItem.valid_through`. `None` for collectors that do not expose one.
    valid_through: datetime | None = None
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
    role_family: RoleFamily = RoleFamily.UNKNOWN
    role_family_evidence: dict[str, str] = field(default_factory=dict)
    role_family_version: str = ROLE_FAMILY_VERSION
    #: ISO country codes (or `regions.ANY_COUNTRY`) the `regions-v1` table resolved from
    #: `location_text`. Empty means unknown — office location is never allowed country,
    #: and this must never be read as "no country allowed" (card F17-06).
    allowed_countries: tuple[str, ...] = ()
    allowed_countries_version: str = REGIONS_VERSION
    #: Cited-evidence reasons of the content rules (F48-15); empty when they are off.
    classification_reasons: tuple[dict[str, str | None], ...] = ()
    #: Explicit application-window deadline (card F20-61), threaded from the
    #: collector when it exposes one (today only `jobposting.py`). `None` otherwise —
    #: never fabricated.
    valid_through: datetime | None = None
    #: Recency-filter exception signal (card F20-61): an estágio/trainee/entry-level/
    #: early-careers/residency program, which tends to stay open far longer than a
    #: single senior/mid role. Independent of `ContractType` — a program is still
    #: shown past the recency window even when its contract type is `UNKNOWN`.
    recency_exempt_program: bool = False


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


def _skill_pattern(alias: str, *, uppercase_only: bool = False) -> re.Pattern[str]:
    folded = alias.casefold()
    escaped = re.escape(folded.upper() if uppercase_only else folded)
    dotted_variant = r"(?!\.js\b)" if folded == "react" else ""
    return re.compile(
        rf"(?<![\w+#]){escaped}(?![\w+#]){dotted_variant}",
        0 if uppercase_only else re.IGNORECASE,
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
                occurrence = _skill_pattern(
                    alias,
                    uppercase_only=alias in _UPPERCASE_PROSE_ALIASES and not structured,
                ).search(text)
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


# card F20-XX: real postings from several ATSes (e.g. Nubank/Greenhouse) render work mode
# only inside the description body, in a standardized "Work Model for this Role" section,
# never in title/location/metadata. These patterns are intentionally narrow (the labelled
# section itself, or a "<mode> model" / "fully on-site" phrasing) rather than a bare
# \bremote\b / \bhybrid\b scan of the whole description, which would false-positive on a
# colleague's remote status ("partner with senior remote engineers") or generic
# remote-friendly-company boilerplate unrelated to this specific role.
_WORK_MODE_DESCRIPTION_SECTION_PATTERNS: dict[WorkMode, tuple[str, ...]] = {
    WorkMode.REMOTE: (
        r"\bwork model(?:\s+for\s+this\s+role)?\b[\s:\-]*\s*remote\b",
        r"\bremote\s+(?:work\s+)?model\b",
    ),
    WorkMode.HYBRID: (
        r"\bwork model(?:\s+for\s+this\s+role)?\b[\s:\-]*\s*hybrid\b",
        r"\bhybrid\s+(?:work\s+)?model\b",
    ),
    WorkMode.ONSITE: (
        r"\bwork model(?:\s+for\s+this\s+role)?\b[\s:\-]*\s*on[ -]?site\b",
        r"\bon[ -]?site\s+(?:work\s+)?model\b",
        r"\bfully\s+on[ -]?site\b",
        r"\bon[ -]?site\s+(?:role|position)\b",
        r"\bon[ -]?site\s+(?:\d+|one|two|three|four|five|six|seven)\s+days?\s+a\s+week\b",
    ),
}


def _work_mode_from_description(description_text: str) -> WorkMode:
    result = _infer_unique(
        (description_text,), _WORK_MODE_DESCRIPTION_SECTION_PATTERNS, WorkMode.UNKNOWN
    )
    return WorkMode(result)


def infer_work_mode(
    title: str | None,
    location_text: str | None,
    metadata: Mapping[str, Any],
    description: str | None = None,
) -> WorkMode:
    remote_flag = any(
        key.casefold() in {"isremote", "is_remote", "remote"} and value is True
        for key, value in metadata.items()
    )
    explicit_flag = "remote" if remote_flag else None
    general_result = WorkMode(
        _infer_unique(
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
    )
    description_text = normalize_location(description) or ""
    description_result = (
        _work_mode_from_description(description_text) if description_text else WorkMode.UNKNOWN
    )
    if general_result is WorkMode.UNKNOWN:
        return description_result
    if description_result is WorkMode.UNKNOWN or description_result is general_result:
        return general_result
    # Conflicting explicit signals (e.g. a hybrid title but a remote "Work Model" section)
    # deliberately fall back to UNKNOWN rather than silently favoring either — same
    # never-override convention as seniority_classification's structured/title conflict.
    return WorkMode.UNKNOWN


#: Lowest to highest. A title naming two levels takes the higher one ("Senior Staff
#: Engineer" is STAFF), so the order is part of the mapping version.
_SENIORITY_LADDER: tuple[Seniority, ...] = (
    Seniority.INTERN,
    Seniority.JUNIOR,
    Seniority.MID,
    Seniority.SENIOR,
    Seniority.STAFF,
    Seniority.LEAD,
    Seniority.MANAGER,
    Seniority.DIRECTOR,
)

# Level words, read on the case-folded title without accents ("Sênior" is "senior"). Order
# matters: a match is blanked before the next expression runs, so the longer phrase wins
# ("semi senior" is MID and its "senior" is never read). `None` blanks a phrase that only
# looks like a level.
_SENIORITY_WORDS: tuple[tuple[Seniority | None, str], ...] = (
    # A team name at several companies, used at every level; not the STAFF level.
    (None, r"\bmember of technical staff\b"),
    (None, r"\bmiddle east\b"),
    (None, r"\bmid[- ]market\b"),
    (None, r"\bpl[/-]?sql\b"),
    # An academic credential, not a job level (diagnostic in docs/44-roadmap-fase-20/
    # evidencias/diagnostico-vagas-junior-2026-09-28.md).
    (None, r"\bgraduate\s+(?:school|degree|program)\b"),
    (Seniority.DIRECTOR, r"\bhead of\b"),
    (Seniority.DIRECTOR, r"\bdirector\b|\bdiretor(?:a)?\b"),
    (Seniority.MANAGER, r"\bmanager\b|\bgerente\b"),
    (Seniority.LEAD, r"\blead\b|\blider\b"),
    # "especialista" and "principal" have no dedicated enum tier; both denote a deep
    # individual-contributor level closest to STAFF (card F17-06 scope).
    (Seniority.STAFF, r"\bstaff\b|\bespecialista\b|\bprincipal\b"),
    (Seniority.MID, r"\bsemi[- ]?senior\b|\bssr\b"),
    (Seniority.SENIOR, r"\bsenior\b|\bsr\b"),
    (Seniority.MID, r"\bmid(?:[- ]?level)?\b|\bmiddle\b|\bplen[oa]\b|\bpl\b"),
    # seniority-v5 (F52-02): "entry level" and "new grad" are a first job, not an
    # internship, and "associate" is the usual English word for the junior tier.
    (
        Seniority.JUNIOR,
        r"\bentry[ -]level\b|\bnew (?:college )?grad(?:uate)?\b|\bearly career\b"
        r"|\bjunior\b|\bjr\b|\bgraduate\b|\bassociate\b",
    ),
    # `trainee` and `apprentice`/`aprendiz` are entry programs, INTERN-equivalent in this
    # app's domain (F20-70).
    (
        Seniority.INTERN,
        r"\bintern(?:ship)?\b|\bestagi[oa]\b|\bestagiari[oa]s?\b|\btrainee\b"
        r"|\bapprentice\b|\baprendiz\b",
    ),
)

# Read only when the title has no level word: a numeral after the role, and a role that
# implies a level. "Senior Engineer II" is SENIOR, not MID.
_SENIORITY_IMPLIED: tuple[tuple[Seniority | None, str], ...] = (
    (Seniority.SENIOR, r"\biii\b"),
    (Seniority.MID, r"\bii\b"),
    # A lone "I" is a level only where a level numeral goes: closing the title or a part
    # of it ("Software Engineer I", "Engineer I - Payments").
    (Seniority.JUNIOR, r"(?<=[a-z)] )i\b(?=\s*(?:$|[-,|(/:]))"),
    (Seniority.SENIOR, r"\barchitect\b|\barquitet[oa]\b"),
)

# What may stand between two level words for them to be a range ("Pl/Sr", "Junior to
# Senior", "Pleno, Sênior e Especialista") rather than one compound level ("Senior Staff").
_SENIORITY_RANGE_CONNECTOR = re.compile(
    r"(?:\.|\([ao]\))?\s*(?:[/,&+]|,?\s*\b(?:e|ou|or|and|a|to|ate)\b)\s*"
)
# Only the individual-contributor levels form a range: "Manager, Senior Data Engineer" is
# an inverted title, not a posting open from senior to manager.
_SENIORITY_RANGE_LEVELS = frozenset(
    {Seniority.INTERN, Seniority.JUNIOR, Seniority.MID, Seniority.SENIOR, Seniority.STAFF}
)


def _fold_accents(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )


def _named_seniorities(
    text: str, words: tuple[tuple[Seniority | None, str], ...]
) -> tuple[Seniority, tuple[Seniority, ...]]:
    """The level `text` names and, when it names a range, the levels of that range."""
    found: list[tuple[int, int, Seniority]] = []
    for level, expression in words:
        for match in re.finditer(expression, text):
            if level is not None:
                found.append((match.start(), match.end(), level))
        text = re.sub(expression, lambda match: " " * len(match.group()), text)
    found.sort()
    in_range: set[Seniority] = set()
    for (_, end, first), (start, _, second) in zip(found, found[1:]):
        if (
            first is not second
            and {first, second} <= _SENIORITY_RANGE_LEVELS
            and _SENIORITY_RANGE_CONNECTOR.fullmatch(text[end:start])
        ):
            in_range.update((first, second))
    if in_range:
        # A range keeps its lowest level (SPEC 52, Q1); the evidence carries the rest.
        levels = tuple(level for level in _SENIORITY_LADDER if level in in_range)
        return levels[0], levels
    named = {level for _, _, level in found}
    if named == {Seniority.INTERN, Seniority.JUNIOR}:
        # "Associate Intern", "Graduate Trainee": the junior word describes the internship.
        return Seniority.INTERN, ()
    highest = next((level for level in reversed(_SENIORITY_LADDER) if level in named), None)
    return highest or Seniority.UNKNOWN, ()


def _infer_seniority(evidence: tuple[str, ...]) -> tuple[Seniority, tuple[Seniority, ...]]:
    results = set()
    for text in evidence:
        folded = _fold_accents(text)
        result = _named_seniorities(folded, _SENIORITY_WORDS)
        if result[0] is Seniority.UNKNOWN:
            result = _named_seniorities(folded, _SENIORITY_IMPLIED)
        if result[0] is not Seniority.UNKNOWN:
            results.add(result)
    # Two pieces of evidence that disagree stay UNKNOWN: neither is silently preferred.
    return results.pop() if len(results) == 1 else (Seniority.UNKNOWN, ())


def infer_seniority(
    title: str | None, location_text: str | None, metadata: Mapping[str, Any]
) -> Seniority:
    del location_text
    return _infer_seniority(
        _evidence_texts(
            title,
            metadata=metadata,
            metadata_keys=frozenset(
                {"seniority", "level", "experience_level", "experiencelevel"}
            ),
        )
    )[0]


#: v2 -> v3 (F20-70): fixed INTERN to also match the person/adjective form
#: "estagiário"/"estagiária" (was noun-only, "estágio"/"estágia"), and added
#: trainee/entry level/new grad/apprentice/aprendiz (INTERN) and early
#: career/graduate (JUNIOR) — see docs/44-roadmap-fase-20/fase-20/
#: f20-70-lacunas-de-palavra-chave-senioridade.md.
#:
#: v3 -> v5 (F52-02; `seniority-v4` names the description rules in
#: content_classification.py): accents are ignored; a title naming two levels takes the
#: higher one, or the lowest of an explicit range; numerals I/II/III, "architect", "head
#: of", "associate" and "semi senior" are read; "entry level" and "new grad" move from
#: INTERN to JUNIOR. Unlike v3, this changes titles that were already classified — see
#: docs/pesquisas/f52-02-reaplicacao-senioridade.md.
SENIORITY_MAPPING_VERSION = "seniority-v5"

# Collector payloads are intentionally listed even when they have no approved level
# field. Adding a field here is part of that collector's homologation, not a heuristic.
#
# seniority-v2 checked the real fixtures under tests/backend/acquisition/ for Ashby,
# Greenhouse and Lever payloads: none of them carry a structured seniority/level field
# (no key such as "level", "seniority", "experienceLevel" appears in any fixture), so
# those three collectors remain unmapped (()). Adding an entry later requires the same
# fixture evidence, per the mapping-version comment above.
HOMOLOGATED_SENIORITY_FIELDS: dict[str, tuple[str, ...]] = {
    "ashby": (),
    "greenhouse": (),
    "lever": (),
    "manual": ("seniority",),
    "remotive": (),
}


def seniority_classification(
    title: str | None, metadata: Mapping[str, Any], *, source_type: str = "manual"
) -> tuple[Seniority, dict[str, str | None]]:
    """Classify only explicit, reviewable seniority evidence.

    A structured value wins only when it maps unambiguously; conflicting structured and
    title values deliberately remain UNKNOWN rather than silently favoring either.
    """
    structured_keys = HOMOLOGATED_SENIORITY_FIELDS.get(source_type, ())
    external = next(
        (
            value.strip()
            for key, value in metadata.items()
            if key.casefold() in structured_keys
            and isinstance(value, str)
            and value.strip()
        ),
        None,
    )
    structured = infer_seniority(None, None, {"seniority": external} if external else {})
    title_value, title_range = _infer_seniority(
        _evidence_texts(title, metadata={}, metadata_keys=frozenset())
    )
    conflict = (
        structured is not Seniority.UNKNOWN
        and title_value is not Seniority.UNKNOWN
        and structured is not title_value
    )
    value = (
        Seniority.UNKNOWN
        if conflict or (external is not None and structured is Seniority.UNKNOWN)
        else structured if external is not None else title_value
    )
    source = "conflict" if conflict else "structured" if external else "title"
    return value, {
        "code": "SENIORITY_CLASSIFICATION",
        "source": source,
        "external_value": external,
        "mapping_version": SENIORITY_MAPPING_VERSION,
        "collector": source_type,
        "value": value.value,
        # The levels of a title that names a range ("Pl/Sr"); `value` is the lowest one.
        "range": ",".join(title_range) if source == "title" and title_range else None,
    }


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


#: Card F20-61: title/metadata evidence for "this is a time-boxed entry program"
#: (estágio/trainee/early-careers/residência) — the recency-filter exception signal.
#: Deliberately not a `ContractType` member: "trainee" is not the same thing as
#: "internship" for the rest of the system (e.g. `ContractType.INTERNSHIP` also
#: implies eligibility/matching semantics this signal must not carry). Reuses
#: `ContractType.INTERNSHIP`'s own patterns (estágio/internship) plus the additional
#: terms this card's exception explicitly covers.
_RECENCY_EXEMPT_PROGRAM_PATTERNS: tuple[str, ...] = (
    r"\binternship\b",
    r"\best[aá]gi[oa]\b",
    r"\best[aá]gi[áa]ri[oa]s?\b",
    r"\btrainee\b",
    r"\bresid[eê]ncia\b",
    r"\bresidency\b",
    r"\bearly[ -]?career[s]?\b",
    r"\bin[íi]cio de carreira\b",
)


def infer_recency_exempt_program(
    title: str | None, metadata: Mapping[str, Any], *, contract_type: ContractType
) -> bool:
    """Whether the recency filter's "programa com prazo" exception applies.

    True whenever the contract type is already `INTERNSHIP`, or the title/metadata
    otherwise names a time-boxed entry program (trainee/early-careers/residência) that
    `infer_contract_type`'s narrower pattern set does not classify as INTERNSHIP.
    """
    if contract_type is ContractType.INTERNSHIP:
        return True
    evidence = _evidence_texts(
        title,
        metadata=metadata,
        metadata_keys=frozenset(
            {"employmenttype", "employment_type", "commitment", "job_type", "categories"}
        ),
    )
    return any(
        re.search(pattern, text)
        for text in evidence
        for pattern in _RECENCY_EXEMPT_PROGRAM_PATTERNS
    )


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


def normalize_candidate(
    value: NormalizationInput, *, content_rules: bool | frozenset[str] = False
) -> CanonicalCandidate:
    """Normalize one collected item without guessing omitted source fields.

    `content_rules` switches to `seniority-v4` / `work-mode-v7` / `allowed-countries-v2`
    (card F48-15, description-aware, evidence cited): `True` runs every rule, a set of rule
    names runs only those (card F50-02), empty or `False` none. Off by default until the
    precision gate is met; see `content_classification`.
    """
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
    classification_reasons: tuple[dict[str, str | None], ...] = ()
    allowed_countries_version = REGIONS_VERSION
    if isinstance(content_rules, frozenset) and content_rules:
        from opportunity_radar.opportunities import content_classification as content

        partial = content.classify_enabled_rules(
            original_title,
            location_text,
            value.description,
            value.metadata,
            source_type=value.source_type,
            enabled_rules=content_rules,
        )
        work_mode = partial.work_mode
        seniority = partial.seniority
        allowed_countries = partial.allowed_countries
        allowed_countries_version = partial.allowed_countries_version
        classification_reasons = partial.reasons
    elif content_rules:
        from opportunity_radar.opportunities import content_classification as content
        from opportunity_radar.opportunities.regions import (
            REGIONS_VERSION_V2,
            resolve_allowed_countries_v2,
        )

        work_mode, work_mode_reason = content.classify_work_mode_v7(
            original_title, location_text, value.metadata, value.description
        )
        seniority, seniority_reason = content.classify_seniority_v4(
            original_title, value.description, value.metadata, source_type=value.source_type
        )
        allowed_countries, countries_evidence = resolve_allowed_countries_v2(
            location_text, value.description
        )
        allowed_countries_version = REGIONS_VERSION_V2
        classification_reasons = (
            seniority_reason,
            work_mode_reason,
            content.allowed_countries_reason(allowed_countries, countries_evidence),
        )
    else:
        work_mode = infer_work_mode(
            original_title, location_text, value.metadata, value.description
        )
        seniority, _ = seniority_classification(
            original_title, value.metadata, source_type=value.source_type
        )
        allowed_countries = resolve_allowed_countries(location_text)
    contract_type = infer_contract_type(original_title, location_text, value.metadata)
    recency_exempt_program = infer_recency_exempt_program(
        original_title, value.metadata, contract_type=contract_type
    )
    role_family_decision = classify_role_family(
        title=original_title,
        departments=departments_from_metadata(value.metadata),
        description=value.description,
    )
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
        role_family=role_family_decision.role_family,
        role_family_evidence=dict(role_family_decision.evidence),
        role_family_version=role_family_decision.version,
        allowed_countries=allowed_countries,
        allowed_countries_version=allowed_countries_version,
        classification_reasons=classification_reasons,
        valid_through=value.valid_through,
        recency_exempt_program=recency_exempt_program,
    )


def build_candidate(
    value: NormalizationInput, *, content_rules: bool | frozenset[str] = False
) -> CanonicalCandidate:
    """Compatibility entry point for the original normalization slice."""
    return normalize_candidate(value, content_rules=content_rules)


#: Card F20-61 / F48-16: the default search shows only a posting whose reference date
#: (`recency_reference`) is inside this window. Not a matching/scoring parameter — never
#: read by `score`, eligibility or verdict (same Phase 20 invariant
#: `opportunity_fingerprint`/role-family classification follow). Decision 3 (spec 48 §9)
#: moved the default from 14 to 30 days; 14 stays available as the "Novas" lens.
DEFAULT_RECENCY_WINDOW_DAYS = 30
NEW_RECENCY_WINDOW_DAYS = 14


class RecencyBasis(StrEnum):
    """Which date the recency reference came from (persisted as `recency_basis`)."""

    PUBLISHED = "published"
    UPDATED = "updated"
    FIRST_SEEN = "first_seen"


def recency_reference(
    *,
    published_at: datetime | None,
    source_updated_at: datetime | None,
    first_seen_at: datetime | None,
) -> tuple[datetime | None, RecencyBasis]:
    """The single recency rule (card F48-16): `published_at ?? source_updated_at ??
    first_seen_at`, plus which of the three won.

    SQL mirror: `dashboard.queries._recency_reference_expression` (COALESCE in the same
    order); `tests/backend/opportunities/test_recency_filter.py` locks the two together.
    """
    if published_at is not None:
        return published_at, RecencyBasis.PUBLISHED
    if source_updated_at is not None:
        return source_updated_at, RecencyBasis.UPDATED
    return first_seen_at, RecencyBasis.FIRST_SEEN


def recency_basis_of(
    *, published_at: datetime | None, source_updated_at: datetime | None
) -> RecencyBasis:
    """The persisted basis. `first_seen_at` always exists, so it never affects the basis."""
    return recency_reference(
        published_at=published_at, source_updated_at=source_updated_at, first_seen_at=None
    )[1]


@dataclass(frozen=True, slots=True)
class RecencyDecision:
    """Whether one opportunity belongs in the default (recency-filtered) listing.

    `effective_date` is `published_at ?? source_updated_at ?? first_seen_at` with
    `basis` telling which (`date_is_estimated` whenever it is not `published`) — never a
    fabricated date. `visible` is `True` when any of three independent conditions holds:
    the effective date is inside the window, the posting is a time-boxed entry program
    (estágio/trainee/early-careers/residência), or `valid_through` names an application
    deadline still in the future. Toggling the filter off (card F20-61 scope item 3)
    is the caller's job — this always answers "would the filter show it", regardless
    of whether the caller applies that answer.
    """

    visible: bool
    effective_date: datetime | None
    date_is_estimated: bool
    basis: RecencyBasis = RecencyBasis.FIRST_SEEN


def recency_decision(
    *,
    published_at: datetime | None,
    first_seen_at: datetime | None,
    valid_through: datetime | None,
    recency_exempt_program: bool,
    now: datetime,
    window_days: int = DEFAULT_RECENCY_WINDOW_DAYS,
    source_updated_at: datetime | None = None,
) -> RecencyDecision:
    """Pure, deterministic recency calculation (cards F20-61 and F48-16).

    `now` is always supplied by the caller — this function never reads the clock, so
    tests can freeze time and cover both sides of the window boundary exactly.
    """
    effective_date, basis = recency_reference(
        published_at=published_at,
        source_updated_at=source_updated_at,
        first_seen_at=first_seen_at,
    )
    date_is_estimated = basis is not RecencyBasis.PUBLISHED and effective_date is not None
    within_window = (
        effective_date is not None and effective_date >= now - timedelta(days=window_days)
    )
    has_open_deadline = valid_through is not None and valid_through > now
    visible = within_window or recency_exempt_program or has_open_deadline
    return RecencyDecision(
        visible=visible,
        effective_date=effective_date,
        date_is_estimated=date_is_estimated,
        basis=basis,
    )
