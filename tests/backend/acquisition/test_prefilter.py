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


def test_classifier_marks_a_title_decision_made_with_no_department_at_all() -> None:
    from opportunity_radar.opportunities.role_family import classify_role_family

    with_department = classify_role_family(title="Account Executive", departments=("Wizards",))
    without = classify_role_family(title="Account Executive", departments=())

    assert with_department.evidence["rule"] == "title"
    assert "departments" not in with_department.evidence
    assert without.evidence["departments"] == "none"
    assert all(isinstance(value, str) for value in without.evidence.values())


@pytest.mark.parametrize(
    ("title", "departments"),
    [
        ("Account Executive", ()),
        ("Account Executive", ("Wizards",)),
        ("Account Executive", ("Engineering",)),
        ("Backend Engineer", ("Engineering",)),
        ("Wizard of Light", ()),
    ],
)
def test_classifier_evidence_serializes_through_the_http_schema(
    title: str, departments: tuple[str, ...]
) -> None:
    from pydantic import TypeAdapter

    from opportunity_radar.opportunities.role_family import classify_role_family
    from opportunity_radar.presentation.http.opportunities import OpportunityResponse

    evidence = classify_role_family(title=title, departments=departments).evidence
    annotation = OpportunityResponse.model_fields["role_family_evidence"].annotation

    assert TypeAdapter(annotation).validate_python(evidence) == evidence
