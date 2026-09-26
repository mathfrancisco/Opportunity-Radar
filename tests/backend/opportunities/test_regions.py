"""Unit coverage for the `regions-v1` table (card F17-06)."""

from __future__ import annotations

import pytest

from opportunity_radar.opportunities.regions import (
    ANY_COUNTRY,
    REGIONS_VERSION,
    resolve_allowed_countries,
)


def test_regions_version_is_pinned() -> None:
    assert REGIONS_VERSION == "regions-v1"


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
