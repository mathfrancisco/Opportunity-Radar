"""Versioned region-to-country resolution for `location_text` (card F17-06, `regions-v1`).

Office location is never allowed country. This module only resolves the *permission*
signals a location text carries on its face — "Remote — Brazil", "LATAM", "Anywhere" — to
ISO 3166-1 alpha-2 country codes. It never guesses: text that names neither a known region
nor a known country resolves to an empty tuple, which callers must treat as unknown, not
as "no country allowed".
"""

from __future__ import annotations

import re

REGIONS_VERSION = "regions-v1"

#: Sentinel standing for "any country" — used for regions with no fixed member list
#: (Anywhere/Worldwide/Global). Never confused with "unknown": unknown is `()`.
ANY_COUNTRY = "ANY"

LATAM_COUNTRIES: tuple[str, ...] = (
    "AR", "BO", "BR", "CL", "CO", "CR", "CU", "DO", "EC", "SV",
    "GT", "HN", "MX", "NI", "PA", "PY", "PE", "PR", "UY", "VE",
)

AMERICAS_COUNTRIES: tuple[str, ...] = LATAM_COUNTRIES + ("US", "CA")

EMEA_COUNTRIES: tuple[str, ...] = (
    "PT", "ES", "FR", "DE", "IT", "NL", "BE", "IE", "GB", "SE",
    "NO", "DK", "FI", "PL", "CH", "AT", "GR", "RO", "HU", "CZ",
    "AE", "SA", "IL", "TR", "ZA", "NG", "KE", "EG", "MA",
)

REGIONS: dict[str, tuple[str, ...]] = {
    "LATAM": LATAM_COUNTRIES,
    "AMERICAS": AMERICAS_COUNTRIES,
    "EMEA": EMEA_COUNTRIES,
    "ANYWHERE": (ANY_COUNTRY,),
    "WORLDWIDE": (ANY_COUNTRY,),
}

#: Country names/aliases (casefolded, accent-sensitive as typed) recognized after
#: "Remote — <country>" / "Remoto (<país>)" patterns, or as the whole location text.
_COUNTRY_NAME_TO_CODE: dict[str, str] = {
    "brazil": "BR",
    "brasil": "BR",
    "mexico": "MX",
    "méxico": "MX",
    "argentina": "AR",
    "chile": "CL",
    "colombia": "CO",
    "colômbia": "CO",
    "peru": "PE",
    "perú": "PE",
    "uruguay": "UY",
    "uruguai": "UY",
    "paraguay": "PY",
    "paraguai": "PY",
    "bolivia": "BO",
    "bolívia": "BO",
    "ecuador": "EC",
    "equador": "EC",
    "costa rica": "CR",
    "panama": "PA",
    "panamá": "PA",
    "united states": "US",
    "usa": "US",
    "estados unidos": "US",
    "canada": "CA",
    "canadá": "CA",
    "portugal": "PT",
    "spain": "ES",
    "espanha": "ES",
    "españa": "ES",
    "germany": "DE",
    "alemanha": "DE",
    "france": "FR",
    "frança": "FR",
    "italy": "IT",
    "itália": "IT",
    "united kingdom": "GB",
    "uk": "GB",
    "reino unido": "GB",
    "ireland": "IE",
    "irlanda": "IE",
    "netherlands": "NL",
    "holanda": "NL",
    "poland": "PL",
    "polônia": "PL",
    "india": "IN",
    "índia": "IN",
}

_REGION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("LATAM", re.compile(r"\blatam\b", re.IGNORECASE)),
    ("AMERICAS", re.compile(r"\bamericas\b", re.IGNORECASE)),
    ("EMEA", re.compile(r"\bemea\b", re.IGNORECASE)),
    ("ANYWHERE", re.compile(r"\banywhere\b", re.IGNORECASE)),
    ("WORLDWIDE", re.compile(r"\bworldwide\b|\bglobal\b", re.IGNORECASE)),
)

#: "Remote — Brazil", "Remote - Brazil", "Remote: Brazil", "Remoto (Brasil)".
_REMOTE_COUNTRY_PATTERN = re.compile(
    r"remote\s*[—\-–:]\s*([a-zà-ÿ .]+?)\s*$"
    r"|remoto\s*\(([a-zà-ÿ .]+?)\)",
    re.IGNORECASE,
)


