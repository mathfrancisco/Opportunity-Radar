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

    def career_profile_for_update(self) -> CareerProfileModel | None:
        return self.session.scalar(select(CareerProfileModel).limit(1))

    def active_version(self) -> ProfileVersionModel | None:
        return self.session.scalars(
            self._versions().where(ProfileVersionModel.status == "ACTIVE")
        ).unique().one_or_none()

    def version(self, version_id: UUID) -> ProfileVersionModel | None:
        return self.session.scalars(
            self._versions().where(ProfileVersionModel.id == version_id)
        ).unique().one_or_none()

    def versions(self) -> list[ProfileVersionModel]:
        return list(
            self.session.scalars(
                self._versions().order_by(ProfileVersionModel.number.desc())
            ).unique()
        )

    def version_for_update(self, version_id: UUID) -> ProfileVersionModel | None:
        locked_id = self.session.scalar(
            select(ProfileVersionModel.id)
            .where(ProfileVersionModel.id == version_id)
            .with_for_update()
        )
        if locked_id is None:
            return None
        return self.session.scalars(
            self._versions().where(ProfileVersionModel.id == locked_id)
        ).unique().one()

    @staticmethod
    def _versions() -> Select[tuple[ProfileVersionModel]]:
        return select(ProfileVersionModel).options(
            joinedload(ProfileVersionModel.skills).joinedload(ProfileSkillModel.skill),
            joinedload(ProfileVersionModel.experiences),
            joinedload(ProfileVersionModel.projects),
            joinedload(ProfileVersionModel.preference),
        )
