"""F48-13 end to end: a profile without a seniority preference hides no level (F20-72)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from opportunity_radar.matching.domain import (
    EligibilityStatus,
    OpportunitySnapshot,
    default_rule_set,
    evaluate_match,
)
from opportunity_radar.matching.service import _profile_snapshot
from opportunity_radar.opportunities.domain import OpportunityStatus, Seniority, WorkMode
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    ProfileSnapshot,
    ProfileVersion,
    ProfileVersionStatus,
)


def _version(**preferences: object) -> ProfileVersion:
    return ProfileVersion(
        id=uuid4(),
        number=1,
        status=ProfileVersionStatus.ACTIVE,
        profile_lock_version=1,
        snapshot=ProfileSnapshot(
            skills=(),
            experiences=(),
            projects=(),
            preferences=EmploymentPreference(work_modes=("REMOTE",), **preferences),  # type: ignore[arg-type]
        ),
    )


def _evaluate(seniority: Seniority, version: ProfileVersion):
    opportunity = OpportunitySnapshot(
        opportunity_id=uuid4(),
        content_version=1,
        status=OpportunityStatus.ACTIVE,
        work_mode=WorkMode.REMOTE,
        seniority=seniority,
    )
    return evaluate_match(
        opportunity,
        _profile_snapshot(version),
        default_rule_set(),
        assessed_at=datetime(2026, 9, 29, tzinfo=UTC),
    )


@pytest.mark.parametrize("seniority", list(Seniority))
def test_profile_without_seniority_never_makes_a_level_ineligible(seniority: Seniority) -> None:
    result = _evaluate(seniority, _version(accepted_seniorities=()))

    assert result.eligibility.status is not EligibilityStatus.INELIGIBLE


@pytest.mark.parametrize("seniority", [Seniority.INTERN, Seniority.JUNIOR, Seniority.MID])
def test_default_profile_keeps_junior_levels_eligible(seniority: Seniority) -> None:
    result = _evaluate(seniority, _version())

    assert result.eligibility.status is not EligibilityStatus.INELIGIBLE


def test_preference_reaches_the_matching_snapshot_and_senior_ranks_lower() -> None:
    version = _version()
    snapshot = _profile_snapshot(version)
    assert snapshot.accepted_seniorities == (
        Seniority.INTERN,
        Seniority.JUNIOR,
        Seniority.MID,
        Seniority.UNKNOWN,
    )
    junior = _evaluate(Seniority.JUNIOR, version)
    senior = _evaluate(Seniority.SENIOR, version)
    assert senior.eligibility.status is not EligibilityStatus.INELIGIBLE
    assert senior.score < junior.score
