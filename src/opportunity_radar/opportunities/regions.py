"""Versioned region-to-country resolution for `location_text` (card F17-06, `regions-v1`).

Office location is never allowed country. This module only resolves the *permission*
signals a location text carries on its face — "Remote — Brazil", "LATAM", "Anywhere" — to
ISO 3166-1 alpha-2 country codes. It never guesses: text that names neither a known region
nor a known country resolves to an empty tuple, which callers must treat as unknown, not
as "no country allowed".
"""

from __future__ import annotations

import re

#: v1 -> v2 (R55-D1): a structured location that ends in a country resolves to it
#: ("Remote, United Kingdom", "Toronto, Canada", "Remote - US"); v1 read only "Remote -
#: <country>" and a bare country name. Only locations that were unknown change.
REGIONS_VERSION = "regions-v2"

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
    "australia": "AU",
    "new zealand": "NZ",
    "japan": "JP",
    "singapore": "SG",
    "switzerland": "CH",
    "sweden": "SE",
    "norway": "NO",
    "denmark": "DK",
    "finland": "FI",
    "austria": "AT",
    "belgium": "BE",
    "czech republic": "CZ",
    "czechia": "CZ",
    "romania": "RO",
    "greece": "GR",
    "hungary": "HU",
    "israel": "IL",
    "turkey": "TR",
    "south africa": "ZA",
    "nigeria": "NG",
    "kenya": "KE",
    "egypt": "EG",
    "morocco": "MA",
    "united arab emirates": "AE",
    "philippines": "PH",
    "china": "CN",
    "hong kong": "HK",
    "south korea": "KR",
    "indonesia": "ID",
    "vietnam": "VN",
    "ukraine": "UA",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
}

#: Short forms read only as the country segment of a structured location ("Remote, US"):
#: in running text "us" is a pronoun.
_COUNTRY_SHORT_FORMS: dict[str, str] = {
    "us": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "uk": "GB",
    "u.k.": "GB",
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


#: Words of a location segment that state the work mode, not the place.
_MODE_SEGMENT = re.compile(
    r"^(?:fully\s+|100%\s+)?(?:remote(?:ly)?|remoto|remota|hybrid|h[íi]brido|on[- ]?site|presencial"
    r"|home\s*office|work from home|wfh)(?:\s+(?:only|first|-\s*first))?$",
    re.IGNORECASE,
)
_MODE_PARENTHETICAL = re.compile(
    r"\(\s*(?:fully\s+)?(?:remote|remoto|hybrid|h[íi]brido|on[- ]?site|presencial)[^)]*\)",
    re.IGNORECASE,
)
_LOCATION_PARTS = re.compile(r"\s*(?:[;|]|\n|\s/\s)\s*")
_LOCATION_SEGMENTS = re.compile(r"\s*(?:,|\s[-–—]\s|:|[()])\s*")


def _country_of_segment(segment: str) -> str | None:
    key = segment.casefold().strip()
    return _COUNTRY_SHORT_FORMS.get(key) or _COUNTRY_NAME_TO_CODE.get(key.rstrip("."))


def _structured_countries(text: str) -> tuple[str, ...]:
    """Countries named by the last place segment of each part of a structured location.

    "Remote, United Kingdom" -> GB; "Toronto, Canada" -> CA; "London, UK; Berlin, Germany"
    -> GB, DE. Work-mode segments ("Remote", "(Hybrid)") are ignored. A part whose last
    place segment is not a known country ("San Francisco, CA", "Remote") makes the whole
    text unknown: it is never guessed from the parts that did resolve.
    """
    found: list[str] = []
    for part in _LOCATION_PARTS.split(text):
        segments = [
            segment
            for segment in _LOCATION_SEGMENTS.split(_MODE_PARENTHETICAL.sub(" ", part))
            if segment and not _MODE_SEGMENT.match(segment)
        ]
        code = _country_of_segment(segments[-1]) if segments else None
        if code is None:
            return ()
        if code not in found:
            found.append(code)
    return tuple(found)


def resolve_allowed_countries(location_text: str | None) -> tuple[str, ...]:
    """Resolve a raw location text to ISO country codes via the `regions-v2` table.

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

    return _structured_countries(text)


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