def resolve_allowed_countries(location_text: str | None) -> tuple[str, ...]:
    """Resolve a raw location text to ISO country codes via the `regions-v1` table.

    Returns an empty tuple when nothing recognizable is found — unknown, never an
    implicit "no country allowed". A single-country "ANY" tuple means the text names a
    region with no fixed member list (Anywhere/Worldwide/Global).
    """
    text = (location_text or "").strip()
    if not text:
        return ()

    remote_match = _REMOTE_COUNTRY_PATTERN.search(text)
    if remote_match:
        country_name = (remote_match.group(1) or remote_match.group(2) or "").strip()
        code = _COUNTRY_NAME_TO_CODE.get(country_name.casefold().rstrip("."))
        if code:
            return (code,)

    for region, pattern in _REGION_PATTERNS:
        if pattern.search(text):
            return REGIONS[region]

    code = _COUNTRY_NAME_TO_CODE.get(text.casefold())
    if code:
        return (code,)

    return ()


REGIONS_VERSION_V2 = "allowed-countries-v2"

_PLACE_NAMES = sorted(
    [*_COUNTRY_NAME_TO_CODE, "latam", "americas", "emea", "worldwide", "anywhere"],
    key=len,
    reverse=True,
)
_PLACE = "|".join(re.escape(name) for name in _PLACE_NAMES)
_THE = r"(?:the\s+)?"

#: Permission phrases in a description ("must be located in Brazil", "remoto no Brasil").
#: Deliberately phrase-anchored: a bare country name in a description is an office or a
#: customer market, never a permission.
_DESCRIPTION_COUNTRY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(expression)
    for expression in (
        rf"\b(?:remote|remotely)\s+(?:within|from|in|across)\s+{_THE}({_PLACE})\b",
        rf"\bmust\s+(?:be\s+)?(?:located|based|living|residing|reside)\s+in\s+{_THE}({_PLACE})\b",
        rf"\b(?:authorized|eligible|legally entitled)\s+to\s+work\s+in\s+{_THE}({_PLACE})\b",
        rf"\bopen\s+to\s+(?:candidates|applicants)\s+(?:located\s+|based\s+)?in\s+{_THE}({_PLACE})\b",
        rf"\b(?:remoto|remota|home\s*office|trabalho\s+remoto)\s+(?:em|no|na|para|dentro\s+d[oa])\s+({_PLACE})\b",
        rf"\bresidentes?\s+(?:no|na|em)\s+({_PLACE})\b",
        rf"\b(?:apenas|somente)\s+(?:para\s+)?(?:candidatos\s+)?(?:residentes\s+)?(?:no|na|em)\s+({_PLACE})\b",
    )
)


def _place_codes(place: str) -> tuple[str, ...]:
    region = place.upper()
    if region in REGIONS:
        return REGIONS[region]
    code = _COUNTRY_NAME_TO_CODE.get(place)
    return (code,) if code else ()


def resolve_allowed_countries_v2(
    location_text: str | None, description: str | None
) -> tuple[tuple[str, ...], dict[str, str] | None]:
    """`allowed-countries-v2`: location (v1 table) first, then description phrases.

    Returns `(countries, evidence)`. `()` stays "unknown". Two description phrases that
    resolve to different country sets are ambiguous and yield `()`.
    """
    from_location = resolve_allowed_countries(location_text)
    if from_location:
        return from_location, {"source": "location", "evidence": (location_text or "").strip()}
    text = re.sub(r"\s+", " ", (description or "").casefold()).strip()
    if not text:
        return (), None
    found: dict[tuple[str, ...], str] = {}
    for pattern in _DESCRIPTION_COUNTRY_PATTERNS:
        for match in pattern.finditer(text):
            codes = _place_codes(match.group(1))
            if codes:
                start, end = max(0, match.start() - 40), min(len(text), match.end() + 40)
                found.setdefault(codes, text[start:end].strip())
    if len(found) != 1:
        return (), None
    codes, snippet = next(iter(found.items()))
    return codes, {"source": "description", "evidence": snippet}
