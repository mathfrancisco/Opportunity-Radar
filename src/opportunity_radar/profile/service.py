"""Application service for immutable, versioned career profiles."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.profile.domain import (
    EmploymentPreference,
    Experience,
    ImmutableProfileVersionError,
    ProfileConflictError,
    ProfileNotFoundError,
    ProfileSnapshot,
    ProfileVersion,
    ProfileVersionStatus,
    Project,
    Skill,
)
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ExperienceModel,
    ProfileSkillModel,
    ProfileVersionModel,
    ProjectModel,
    SkillModel,
)
from opportunity_radar.profile.repository import SqlAlchemyProfileRepository

# The lock is the profile's version counter: a mismatch always means another write won.
_CONFLICT = "career profile was changed by another edit; nothing was saved"


class ProfileService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SqlAlchemyProfileRepository(session)

    def get_active(self) -> ProfileVersion:
        version = self.repository.active_version()
        if version is None:
            raise ProfileNotFoundError("no active profile version")
        return self._to_domain(version)

    def get_version(self, version_id: UUID) -> ProfileVersion:
        version = self.repository.version(version_id)
        if version is None:
            raise ProfileNotFoundError("profile version not found")
        return self._to_domain(version)

    def list_versions(self) -> list[ProfileVersion]:
        return [self._to_domain(version) for version in self.repository.versions()]

    def create_version(
        self,
        snapshot: ProfileSnapshot,
        expected_profile_version: int,
    ) -> ProfileVersion:
        """Record `snapshot` as a draft; publishing and activating it are separate writes."""
        return self._commit(lambda: self._create_draft(snapshot, expected_profile_version))

    def create_active_version(
        self,
        snapshot: ProfileSnapshot,
        expected_profile_version: int,
    ) -> ProfileVersion:
        """Create, publish and activate `snapshot` as a single write (card F18-07).

        Done as three requests, a failure between them left a draft or a published version
        behind. Here the expected version is consumed once and nothing is committed until
        the new version is active: a conflict or any error rolls the whole write back, and
        the previous active version stays active.
        """

        def write() -> ProfileVersionModel:
            version = self._create_draft(snapshot, expected_profile_version)
            self._mark_published(version)
            self._mark_active(version)
            return version

        return self._commit(write)

    def publish(self, version_id: UUID, expected_profile_version: int) -> ProfileVersion:
        def write() -> ProfileVersionModel:
            version = self._version_for_update(version_id)
            if version.status != ProfileVersionStatus.DRAFT.value:
                raise ImmutableProfileVersionError("only draft profile versions can be published")
            self._advance_profile(self._career_profile(), expected_profile_version)
            self._mark_published(version)
            return version

        return self._commit(write)

    def activate(self, version_id: UUID, expected_profile_version: int) -> ProfileVersion:
        def write() -> ProfileVersionModel:
            version = self._version_for_update(version_id)
            if version.status != ProfileVersionStatus.PUBLISHED.value:
                raise ImmutableProfileVersionError(
                    "only published profile versions can be activated"
                )
            self._advance_profile(self._career_profile(), expected_profile_version)
            self._mark_active(version)
            return version

        return self._commit(write)

    def _commit(self, write: Callable[[], ProfileVersionModel]) -> ProfileVersion:
        """Commit one write whole, or roll all of it back.

        A failed write must not leave an advanced lock or a half-built version in the
        session, where a later commit by the same caller would persist it.
        """
        try:
            version_id = write().id
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.get_version(version_id)

    def _create_draft(
        self, snapshot: ProfileSnapshot, expected_profile_version: int
    ) -> ProfileVersionModel:
        snapshot.validate()
        profile = self._claim_profile(expected_profile_version)
        next_number = (
            self.session.scalar(
                select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                    ProfileVersionModel.career_profile_id == profile.id
                )
            )
            or 0
        ) + 1
        version = ProfileVersionModel(
            career_profile_id=profile.id,
            number=next_number,
            status=ProfileVersionStatus.DRAFT.value,
        )
        self._apply_snapshot(version, snapshot)
        self.session.add(version)
        self.session.flush()
        return version

    def _claim_profile(self, expected: int) -> CareerProfileModel:
        """Advance the profile lock from `expected`, creating the profile on its first write."""
        profile = self.repository.career_profile_for_update()
        if profile is not None:
            self._advance_profile(profile, expected)
            return profile
        if expected != 0:
            raise ProfileConflictError(_CONFLICT)
        profile = CareerProfileModel(version=1)
        self.session.add(profile)
        try:
            self.session.flush()
        except IntegrityError as error:
            # Another first write created the singleton profile in the meantime.
            raise ProfileConflictError(_CONFLICT) from error
        return profile

    def _career_profile(self) -> CareerProfileModel:
        profile = self.repository.career_profile_for_update()
        assert profile is not None
        return profile

    def _version_for_update(self, version_id: UUID) -> ProfileVersionModel:
        version = self.repository.version_for_update(version_id)
        if version is None:
            raise ProfileNotFoundError("profile version not found")
        return version

    @staticmethod
    def _mark_published(version: ProfileVersionModel) -> None:
        version.status = ProfileVersionStatus.PUBLISHED.value
        version.published_at = datetime.now(UTC)

    def _mark_active(self, version: ProfileVersionModel) -> None:
        active = self.session.scalar(
            select(ProfileVersionModel)
            .where(
                ProfileVersionModel.career_profile_id == version.career_profile_id,
                ProfileVersionModel.status == ProfileVersionStatus.ACTIVE.value,
            )
            .with_for_update()
        )
        if active is not None:
            # One ACTIVE version per profile is a unique index: the previous one is archived
            # before this one takes its place, never deleted, so it stays readable.
            active.status = ProfileVersionStatus.ARCHIVED.value
            self.session.flush()
        version.status = ProfileVersionStatus.ACTIVE.value
        version.activated_at = datetime.now(UTC)

    def _advance_profile(self, profile: CareerProfileModel, expected: int) -> None:
        result = cast(
            CursorResult[Any],
            self.session.execute(
                update(CareerProfileModel)
                .where(CareerProfileModel.id == profile.id, CareerProfileModel.version == expected)
                .values(version=expected + 1)
            ),
        )
        if result.rowcount != 1:
            raise ProfileConflictError(_CONFLICT)

    def _apply_snapshot(self, version: ProfileVersionModel, snapshot: ProfileSnapshot) -> None:
        version.skills = []
        for skill in snapshot.skills:
            canonical_name = skill.canonical_name.strip().casefold()
            skill_model = self.session.scalar(
                select(SkillModel).where(SkillModel.canonical_name == canonical_name)
            )
            if skill_model is None:
                skill_model = SkillModel(
                    canonical_name=canonical_name,
                    display_name=skill.canonical_name.strip(),
                )
            version.skills.append(
                ProfileSkillModel(
                    skill=skill_model,
                    level=skill.level,
                    last_used_at=skill.last_used_at,
                    experience_months=skill.experience_months,
                )
            )
        version.experiences = [
            ExperienceModel(
                company_name=experience.company_name,
                title=experience.title,
                started_on=experience.started_on,
                ended_on=experience.ended_on,
                summary=experience.summary,
            )
            for experience in snapshot.experiences
        ]
        version.projects = [
            ProjectModel(
                name=project.name,
                started_on=project.started_on,
                ended_on=project.ended_on,
                description=project.description,
                url=project.url,
            )
            for project in snapshot.projects
        ]
        preferences = snapshot.preferences
        version.preference = EmploymentPreferenceModel(
            work_modes=list(preferences.work_modes),
            contracts=list(preferences.contracts),
            countries=list(preferences.countries),
            timezone_start_hour=preferences.timezone_start_hour,
            timezone_end_hour=preferences.timezone_end_hour,
            compensation_min=preferences.compensation_min,
            compensation_max=preferences.compensation_max,
            compensation_currency=preferences.compensation_currency,
            compensation_period=preferences.compensation_period,
            relocation_allowed=preferences.relocation_allowed,
            sponsorship_required=preferences.sponsorship_required,
            target_role_families=list(preferences.target_role_families),
        )

    @staticmethod
    def _to_domain(version: ProfileVersionModel) -> ProfileVersion:
        preference = version.preference
        assert preference is not None
        snapshot = ProfileSnapshot(
            skills=tuple(
                Skill(
                    canonical_name=skill.skill.canonical_name,
                    level=skill.level,
                    last_used_at=skill.last_used_at,
                    experience_months=skill.experience_months,
                )
                for skill in version.skills
            ),
            experiences=tuple(
                Experience(
                    company_name=experience.company_name,
                    title=experience.title,
                    started_on=experience.started_on,
                    ended_on=experience.ended_on,
                    summary=experience.summary,
                )
                for experience in version.experiences
            ),
            projects=tuple(
                Project(
                    name=project.name,
                    started_on=project.started_on,
                    ended_on=project.ended_on,
                    description=project.description,
                    url=project.url,
                )
                for project in version.projects
            ),
            preferences=EmploymentPreference(
                work_modes=tuple(preference.work_modes),
                contracts=tuple(preference.contracts),
                countries=tuple(preference.countries),
                timezone_start_hour=preference.timezone_start_hour,
                timezone_end_hour=preference.timezone_end_hour,
                compensation_min=preference.compensation_min,
                compensation_max=preference.compensation_max,
                compensation_currency=preference.compensation_currency,
                compensation_period=preference.compensation_period,
                relocation_allowed=preference.relocation_allowed,
                sponsorship_required=preference.sponsorship_required,
                target_role_families=tuple(preference.target_role_families),
            ),
        )
        return ProfileVersion(
            id=version.id,
            number=version.number,
            status=ProfileVersionStatus(version.status),
            profile_lock_version=version.career_profile.version,
            snapshot=snapshot,
        )
