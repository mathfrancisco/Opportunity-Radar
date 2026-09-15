"""Create Opportunities persistence tables.

Revision ID: 20260914_0005
Revises: 20260913_0004
Create Date: 2026-09-14 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260914_0005"
down_revision = "20260913_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("fingerprint_version", sa.String(32), nullable=False),
        sa.Column("canonical_title", sa.String(512), nullable=False),
        sa.Column("normalized_title", sa.String(512), nullable=False),
        sa.Column(
            "canonical_company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_radar.company.id", ondelete="SET NULL"),
        ),
        sa.Column("company_name", sa.String(255)),
        sa.Column("normalized_company_name", sa.String(255)),
        sa.Column("location_text", sa.String(512)),
        sa.Column("normalized_location", sa.String(512)),
        sa.Column("work_mode", sa.String(16), nullable=False, server_default="UNKNOWN"),
        sa.Column("seniority", sa.String(16), nullable=False, server_default="UNKNOWN"),
        sa.Column(
            "contract_type", sa.String(16), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column(
            "description",
            sa.Text(),
        ),
        sa.Column(
            "lifecycle_status",
            sa.String(16),
            nullable=False,
            server_default="DISCOVERED",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
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
        sa.UniqueConstraint(
            "fingerprint_version",
            "fingerprint",
            name="uq_opportunity_fingerprint_version_value",
        ),
        sa.CheckConstraint(
            "work_mode IN ('REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN')",
            name="ck_opportunity_work_mode",
        ),
        sa.CheckConstraint(
            "seniority IN ('INTERN', 'JUNIOR', 'MID', 'SENIOR', 'LEAD', "
            "'STAFF', 'MANAGER', 'DIRECTOR', 'UNKNOWN')",
            name="ck_opportunity_seniority",
        ),
        sa.CheckConstraint(
            "contract_type IN ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY', "
            "'INTERNSHIP', 'UNKNOWN')",
            name="ck_opportunity_contract_type",
        ),
        sa.CheckConstraint(
            "lifecycle_status IN ('DISCOVERED', 'ACTIVE', 'STALE', 'CLOSED', "
            "'ARCHIVED', 'REJECTED')",
            name="ck_opportunity_lifecycle_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_opportunity_version_positive"),
        schema="opportunities",
    )
    op.create_index(
        "ix_opportunity_company_status",
        "opportunity",
        ["canonical_company_id", "lifecycle_status"],
        schema="opportunities",
    )
    op.create_index(
        "ix_opportunity_published",
        "opportunity",
        ["published_at"],
        schema="opportunities",
    )

    op.create_table(
        "source_occurrence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(512)),
        sa.Column("source_url", sa.String(2048)),
        sa.Column("normalized_source_url", sa.String(2048)),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source_published_at", sa.DateTime(timezone=True)),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("raw_item_id", name="uq_source_occurrence_raw_item"),
        schema="opportunities",
    )
    op.create_index(
        "uq_source_occurrence_source_external",
        "source_occurrence",
        ["source_definition_id", "external_id"],
        unique=True,
        schema="opportunities",
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.create_index(
        "uq_source_occurrence_source_url_fallback",
        "source_occurrence",
        ["source_definition_id", "normalized_source_url"],
        unique=True,
        schema="opportunities",
        postgresql_where=sa.text(
            "external_id IS NULL AND normalized_source_url IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_source_occurrence_source_url",
        "source_occurrence",
        ["source_url"],
        schema="opportunities",
    )
    op.create_index(
        "ix_source_occurrence_normalized_url",
        "source_occurrence",
        ["normalized_source_url"],
        schema="opportunities",
    )

    op.create_table(
        "normalization_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "raw_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "source_occurrence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "opportunities.source_occurrence.id", ondelete="CASCADE"
            ),
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("normalizer_version", sa.String(32), nullable=False),
        sa.Column("identity_decision", sa.String(16)),
        sa.Column(
            "reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("error_summary", sa.Text()),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "raw_item_id",
            "normalizer_version",
            name="uq_normalization_result_raw_version",
        ),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'REVIEW_REQUIRED', 'FAILED')",
            name="ck_normalization_result_status",
        ),
        sa.CheckConstraint(
            "identity_decision IN ('NEW', 'MERGED', 'REFRESHED', 'REVIEW')",
            name="ck_normalization_result_identity_decision",
        ),
        sa.CheckConstraint(
            "(status = 'FAILED' AND error_summary IS NOT NULL "
            "AND identity_decision IS NULL AND opportunity_id IS NULL "
            "AND source_occurrence_id IS NULL) "
            "OR (status IN ('SUCCEEDED', 'REVIEW_REQUIRED') "
            "AND error_summary IS NULL AND identity_decision IS NOT NULL "
            "AND opportunity_id IS NOT NULL "
            "AND source_occurrence_id IS NOT NULL)",
            name="ck_normalization_result_outcome",
        ),
        schema="opportunities",
    )


def downgrade() -> None:
    op.drop_table("normalization_result", schema="opportunities")
    op.drop_index(
        "uq_source_occurrence_source_url_fallback",
        table_name="source_occurrence",
        schema="opportunities",
    )
    op.drop_index(
        "ix_source_occurrence_normalized_url",
        table_name="source_occurrence",
        schema="opportunities",
    )
    op.drop_index(
        "ix_source_occurrence_source_url",
        table_name="source_occurrence",
        schema="opportunities",
    )
    op.drop_index(
        "uq_source_occurrence_source_external",
        table_name="source_occurrence",
        schema="opportunities",
    )
    op.drop_table("source_occurrence", schema="opportunities")
    op.drop_index(
        "ix_opportunity_published",
        table_name="opportunity",
        schema="opportunities",
    )
    op.drop_index(
        "ix_opportunity_company_status",
        table_name="opportunity",
        schema="opportunities",
    )
    op.drop_table("opportunity", schema="opportunities")
