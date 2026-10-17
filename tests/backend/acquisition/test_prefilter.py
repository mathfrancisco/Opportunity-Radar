"""R55-B5: the country half of the ingestion prefilter never guesses."""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.prefilter import location_outside_countries


@pytest.mark.parametrize(
    "location",
    [
        "São Paulo, Brazil",
        "Remote - Brazil",
        "Remoto (Brasil)",
        "LATAM",
        "Americas",
        "Worldwide",
        "Anywhere",
        "London, UK; São Paulo, Brazil",
        "Remote",
        "Hybrid",
        "Springfield",
        "San Francisco, CA",
        "",
        None,
    ],
)
def test_location_kept_for_brazil_profile(location: str | None) -> None:
    assert location_outside_countries(location, ("BR",)) is False


@pytest.mark.parametrize(
    "location",
    [
        "New York, United States",
        "Remote, United Kingdom",
        "Toronto, Canada",
        "EMEA",
        "Remote - US",
    ],
)
def test_location_dropped_only_when_it_names_other_countries(location: str) -> None:
    assert location_outside_countries(location, ("BR",)) is True


def test_no_profile_countries_never_drops() -> None:
    assert location_outside_countries("New York, United States", ()) is False
    assert location_outside_countries("New York, United States", ("",)) is False


def test_profile_country_codes_are_case_insensitive() -> None:
    assert location_outside_countries("Lisbon, Portugal", ("pt",)) is False
    assert location_outside_countries("Lisbon, Portugal", ("br",)) is True
