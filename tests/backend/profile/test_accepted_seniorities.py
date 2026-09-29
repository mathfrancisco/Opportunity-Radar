"""F48-13: seniority preference and target-area seeding on the profile."""

from __future__ import annotations

import pytest

from opportunity_radar.presentation.http.profile import PreferenceBody, _preferences
from opportunity_radar.profile.domain import (
    DEFAULT_ACCEPTED_SENIORITIES,
    EmploymentPreference,
    InvalidProfileSnapshotError,
    ProfileSnapshot,
)
from scripts.seed_profile_target_areas import SEED_ROLE_FAMILIES, seeded_snapshot


def _snapshot(**preferences: object) -> ProfileSnapshot:
    return ProfileSnapshot(
        skills=(),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(**preferences),  # type: ignore[arg-type]
    )


def test_default_preference_accepts_below_senior_and_unknown_only() -> None:
    assert DEFAULT_ACCEPTED_SENIORITIES == ("INTERN", "JUNIOR", "MID", "UNKNOWN")
    assert EmploymentPreference().accepted_seniorities == DEFAULT_ACCEPTED_SENIORITIES
    assert PreferenceBody().accepted_seniorities == list(DEFAULT_ACCEPTED_SENIORITIES)


def test_snapshot_rejects_unknown_or_duplicate_seniorities() -> None:
    with pytest.raises(InvalidProfileSnapshotError, match="known levels"):
        _snapshot(accepted_seniorities=("JUNIOR", "WIZARD")).validate()
    with pytest.raises(InvalidProfileSnapshotError, match="unique"):
        _snapshot(accepted_seniorities=("JUNIOR", "JUNIOR")).validate()
    _snapshot(accepted_seniorities=()).validate()


def test_body_rejects_unknown_level_and_dedupes() -> None:
    with pytest.raises(ValueError, match="unknown seniorities"):
        PreferenceBody(accepted_seniorities=["WIZARD"])
    body = PreferenceBody(accepted_seniorities=["JUNIOR", "JUNIOR", "MID"])
    assert body.accepted_seniorities == ["JUNIOR", "MID"]


def test_omitted_preference_is_copied_from_the_base_and_explicit_empty_wins() -> None:
    base = _snapshot(accepted_seniorities=("SENIOR",))
    kept = _preferences(PreferenceBody.model_validate({"work_modes": ["REMOTE"]}), base)
    assert kept.accepted_seniorities == ("SENIOR",)
    cleared = _preferences(PreferenceBody.model_validate({"accepted_seniorities": []}), base)
    assert cleared.accepted_seniorities == ()


def test_seed_writes_the_technical_proxy_only_when_areas_are_empty() -> None:
    seeded = seeded_snapshot(_snapshot())
    assert seeded is not None
    assert seeded.preferences.target_role_families == SEED_ROLE_FAMILIES
    assert SEED_ROLE_FAMILIES == ("SOFTWARE_ENGINEERING", "DATA", "INFRASTRUCTURE", "SECURITY")


def test_seed_never_overwrites_user_areas_and_invents_nothing() -> None:
    assert seeded_snapshot(_snapshot(target_role_families=("DESIGN",))) is None
    seeded = seeded_snapshot(_snapshot(work_modes=("REMOTE",)))
    assert seeded is not None
    assert seeded.skills == ()
    assert seeded.preferences.target_titles == ()
    assert seeded.preferences.work_modes == ("REMOTE",)
