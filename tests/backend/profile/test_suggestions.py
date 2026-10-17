"""R55-D4: repeated "not for me" marks become profile suggestions, and only suggestions."""

from __future__ import annotations

import pytest

from opportunity_radar.profile.domain import EmploymentPreference
from opportunity_radar.profile.suggestions import (
    MIN_MARKS,
    MarkedPosting,
    SuggestionKind,
    build_suggestions,
)


def _posting(reason: str, **changes: object) -> MarkedPosting:
    values: dict[str, object] = {
        "reason": reason,
        "role_family": None,
        "seniority": None,
        "allowed_countries": (),
        "company_name": None,
    }
    values.update(changes)
    return MarkedPosting(**values)  # type: ignore[arg-type]


_PREFERENCES = EmploymentPreference(
    countries=("BR", "PT"),
    target_role_families=("SOFTWARE_ENGINEERING", "DATA"),
    accepted_seniorities=("JUNIOR", "MID", "UNKNOWN"),
)


def test_one_mark_is_a_judgement_two_are_a_pattern() -> None:
    one = [_posting("AREA", role_family="DATA")]
    two = one * MIN_MARKS

    assert build_suggestions(_PREFERENCES, one) == []
    [suggestion] = build_suggestions(_PREFERENCES, two)
    assert (suggestion.kind, suggestion.value, suggestion.marks) == (
        SuggestionKind.REMOVE_ROLE_FAMILY,
        "DATA",
        2,
    )


@pytest.mark.parametrize(
    ("posting", "kind", "value"),
    [
        (_posting("AREA", role_family="DATA"), SuggestionKind.REMOVE_ROLE_FAMILY, "DATA"),
        (_posting("SENIORITY", seniority="MID"), SuggestionKind.REMOVE_SENIORITY, "MID"),
        (
            _posting("LOCATION", allowed_countries=("PT", "ES")),
            SuggestionKind.REMOVE_COUNTRY,
            "PT",
        ),
        (
            _posting("COMPANY", company_name="Acme Corp"),
            SuggestionKind.LOWER_COMPANY_PRIORITY,
            "Acme Corp",
        ),
    ],
)
def test_each_reason_points_at_its_own_preference(
    posting: MarkedPosting, kind: SuggestionKind, value: str
) -> None:
    [suggestion] = build_suggestions(_PREFERENCES, [posting, posting])

    assert (suggestion.kind, suggestion.value) == (kind, value)


@pytest.mark.parametrize(
    "posting",
    [
        # an area the profile does not target is already out
        _posting("AREA", role_family="SALES"),
        _posting("AREA", role_family="UNKNOWN"),
        _posting("AREA", role_family=None),
        # a level the profile does not accept is already ranked down
        _posting("SENIORITY", seniority="SENIOR"),
        _posting("SENIORITY", seniority="UNKNOWN"),
        _posting("LOCATION", allowed_countries=("US",)),
        _posting("LOCATION", allowed_countries=("ANY",)),
        _posting("COMPANY", company_name="  "),
        _posting("OTHER", role_family="DATA", seniority="MID"),
        _posting("COMPENSATION", role_family="DATA", seniority="MID"),
    ],
)
def test_nothing_is_suggested_for_what_the_profile_does_not_state(posting: MarkedPosting) -> None:
    assert build_suggestions(_PREFERENCES, [posting] * 3) == []


def test_company_names_group_ignoring_case_and_the_first_spelling_wins() -> None:
    postings = [
        _posting("COMPANY", company_name="Acme Corp"),
        _posting("COMPANY", company_name="ACME CORP"),
    ]

    [suggestion] = build_suggestions(_PREFERENCES, postings)

    assert (suggestion.value, suggestion.marks) == ("Acme Corp", 2)


def test_suggestions_are_ordered_by_evidence() -> None:
    postings = [_posting("AREA", role_family="DATA")] * 2 + [
        _posting("SENIORITY", seniority="MID")
    ] * 3

    found = build_suggestions(_PREFERENCES, postings)

    assert [(item.kind, item.marks) for item in found] == [
        (SuggestionKind.REMOVE_SENIORITY, 3),
        (SuggestionKind.REMOVE_ROLE_FAMILY, 2),
    ]


def test_an_empty_area_list_means_all_areas_and_has_nothing_to_remove() -> None:
    open_profile = EmploymentPreference(target_role_families=())

    assert build_suggestions(open_profile, [_posting("AREA", role_family="DATA")] * 3) == []
