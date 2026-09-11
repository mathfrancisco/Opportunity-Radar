"""HTTP contract for the Profile bounded context."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    Experience,
    ImmutableProfileVersionError,
    ProfileConflictError,
    ProfileError,
    ProfileNotFoundError,
    ProfileSnapshot,
    ProfileVersion,
    Project,
    Skill,
)
from opportunity_radar.profile.service import ProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


class SkillBody(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=128)
    level: str | None = Field(default=None, max_length=32)
    last_used_at: date | None = None
    experience_months: int | None = Field(default=None, ge=0)


class ExperienceBody(BaseModel):
    company_name: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=256)
    started_on: date
    ended_on: date | None = None
    summary: str | None = None


class ProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    started_on: date | None = None
    ended_on: date | None = None
    description: str | None = None
    url: str | None = Field(default=None, max_length=2048)


class PreferenceBody(BaseModel):
    work_modes: list[str] = Field(default_factory=list)
    contracts: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    timezone_start_hour: int | None = Field(default=None, ge=0, le=23)
    timezone_end_hour: int | None = Field(default=None, ge=0, le=23)
    compensation_min: Decimal | None = Field(default=None, ge=0)
    compensation_max: Decimal | None = Field(default=None, ge=0)
    compensation_currency: str | None = Field(default=None, min_length=3, max_length=3)
    relocation_allowed: bool = False
    sponsorship_required: bool = False


class CreateVersionBody(BaseModel):
    expected_profile_version: int = Field(ge=0)
    skills: list[SkillBody] = Field(default_factory=list)
    experiences: list[ExperienceBody] = Field(default_factory=list)
    projects: list[ProjectBody] = Field(default_factory=list)
    preferences: PreferenceBody = Field(default_factory=PreferenceBody)


class VersionOperationBody(BaseModel):
    expected_profile_version: int = Field(ge=0)


class ProfileVersionResponse(BaseModel):
    id: UUID
    number: int
    status: str
    profile_lock_version: int
    skills: list[SkillBody]
    experiences: list[ExperienceBody]
    projects: list[ProjectBody]
    preferences: PreferenceBody


@router.get("", response_model=ProfileVersionResponse)
def get_profile(session: Session = Depends(get_session)) -> ProfileVersionResponse:
    return _execute(lambda: ProfileService(session).get_active())


@router.get("/versions", response_model=list[ProfileVersionResponse])
def list_profile_versions(session: Session = Depends(get_session)) -> list[ProfileVersionResponse]:
    try:
        return [_serialize(version) for version in ProfileService(session).list_versions()]
    except ProfileError as error:
        _raise_http(error)


@router.post(
    "/versions",
    response_model=ProfileVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_version(
    body: CreateVersionBody, session: Session = Depends(get_session)
) -> ProfileVersionResponse:
    snapshot = ProfileSnapshot(
        skills=tuple(Skill(**skill.model_dump()) for skill in body.skills),
        experiences=tuple(Experience(**experience.model_dump()) for experience in body.experiences),
        projects=tuple(Project(**project.model_dump()) for project in body.projects),
        preferences=EmploymentPreference(**body.preferences.model_dump()),
    )
    return _execute(
        lambda: ProfileService(session).create_version(snapshot, body.expected_profile_version)
    )


@router.post("/versions/{version_id}/publish", response_model=ProfileVersionResponse)
def publish_profile_version(
    version_id: UUID, body: VersionOperationBody, session: Session = Depends(get_session)
) -> ProfileVersionResponse:
    return _execute(
        lambda: ProfileService(session).publish(version_id, body.expected_profile_version)
    )


@router.post("/versions/{version_id}/activate", response_model=ProfileVersionResponse)
def activate_profile_version(
    version_id: UUID, body: VersionOperationBody, session: Session = Depends(get_session)
) -> ProfileVersionResponse:
    return _execute(
        lambda: ProfileService(session).activate(version_id, body.expected_profile_version)
    )


def _execute(operation: Callable[[], ProfileVersion]) -> ProfileVersionResponse:
    try:
        return _serialize(operation())
    except ProfileError as error:
        _raise_http(error)


def _raise_http(error: ProfileError) -> NoReturn:
    if isinstance(error, ProfileNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, (ProfileConflictError, ImmutableProfileVersionError)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error


def _serialize(version: ProfileVersion) -> ProfileVersionResponse:
    return ProfileVersionResponse(
        id=version.id,
        number=version.number,
        status=version.status.value,
        profile_lock_version=version.profile_lock_version,
        skills=[SkillBody(**asdict(skill)) for skill in version.snapshot.skills],
        experiences=[
            ExperienceBody(**asdict(experience))
            for experience in version.snapshot.experiences
        ],
        projects=[ProjectBody(**asdict(project)) for project in version.snapshot.projects],
        preferences=PreferenceBody(**asdict(version.snapshot.preferences)),
    )
