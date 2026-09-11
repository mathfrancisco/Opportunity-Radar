"""Create Profile and Company Radar catalogs.

Revision ID: 20260910_0002
Revises: 20260910_0001
Create Date: 2026-09-10 00:00:01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260910_0002"
down_revision = "20260910_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "career_profile",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "singleton_key",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("singleton_key", name="ck_career_profile_singleton"),
        sa.UniqueConstraint("singleton_key", name="uq_career_profile_singleton_key"),
        schema="profile",
    )
    op.create_table(
        "profile_version",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "career_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.career_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ACTIVE', 'ARCHIVED')",
            name="ck_profile_version_status",
        ),
        sa.UniqueConstraint(
            "career_profile_id",
            "number",
            name="uq_profile_version_number",
        ),
        schema="profile",
    )
    op.create_index(
        "uq_profile_version_active",
        "profile_version",
        ["career_profile_id"],
        unique=True,
        schema="profile",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_table(
        "skill",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("canonical_name", name="uq_skill_canonical_name"),
        schema="profile",
    )
    op.create_table(
        "profile_skill",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.skill.id"),
            nullable=False,
        ),
        sa.Column("level", sa.String(32)),
        sa.Column("last_used_at", sa.Date()),
        sa.Column("experience_months", sa.Integer()),
        sa.CheckConstraint(
            "experience_months IS NULL OR experience_months >= 0",
            name="ck_profile_skill_months",
        ),
        sa.UniqueConstraint(
            "profile_version_id",
            "skill_id",
            name="uq_profile_skill_version_skill",
        ),
        schema="profile",
    )
    op.create_table(
        "experience",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_name", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date()),
        sa.Column("summary", sa.Text()),
        sa.CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on",
            name="ck_experience_dates",
        ),
        schema="profile",
    )
    op.create_table(
        "project",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("started_on", sa.Date()),
        sa.Column("ended_on", sa.Date()),
        sa.Column("description", sa.Text()),
        sa.Column("url", sa.String(2048)),
        sa.CheckConstraint(
            "ended_on IS NULL OR started_on IS NULL OR ended_on >= started_on",
            name="ck_project_dates",
        ),
        schema="profile",
    )
    op.create_table(
        "employment_preference",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_modes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "contracts",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column(
            "countries",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        sa.Column("timezone_start_hour", sa.Integer()),
        sa.Column("timezone_end_hour", sa.Integer()),
        sa.Column("compensation_min", sa.Numeric(14, 2)),
        sa.Column("compensation_max", sa.Numeric(14, 2)),
        sa.Column("compensation_currency", sa.String(3)),
        sa.Column(
            "relocation_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "sponsorship_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.CheckConstraint(
            "compensation_min IS NULL OR compensation_max IS NULL "
            "OR compensation_min <= compensation_max",
            name="ck_preference_compensation",
        ),
        sa.CheckConstraint(
            "(timezone_start_hour IS NULL AND timezone_end_hour IS NULL) OR "
            "(timezone_start_hour IS NOT NULL AND timezone_end_hour IS NOT NULL "
            "AND timezone_start_hour >= 0 AND timezone_start_hour < timezone_end_hour "
            "AND timezone_end_hour <= 23)",
            name="ck_preference_timezone",
        ),
        sa.UniqueConstraint(
            "profile_version_id",
            name="uq_preference_profile_version",
        ),
        schema="profile",
    )

    op.create_table(
        "company",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(253)),
        sa.Column(
            "priority",
            sa.String(20),
            nullable=False,
            server_default="normal",
        ),
        sa.Column(
            "radar_status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "verification_state",
            sa.String(30),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("domain", name="uq_company_domain"),
        schema="company_radar",
    )
    op.create_index(
        "ix_company_normalized_name",
        "company",
        ["normalized_name"],
        schema="company_radar",
    )
    op.create_table(
        "company_alias",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_radar.company.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("normalized_alias", sa.String(255), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "normalized_alias",
            name="uq_company_alias_company_normalized",
        ),
        schema="company_radar",
    )
    op.create_index(
        "ix_company_alias_normalized_alias",
        "company_alias",
        ["normalized_alias"],
        schema="company_radar",
    )
    op.create_table(
        "company_source",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_radar.company.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("external_key", sa.String(255)),
        sa.Column(
            "verification_status",
            sa.String(30),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("confidence", sa.Numeric(4, 3)),
        sa.Column("verification_method", sa.String(50)),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_company_source_confidence",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_type",
            "endpoint",
            name="uq_company_source_company_type_endpoint",
        ),
        schema="company_radar",
    )
    op.create_table(
        "company_import_batch",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="running",
        ),
        sa.Column("report", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("file_hash", name="uq_company_import_batch_file_hash"),
        schema="company_radar",
    )
    op.create_table(
        "company_import_issue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_radar.company_import_batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB()),
        schema="company_radar",
    )


def downgrade() -> None:
    op.drop_table("company_import_issue", schema="company_radar")
    op.drop_table("company_import_batch", schema="company_radar")
    op.drop_table("company_source", schema="company_radar")
    op.drop_index(
        "ix_company_alias_normalized_alias",
        table_name="company_alias",
        schema="company_radar",
    )
    op.drop_table("company_alias", schema="company_radar")
    op.drop_index(
        "ix_company_normalized_name",
        table_name="company",
        schema="company_radar",
    )
    op.drop_table("company", schema="company_radar")

    op.drop_table("employment_preference", schema="profile")
    op.drop_table("project", schema="profile")
    op.drop_table("experience", schema="profile")
    op.drop_table("profile_skill", schema="profile")
    op.drop_table("skill", schema="profile")
    op.drop_index(
        "uq_profile_version_active",
        table_name="profile_version",
        schema="profile",
    )
    op.drop_table("profile_version", schema="profile")
    op.drop_table("career_profile", schema="profile")
