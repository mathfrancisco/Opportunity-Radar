"""Content-based classification rules (card F48-15, SPEC 48 section 4.8).

`seniority-v4`, `work-mode-v7` and `allowed-countries-v2` extend the title/location rules
with evidence found in the job description. Every value carries the literal snippet that
produced it; when no rule fires, or two rules disagree, the answer stays `UNKNOWN` (never a
guess). Precedence, in order: structured collector field > title/location > description.

These rules are **not active by default**: `Settings.content_classification_v4_enabled`
stays off until the precision gate (`gate_passes`, measured by
`scripts/measure_content_classification.py` on the human-labelled gold set) is met.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from opportunity_radar.opportunities.domain import (
    _WORK_MODE_DESCRIPTION_SECTION_PATTERNS,
    HOMOLOGATED_SENIORITY_FIELDS,
    Seniority,
    WorkMode,
    infer_seniority,
    infer_work_mode,
    normalize_location,
)

SENIORITY_MAPPING_VERSION_V4 = "seniority-v4"
WORK_MODE_VERSION_V7 = "work-mode-v7"

#: Minimum precision (per rule) on the labelled gold set before the v4/v7/v2 rules may be
#: activated (SPEC 48 decision 7 / card F48-15).
PRECISION_GATE = 0.90

_SNIPPET_RADIUS = 50


@dataclass(frozen=True, slots=True)
class RuleHit:
    value: Any
    rule: str
    evidence: str


def _snippet(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - _SNIPPET_RADIUS)
    end = min(len(text), match.end() + _SNIPPET_RADIUS)
    return re.sub(r"\s+", " ", text[start:end]).strip()


# ---------------------------------------------------------------------------------------
# seniority-v4 (description rules)
# ---------------------------------------------------------------------------------------

_NUM = r"(\d{1,2})"
_EXPERIENCE_TAIL_EN = r"years?\s*(?:of\s+)?(?:[a-z\-/]+\s+){0,3}?experience"
_EXPERIENCE_TAIL_PT = r"anos?\s+(?:de\s+)?(?:[a-zçãáéíóúêô\-/]+\s+){0,3}?experi[eê]ncia"
_RANGE_SEP = r"\s*(?:-|–|—|to|a|à|até|or)\s*"

#: `N-M years of experience` / `N a M anos de experiência`.
_YEARS_RANGE = re.compile(
    rf"\b{_NUM}{_RANGE_SEP}{_NUM}\s*\+?\s*(?:{_EXPERIENCE_TAIL_EN}|{_EXPERIENCE_TAIL_PT})"
    rf"|\bexperi[eê]ncia\s+(?:m[ií]nima\s+)?de\s+{_NUM}{_RANGE_SEP}{_NUM}\s*anos?\b"
)
#: `N+ years of experience`, `at least N years`, `minimum of N years`, `mínimo de N anos`.
_YEARS_MIN = re.compile(
    rf"(?:\b(?:at least|minimum(?: of)?|min\.?|m[ií]nimo(?: de)?|pelo menos)\s+{_NUM}\s*\+?\s*"
    rf"(?:years?|anos?)\b)"
    rf"|(?:\b{_NUM}\s*\+?\s*(?:{_EXPERIENCE_TAIL_EN}|{_EXPERIENCE_TAIL_PT}))"
    rf"|(?:\bexperi[eê]ncia\s+(?:m[ií]nima\s+)?de\s+{_NUM}\s*\+?\s*anos?\b)"
    rf"|(?:\bexperience\s+of\s+(?:at least\s+)?{_NUM}\s*\+?\s*years?\b)"
)
#: A years figure about the employer ("our 15 years of experience", "we have 10 years")
#: is not a requirement on the candidate.
_COMPANY_CONTEXT = re.compile(
    r"\b(?:our|we(?:'ve| have)?|the company has|nossa|nosso|temos|n[oó]s temos)\s+"
    r"(?:over\s+|more than\s+|almost\s+|mais de\s+|quase\s+)?$"
)

_ENTRY_PHRASES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bentry[- ]level\s+(?:position|role|job|opportunity|engineer|developer|analyst)\b"
    ),
    re.compile(r"\bthis\s+is\s+an?\s+entry[- ]level\b"),
    re.compile(
        r"\bno\s+(?:prior\s+|previous\s+|professional\s+)?experience\s+"
        r"(?:is\s+)?(?:required|needed|necessary)\b"
    ),
    re.compile(
        r"\b(?:sem|n[aã]o exige|n[aã]o [eé] necess[aá]ria?)\s+experi[eê]ncia(?:\s+pr[eé]via)?\b"
    ),
    re.compile(r"\bn[ií]vel\s+j[uú]nior\b"),
    re.compile(r"\b(?:looking for|seeking|hiring)\s+(?:a|an)\s+junior\b"),
    re.compile(r"\b(?:procuramos|buscamos)\s+(?:um|uma)?\s*(?:profissional\s+)?j[uú]nior\b"),
    re.compile(r"\bvaga\s+(?:para|de)\s+(?:profissional\s+)?j[uú]nior\b"),
)
_INTERN_PHRASES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bthis\s+(?:is\s+an?\s+)?internship\b"),
    re.compile(r"\b(?:vaga|programa|oportunidade)\s+(?:de|para)\s+est[aá]gio\b"),
    re.compile(r"\best[aá]gio\s+(?:em|de)\s+[a-zà-ÿ]+\b(?=.*\bcursando\b)"),
)


def _years_bucket_min(minimum: int) -> Seniority | None:
    """Bucket of a lower bound: 0-2 JUNIOR, 3-4 MID, 5+ SENIOR (5 belongs to SENIOR)."""
    if minimum <= 2:
        return Seniority.JUNIOR
    if minimum <= 4:
        return Seniority.MID
    return Seniority.SENIOR


def _years_bucket_range(low: int, high: int) -> Seniority | None:
    """Bucket of `low-high` years, or `None` when the range straddles two buckets.

    Explicit overlap handling: JUNIOR is 0-2 and MID is 3-5, SENIOR is 5+. A range is
    classified only when it sits entirely inside one bucket (`0-2` JUNIOR, `3-5` MID; a
    range whose lower bound is >= 5 is SENIOR). A straddling range (`2-4`, `1-3`, `3-6`)
    is ambiguous and yields no value. The boundary 5 is SENIOR only as a lower bound
    (`5-7`, `5+`); as the upper bound of a range starting at 3 or 4 it stays MID.
    """
    if low > high:
        return None
    if high <= 2:
        return Seniority.JUNIOR
    if low >= 5:
        return Seniority.SENIOR
    if low >= 3 and high <= 5:
        return Seniority.MID
    return None


def _description_hits(description_text: str) -> list[RuleHit]:
    hits: list[RuleHit] = []
    consumed: list[tuple[int, int]] = []

    def in_company_context(match: re.Match[str]) -> bool:
        return (
            _COMPANY_CONTEXT.search(description_text[max(0, match.start() - 60) : match.start()])
            is not None
        )

    for match in _YEARS_RANGE.finditer(description_text):
        if in_company_context(match):
            continue
        consumed.append(match.span())
        low, high = (int(group) for group in match.groups() if group is not None)
        bucket = _years_bucket_range(low, high)
        if bucket is not None:
            hits.append(
                RuleHit(bucket, "description_years_range", _snippet(description_text, match))
            )
        else:
            # An ambiguous range is still evidence of *some* level: record it as a null hit
            # so a lone straddling range never lets another weaker rule decide.
            hits.append(
                RuleHit(
                    None, "description_years_range_ambiguous", _snippet(description_text, match)
                )
            )
    for match in _YEARS_MIN.finditer(description_text):
        if any(start <= match.start() < end for start, end in consumed):
            continue
        if in_company_context(match):
            continue
        number = next(int(group) for group in match.groups() if group is not None)
        hits.append(
            RuleHit(
                _years_bucket_min(number),
                "description_years_min",
                _snippet(description_text, match),
            )
        )
    for pattern in _ENTRY_PHRASES:
        match = pattern.search(description_text)
        if match:
            hits.append(
                RuleHit(
                    Seniority.JUNIOR, "description_entry_phrase", _snippet(description_text, match)
                )
            )
    for pattern in _INTERN_PHRASES:
        match = pattern.search(description_text)
        if match:
            hits.append(
                RuleHit(
                    Seniority.INTERN, "description_intern_phrase", _snippet(description_text, match)
                )
            )
    return hits


def seniority_from_description(description: str | None) -> RuleHit | None:
    """Return the single description-derived level, or `None` (UNKNOWN).

    Every rule hit must agree on one level; an ambiguous range or two different levels
    (`5+ years` next to `entry-level`) mean no value is written.
    """
    text = normalize_location(description)
    if not text:
        return None
    hits = _description_hits(text)
    if not hits or any(hit.value is None for hit in hits):
        return None
    values = {hit.value for hit in hits}
    if len(values) != 1:
        return None
    return hits[0]


def classify_seniority_v4(
    title: str | None,
    description: str | None,
    metadata: Mapping[str, Any],
    *,
    source_type: str = "manual",
) -> tuple[Seniority, dict[str, str | None]]:
    """`seniority-v4`: structured field > title > description, with cited evidence."""
    structured_keys = HOMOLOGATED_SENIORITY_FIELDS.get(source_type, ())
    external = next(
        (
            value.strip()
            for key, value in metadata.items()
            if key.casefold() in structured_keys and isinstance(value, str) and value.strip()
        ),
        None,
    )
    structured = infer_seniority(None, None, {"seniority": external} if external else {})
    title_value = infer_seniority(title, None, {})
    conflict = (
        structured is not Seniority.UNKNOWN
        and title_value is not Seniority.UNKNOWN
        and structured is not title_value
    )

    def reason(
        value: Seniority, source: str, rule: str | None, evidence: str | None
    ) -> tuple[Seniority, dict[str, str | None]]:
        return value, {
            "code": "SENIORITY_CLASSIFICATION",
            "source": source,
            "rule": rule,
            "evidence": evidence,
            "external_value": external,
            "mapping_version": SENIORITY_MAPPING_VERSION_V4,
            "collector": source_type,
            "value": value.value,
        }

    if conflict or (external is not None and structured is Seniority.UNKNOWN):
        return reason(
            Seniority.UNKNOWN,
            "conflict" if conflict else "structured",
            "structured_conflict" if conflict else "structured_unmapped",
            external,
        )
    if external is not None:
        return reason(structured, "structured", "structured", external)
    if title_value is not Seniority.UNKNOWN:
        return reason(title_value, "title", "title", title)
    hit = seniority_from_description(description)
    if hit is not None:
        return reason(hit.value, "description", hit.rule, hit.evidence)
    return reason(Seniority.UNKNOWN, "none", None, None)


# ---------------------------------------------------------------------------------------
# work-mode-v7
# ---------------------------------------------------------------------------------------

_WORK_MODE_V7_EXTRA: dict[WorkMode, tuple[str, ...]] = {
    WorkMode.REMOTE: (
        r"\b100%\s+remote\b",
        r"\bthis\s+(?:is\s+)?(?:a\s+|an\s+)?(?:fully\s+)?remote\s+(?:role|position|job|opportunity)\b",
        r"\b(?:role|position)\s+is\s+(?:fully\s+|100%\s+)?remote\b",
        r"\btrabalho\s+(?:100%\s+)?remoto\b",
        r"\b(?:vaga|posi[cç][aã]o)\s+(?:100%\s+)?remot[ao]\b",
        r"\b(?:regime|modelo(?:\s+de\s+trabalho)?|formato)\s+(?:100%\s+)?remoto\b",
        r"\bhome\s*office\s+(?:100%|integral|total)\b",
    ),
    WorkMode.HYBRID: (
        r"\bhybrid\s+(?:role|position|schedule|work\s+arrangement)\b",
        r"\b(?:regime|modelo(?:\s+de\s+trabalho)?|formato|trabalho)\s+h[ií]brido\b",
        r"\bh[ií]brid[oa]\s*(?:\(|com\s+)?\d\s*(?:x|dias)\b",
        r"\b\d\s+days?\s+(?:a|per)\s+week\s+(?:in|at)\s+the\s+office\b",
    ),
    WorkMode.ONSITE: (
        r"\bpresencial\s+(?:\d\s+dias|integral|5x)\b",
        r"\b(?:regime|modelo(?:\s+de\s+trabalho)?|formato)\s+presencial\b",
        r"\bvaga\s+presencial\b",
        r"\bthis\s+is\s+an?\s+on[ -]?site\b",
        r"\bin[- ]office\s+(?:role|position)\b",
    ),
}

_WORK_MODE_V7_PATTERNS: dict[WorkMode, tuple[str, ...]] = {
    mode: _WORK_MODE_DESCRIPTION_SECTION_PATTERNS[mode] + _WORK_MODE_V7_EXTRA[mode]
    for mode in (WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE)
}


def _work_mode_description_hit(description_text: str) -> RuleHit | None:
    found: dict[WorkMode, RuleHit] = {}
    for mode, expressions in _WORK_MODE_V7_PATTERNS.items():
        for expression in expressions:
            match = re.search(expression, description_text)
            if match:
                found.setdefault(
                    mode, RuleHit(mode, "description_phrase", _snippet(description_text, match))
                )
    if len(found) == 1:
        return next(iter(found.values()))
    return None


def classify_work_mode_v7(
    title: str | None,
    location_text: str | None,
    metadata: Mapping[str, Any],
    description: str | None,
) -> tuple[WorkMode, dict[str, str | None]]:
    """`work-mode-v7`: structured/title/location signals > description phrases.

    Conflicting explicit signals fall back to `UNKNOWN` (same convention as v6).
    """
    general = infer_work_mode(title, location_text, metadata, None)
    description_text = normalize_location(description) or ""
    hit = _work_mode_description_hit(description_text) if description_text else None
    # A description that names two different modes is ambiguous for the description rule.
    description_value = hit.value if hit else WorkMode.UNKNOWN

    def reason(
        value: WorkMode, source: str, rule: str | None, evidence: str | None
    ) -> tuple[WorkMode, dict[str, str | None]]:
        return value, {
            "code": "WORK_MODE_CLASSIFICATION",
            "source": source,
            "rule": rule,
            "evidence": evidence,
            "mapping_version": WORK_MODE_VERSION_V7,
            "value": value.value,
        }

    if general is WorkMode.UNKNOWN:
        if hit is not None:
            return reason(description_value, "description", hit.rule, hit.evidence)
        return reason(WorkMode.UNKNOWN, "none", None, None)
    if description_value is WorkMode.UNKNOWN or description_value is general:
        source = (
            "title" if infer_work_mode(title, None, {}, None) is general else "location_or_metadata"
        )
        evidence = title if source == "title" else location_text
        return reason(general, source, "title_location_metadata", evidence)
    return reason(WorkMode.UNKNOWN, "conflict", "title_vs_description", None)


# ---------------------------------------------------------------------------------------
# precision gate
# ---------------------------------------------------------------------------------------


def gate_passes(
    precision_by_rule: Mapping[str, tuple[int, int]],
    *,
    threshold: float = PRECISION_GATE,
) -> bool:
    """`True` only when every rule reaches `threshold` precision on the gold set.

    `precision_by_rule` maps a rule to `(correct, emitted)`. A rule that emitted nothing
    on the gold set has no evidence of precision, and an empty report proves nothing, so
    both fail closed.
    """
    if not precision_by_rule:
        return False
    return all(
        emitted > 0 and correct / emitted >= threshold
        for correct, emitted in precision_by_rule.values()
    )
