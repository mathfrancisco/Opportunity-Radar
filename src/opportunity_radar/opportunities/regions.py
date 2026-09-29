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
