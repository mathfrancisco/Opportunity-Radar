"""Persistence adapter for Profile aggregates."""

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from opportunity_radar.profile.models import (
    CareerProfileModel,
    ProfileSkillModel,
    ProfileVersionModel,
)


class SqlAlchemyProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def career_profile_for_update(self, owner_sub: str | None = None) -> CareerProfileModel | None:
        statement = select(CareerProfileModel)
        if owner_sub is not None:
            statement = statement.where(CareerProfileModel.owner_sub == owner_sub)
        return self.session.scalar(statement.limit(1).with_for_update())

    def active_version(self, owner_sub: str | None = None) -> ProfileVersionModel | None:
        return (
            self.session.scalars(
                self._versions(owner_sub).where(ProfileVersionModel.status == "ACTIVE")
            )
            .unique()
            .one_or_none()
        )

    def version(self, version_id: UUID, owner_sub: str | None = None) -> ProfileVersionModel | None:
        return (
            self.session.scalars(
                self._versions(owner_sub).where(ProfileVersionModel.id == version_id)
            )
            .unique()
            .one_or_none()
        )

    def versions(self, owner_sub: str | None = None) -> list[ProfileVersionModel]:
        return list(
            self.session.scalars(
                self._versions(owner_sub).order_by(ProfileVersionModel.number.desc())
            ).unique()
        )

    def version_for_update(
        self, version_id: UUID, owner_sub: str | None = None
    ) -> ProfileVersionModel | None:
        statement = select(ProfileVersionModel.id).where(
            ProfileVersionModel.id == version_id
        )
        if owner_sub is not None:
            statement = statement.join(CareerProfileModel).where(
                CareerProfileModel.owner_sub == owner_sub
            )
        locked_id = self.session.scalar(statement.with_for_update())
        if locked_id is None:
            return None
        return (
            self.session.scalars(
                self._versions(owner_sub).where(ProfileVersionModel.id == locked_id)
            )
            .unique()
            .one()
        )

    @staticmethod
    def _versions(owner_sub: str | None = None) -> Select[tuple[ProfileVersionModel]]:
        statement = select(ProfileVersionModel).options(
            joinedload(ProfileVersionModel.skills).joinedload(ProfileSkillModel.skill),
            joinedload(ProfileVersionModel.experiences),
            joinedload(ProfileVersionModel.projects),
            joinedload(ProfileVersionModel.preference),
        )
        if owner_sub is not None:
            statement = statement.join(CareerProfileModel).where(
                CareerProfileModel.owner_sub == owner_sub
            )
        return statement
