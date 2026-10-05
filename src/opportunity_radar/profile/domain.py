"""Framework-independent Profile rules and value types."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class ProfileVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ProfileError(Exception):
    """Base error for an invalid profile operation."""


class ProfileNotFoundError(ProfileError):
    pass


class ProfileConflictError(ProfileError):
    pass


class ImmutableProfileVersionError(ProfileError):
    pass


class InvalidProfileSnapshotError(ProfileError):
    pass


@dataclass(frozen=True)
class Skill:
    canonical_name: str
    level: str | None = None
    last_used_at: date | None = None
    experience_months: int | None = None


@dataclass(frozen=True)
class Experience:
    company_name: str
    title: str
    started_on: date
    ended_on: date | None = None
    summary: str | None = None


@dataclass(frozen=True)
class Project:
    name: str
    started_on: date | None = None
    ended_on: date | None = None
    description: str | None = None
    url: str | None = None


#: Levels a profile accepts when it never said anything (F48-13, decision 2). SENIOR and above
#: are not listed on purpose: they rank lower, they are never excluded.
DEFAULT_ACCEPTED_SENIORITIES: tuple[str, ...] = ("INTERN", "JUNIOR", "MID", "UNKNOWN")
VALID_SENIORITIES: frozenset[str] = frozenset(
    {"INTERN", "JUNIOR", "MID", "SENIOR", "STAFF", "LEAD", "MANAGER", "DIRECTOR", "UNKNOWN"}
)


@dataclass(frozen=True)
class EmploymentPreference:
    work_modes: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    timezone_start_hour: int | None = None
    timezone_end_hour: int | None = None
    compensation_min: Decimal | None = None
    compensation_max: Decimal | None = None
    compensation_currency: str | None = None
    compensation_period: str | None = None
    relocation_allowed: bool = False
    sponsorship_required: bool = False
    #: `role-family-v1` areas the Inbox shows by default (card F17-02). Empty means every
    #: area, which is what a profile meant before the preference existed.
    target_role_families: tuple[str, ...] = ()
    target_titles: tuple[str, ...] = ()
    #: `Seniority` values the profile prefers. Empty means "not stated": no level is ranked
    #: down or hidden (F20-72).
    accepted_seniorities: tuple[str, ...] = DEFAULT_ACCEPTED_SENIORITIES


@dataclass(frozen=True)
class ProfileSnapshot:
    skills: tuple[Skill, ...]
    experiences: tuple[Experience, ...]
    projects: tuple[Project, ...]
    preferences: EmploymentPreference

    def validate(self) -> None:
        names = [skill.canonical_name.strip().casefold() for skill in self.skills]
        if not all(names) or len(names) != len(set(names)):
            raise InvalidProfileSnapshotError("skills must have unique canonical names")
        if any(
            skill.experience_months is not None and skill.experience_months < 0
            for skill in self.skills
        ):
            raise InvalidProfileSnapshotError("skill experience months must not be negative")
        for experience in self.experiences:
            if experience.ended_on and experience.ended_on < experience.started_on:
                raise InvalidProfileSnapshotError("experience end date must not precede start date")
        for project in self.projects:
            if project.started_on and project.ended_on and project.ended_on < project.started_on:
                raise InvalidProfileSnapshotError("project end date must not precede start date")
        preferences = self.preferences
        if (
            preferences.compensation_min is not None
            and preferences.compensation_max is not None
            and preferences.compensation_min > preferences.compensation_max
        ):
            raise InvalidProfileSnapshotError("compensation minimum must not exceed maximum")
        if preferences.compensation_period not in {
            None,
            "YEAR",
            "MONTH",
            "WEEK",
            "DAY",
            "HOUR",
        }:
            raise InvalidProfileSnapshotError("compensation period must be normalized")
        if (preferences.timezone_start_hour is None) != (preferences.timezone_end_hour is None):
            raise InvalidProfileSnapshotError(
                "timezone window must include both start and end hours"
            )
        start_hour = preferences.timezone_start_hour
        end_hour = preferences.timezone_end_hour
        if start_hour is not None and end_hour is not None and not (
            0 <= start_hour <= 23 and 0 <= end_hour <= 23 and start_hour < end_hour
        ):
            raise InvalidProfileSnapshotError("timezone window must be valid")
        if len(set(preferences.target_role_families)) != len(preferences.target_role_families):
            raise InvalidProfileSnapshotError("target role families must be unique")
        if len(set(preferences.target_titles)) != len(preferences.target_titles):
            raise InvalidProfileSnapshotError("target titles must be unique")
        seniorities = preferences.accepted_seniorities
        if len(set(seniorities)) != len(seniorities):
            raise InvalidProfileSnapshotError("accepted seniorities must be unique")
        if not set(seniorities) <= VALID_SENIORITIES:
            raise InvalidProfileSnapshotError("accepted seniorities must be known levels")


@dataclass(frozen=True)
class ProfileVersion:
    id: UUID
    number: int
    status: ProfileVersionStatus
    profile_lock_version: int
    snapshot: ProfileSnapshot
