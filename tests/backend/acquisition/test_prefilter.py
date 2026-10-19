"""R55-B5: the country half of the ingestion prefilter never guesses."""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.prefilter import (
    active_profile_target_countries,
    area_off_target,
    location_outside_countries,
)


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


def test_region_containing_the_target_country_is_kept() -> None:
    assert location_outside_countries("EMEA", ("PT",)) is False
    assert location_outside_countries("Europe", ("PT",)) is False


def test_area_off_target_needs_title_and_department_to_agree() -> None:
    sales = ("SOFTWARE_ENGINEERING", "DATA")
    assert area_off_target("Account Executive", (), sales) is True
    assert area_off_target("Account Executive", ("Sales",), sales) is True
    # Department puts a sales title in an on-target area, or is unknown: keep.
    assert area_off_target("Account Executive", ("Engineering",), sales) is False
    assert area_off_target("Account Executive", ("Wizards",), sales) is False
    # Unknown title: keep.
    assert area_off_target("Wizard of Light", ("Sales",), sales) is False
    # A PRODUCT profile keeps a Technical Product Manager filed under Engineering.
    assert area_off_target("Technical Product Manager", ("Engineering",), ("PRODUCT",)) is False
    assert area_off_target("Anything", ("Sales",), ()) is False


def test_profile_countries_reader_swallows_any_exception() -> None:
    class Broken:
        def scalars(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("database gone")

        def execute(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("database gone")

    assert active_profile_target_countries(Broken(), "owner")() == ()  # type: ignore[arg-type]
