from datetime import date

import pytest

from opportunity_radar.profile.domain import (
    EmploymentPreference,
    Experience,
    InvalidProfileSnapshotError,
    ProfileSnapshot,
    Skill,
)


def test_snapshot_rejects_duplicate_skills_case_insensitively() -> None:
    snapshot = ProfileSnapshot(
        skills=(Skill("Python"), Skill(" python ")),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(),
    )

    with pytest.raises(InvalidProfileSnapshotError, match="unique canonical names"):
        snapshot.validate()


def test_snapshot_rejects_invalid_experience_period() -> None:
    snapshot = ProfileSnapshot(
        skills=(),
        experiences=(Experience("Acme", "Engineer", date(2024, 2, 1), date(2024, 1, 1)),),
        projects=(),
        preferences=EmploymentPreference(),
    )

    with pytest.raises(InvalidProfileSnapshotError, match="experience end date"):
        snapshot.validate()
