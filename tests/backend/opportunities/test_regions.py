"""Unit coverage for the `regions` table (card F17-06)."""

from __future__ import annotations

import pytest

from opportunity_radar.opportunities.regions import (
    ANY_COUNTRY,
    REGIONS_VERSION,
    resolve_allowed_countries,
    resolve_allowed_countries_v2,
)


def test_regions_version_is_pinned() -> None:
    assert REGIONS_VERSION == "regions-v2"


@pytest.mark.parametrize(
    ("location_text", "expected"),
    [
        ("Remote — Brazil", ("BR",)),
        ("Remote - Brazil", ("BR",)),
        ("Remote: Brazil", ("BR",)),
        ("Remoto (Brasil)", ("BR",)),
        ("Brazil", ("BR",)),
        ("Brasil", ("BR",)),
    ],
)
def test_resolves_remote_country_patterns_to_iso_codes(
    location_text: str, expected: tuple[str, ...]
) -> None:
    assert resolve_allowed_countries(location_text) == expected


@pytest.mark.parametrize(
    ("location_text", "expected_member"),
    [
        ("LATAM", "BR"),
        ("Remote, LATAM only", "MX"),
        ("Americas", "US"),
        ("EMEA", "PT"),
    ],
)
def test_resolves_regions_to_their_member_countries(
    location_text: str, expected_member: str
) -> None:
    result = resolve_allowed_countries(location_text)
    assert expected_member in result
    assert ANY_COUNTRY not in result


@pytest.mark.parametrize("location_text", ["Anywhere", "Worldwide", "Global"])
def test_resolves_global_regions_to_the_any_sentinel(location_text: str) -> None:
    assert resolve_allowed_countries(location_text) == (ANY_COUNTRY,)


@pytest.mark.parametrize(
    "location_text", [None, "", "   ", "São Paulo, SP", "Nowhere in particular"]
)
def test_returns_empty_for_unrecognizable_text(location_text: str | None) -> None:
    """Office location (a city) is never allowed country: no region/country pattern
    matches, so the result is unknown (`()`), never a guess."""
    assert resolve_allowed_countries(location_text) == ()


# R55-D1: a structured location that ends in a country resolves to it (`regions-v2`).
@pytest.mark.parametrize(
    ("location_text", "expected"),
    [
        ("Remote, United Kingdom", ("GB",)),
        ("Remote - US", ("US",)),
        ("Remote, US", ("US",)),
        ("Remote (Canada)", ("CA",)),
        ("Toronto, Canada", ("CA",)),
        ("London, UK (Remote)", ("GB",)),
        ("New York, NY, United States", ("US",)),
        ("Brazil - Remote", ("BR",)),
        ("São Paulo, Brazil", ("BR",)),
        ("London, UK; Berlin, Germany", ("GB", "DE")),
        ("Sydney, Australia", ("AU",)),
    ],
)
def test_structured_location_resolves_to_its_country(
    location_text: str, expected: tuple[str, ...]
) -> None:
    assert resolve_allowed_countries(location_text) == expected


@pytest.mark.parametrize(
    "location_text",
    [
        "Remote",
        "Remote, Hybrid",
        "San Francisco, CA",  # CA is California here, never guessed as Canada
        "Join us",
        "London, UK; Remote",  # one part is unknown: the whole stays unknown
        "Remote, Europe",
        "Berlin",
    ],
)
def test_structured_location_without_a_known_country_stays_unknown(location_text: str) -> None:
    assert resolve_allowed_countries(location_text) == ()


def test_latam_worldwide_and_brazil_keep_their_resolution() -> None:
    assert "BR" in resolve_allowed_countries("LATAM")
    assert resolve_allowed_countries("Worldwide") == (ANY_COUNTRY,)
    assert resolve_allowed_countries("Brazil") == ("BR",)


@pytest.mark.parametrize(
    ("location_text", "expected"),
    [
        ("Remote, Brazil, Argentina", ("BR", "AR")),
        ("Remote, Canada, US", ("CA", "US")),
        ("Remote - US, Canada", ("US", "CA")),
        ("Berlin, Germany, Brazil", ("DE", "BR")),
        ("Toronto, Canada", ("CA",)),
        ("Remote, Brazil, Argentina; London, UK", ("BR", "AR", "GB")),
    ],
)
def test_every_trailing_country_counts(location_text: str, expected: tuple[str, ...]) -> None:
    assert resolve_allowed_countries(location_text) == expected


def test_allowed_countries_v4_uses_explicit_description_before_structured_location() -> None:
    countries, evidence = resolve_allowed_countries_v2(
        "Remote, United Kingdom",
        "Applicants must be located in Brazil.",
    )

    assert countries == ("BR",)
    assert evidence is not None
    assert evidence["source"] == "description"


def test_allowed_countries_v4_keeps_office_location_out_of_eligibility() -> None:
    countries, evidence = resolve_allowed_countries_v2(
        "London, United Kingdom",
        "Our office is in London.",
    )

    assert countries == ()
    assert evidence is None


@pytest.mark.parametrize(
    "location",
    (
        "Remote, United Kingdom",
        "United Kingdom - Remote",
        "United Kingdom (Remote)",
        "Brasil - Remoto",
    ),
)
def test_allowed_countries_v4_keeps_explicit_remote_location_despite_office_perks(
    location: str,
) -> None:
    countries, evidence = resolve_allowed_countries_v2(
        location,
        "Our London office offers lunch vouchers.",
    )

    expected = ("BR",) if location == "Brasil - Remoto" else ("GB",)
    assert countries == expected
    assert evidence == {"source": "location", "evidence": location}


def test_allowed_countries_v4_alias_is_limited_to_content_resolution() -> None:
    assert resolve_allowed_countries("Remote, UnitedKingdom") == ()

    countries, evidence = resolve_allowed_countries_v2("Remote, UnitedKingdom", None)

    assert countries == ("GB",)
    assert evidence == {"source": "location", "evidence": "Remote, UnitedKingdom"}


def test_allowed_countries_v4_conflict_remains_unknown_without_location_fallback() -> None:
    countries, evidence = resolve_allowed_countries_v2(
        "Remote, United Kingdom",
        "Remote within Brazil; applicants must be located in Portugal.",
    )

    assert countries == ()
    assert evidence is not None
    assert evidence["source"] == "conflict"
    assert "brazil" in evidence["evidence"]
    assert "portugal" in evidence["evidence"]
