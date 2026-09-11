"""SQLAlchemy persistence models for the Profile context."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from opportunity_radar.platform.database import Base


class CareerProfileModel(Base):
    __tablename__ = "career_profile"
    __table_args__ = (
        CheckConstraint("singleton_key", name="ck_career_profile_singleton"),
        UniqueConstraint("singleton_key", name="uq_career_profile_singleton_key"),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    singleton_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    versions: Mapped[list["ProfileVersionModel"]] = relationship(
        back_populates="career_profile", cascade="all, delete-orphan"
    )


class ProfileVersionModel(Base):
    __tablename__ = "profile_version"
    __table_args__ = (
        UniqueConstraint("career_profile_id", "number", name="uq_profile_version_number"),
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ACTIVE', 'ARCHIVED')",
            name="ck_profile_version_status",
        ),
        Index(
            "uq_profile_version_active",
            "career_profile_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    career_profile_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.career_profile.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    career_profile: Mapped[CareerProfileModel] = relationship(back_populates="versions")
    skills: Mapped[list["ProfileSkillModel"]] = relationship(
        back_populates="profile_version", cascade="all, delete-orphan"
    )
    experiences: Mapped[list["ExperienceModel"]] = relationship(
        back_populates="profile_version", cascade="all, delete-orphan"
    )
    projects: Mapped[list["ProjectModel"]] = relationship(
        back_populates="profile_version", cascade="all, delete-orphan"
    )
    preference: Mapped["EmploymentPreferenceModel | None"] = relationship(
        back_populates="profile_version", cascade="all, delete-orphan", uselist=False
    )


class SkillModel(Base):
    __tablename__ = "skill"
    __table_args__ = (
        UniqueConstraint("canonical_name", name="uq_skill_canonical_name"),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProfileSkillModel(Base):
    __tablename__ = "profile_skill"
    __table_args__ = (
        UniqueConstraint(
            "profile_version_id",
            "skill_id",
            name="uq_profile_skill_version_skill",
        ),
        CheckConstraint(
            "experience_months IS NULL OR experience_months >= 0",
            name="ck_profile_skill_months",
        ),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    profile_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("profile.skill.id"), nullable=False
    )
    level: Mapped[str | None] = mapped_column(String(32))
    last_used_at: Mapped[date | None] = mapped_column(Date)
    experience_months: Mapped[int | None] = mapped_column(Integer)
    skill: Mapped[SkillModel] = relationship()
    profile_version: Mapped[ProfileVersionModel] = relationship(back_populates="skills")


class ExperienceModel(Base):
    __tablename__ = "experience"
    __table_args__ = (
        CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on",
            name="ck_experience_dates",
        ),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    profile_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    ended_on: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str | None] = mapped_column(Text)
    profile_version: Mapped[ProfileVersionModel] = relationship(
        back_populates="experiences"
    )


class ProjectModel(Base):
    __tablename__ = "project"
    __table_args__ = (
        CheckConstraint(
            "ended_on IS NULL OR started_on IS NULL OR ended_on >= started_on",
            name="ck_project_dates",
        ),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    profile_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    started_on: Mapped[date | None] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048))
    profile_version: Mapped[ProfileVersionModel] = relationship(back_populates="projects")


class EmploymentPreferenceModel(Base):
    __tablename__ = "employment_preference"
    __table_args__ = (
        CheckConstraint(
            "compensation_min IS NULL OR compensation_max IS NULL "
            "OR compensation_min <= compensation_max",
            name="ck_preference_compensation",
        ),
        CheckConstraint(
            "(timezone_start_hour IS NULL AND timezone_end_hour IS NULL) OR "
            "(timezone_start_hour IS NOT NULL AND timezone_end_hour IS NOT NULL "
            "AND timezone_start_hour >= 0 AND timezone_start_hour < timezone_end_hour "
            "AND timezone_end_hour <= 23)",
            name="ck_preference_timezone",
        ),
        UniqueConstraint("profile_version_id", name="uq_preference_profile_version"),
        {"schema": "profile"},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4
    )
    profile_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_modes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    contracts: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    countries: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    timezone_start_hour: Mapped[int | None] = mapped_column(Integer)
    timezone_end_hour: Mapped[int | None] = mapped_column(Integer)
    compensation_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    compensation_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    compensation_currency: Mapped[str | None] = mapped_column(String(3))
    relocation_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    sponsorship_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    profile_version: Mapped[ProfileVersionModel] = relationship(
        back_populates="preference"
    )
