"""Add compensation and skill evidence to opportunities.

Revision ID: 20260915_0006
Revises: 20260914_0005
Create Date: 2026-09-15 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260915_0006"
down_revision = "20260914_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_compensation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount_min", sa.Numeric(14, 2)),
        sa.Column("amount_max", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("period", sa.String(16), nullable=False, server_default="UNKNOWN"),
        sa.Column("gross_net", sa.String(16), nullable=False, server_default="UNKNOWN"),
        sa.Column("evidence_text", sa.Text()),
        sa.Column("evidence_source", sa.String(512)),
        sa.Column("normalizer_version", sa.String(32), nullable=False),
        sa.Column(
            "source_occurrence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "opportunities.source_occurrence.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "raw_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
            nullable=False,
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
        sa.UniqueConstraint(
            "source_occurrence_id",
            name="uq_opportunity_compensation_source_occurrence",
        ),
        sa.CheckConstraint(
            "amount_min IS NOT NULL OR amount_max IS NOT NULL",
            name="ck_opportunity_compensation_amount_present",
        ),
        sa.CheckConstraint(
            "amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max",
            name="ck_opportunity_compensation_range",
        ),
        sa.CheckConstraint(
            "period IN ('YEAR', 'MONTH', 'WEEK', 'DAY', 'HOUR', 'UNKNOWN')",
            name="ck_opportunity_compensation_period",
        ),
        sa.CheckConstraint(
            "gross_net IN ('GROSS', 'NET', 'UNKNOWN')",
            name="ck_opportunity_compensation_gross_net",
        ),
        schema="opportunities",
    )
    op.create_index(
        "ix_opportunity_compensation_currency_period",
        "opportunity_compensation",
        ["currency", "period"],
        schema="opportunities",
    )

    op.create_table(
        "opportunity_skill",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column(
            "requirement", sa.String(16), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("taxonomy_version", sa.String(32), nullable=False),
        sa.Column("normalizer_version", sa.String(32), nullable=False),
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
        sa.UniqueConstraint(
            "opportunity_id",
            "canonical_name",
            "taxonomy_version",
            name="uq_opportunity_skill_opportunity_name_taxonomy",
        ),
        sa.CheckConstraint(
            "requirement IN ('REQUIRED', 'PREFERRED', 'UNKNOWN')",
            name="ck_opportunity_skill_requirement",
        ),
        schema="opportunities",
    )
    op.create_index(
        "ix_opportunity_skill_requirement",
        "opportunity_skill",
        ["requirement"],
        schema="opportunities",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_skill_requirement",
        table_name="opportunity_skill",
        schema="opportunities",
    )
    op.drop_table("opportunity_skill", schema="opportunities")
    op.drop_index(
        "ix_opportunity_compensation_currency_period",
        table_name="opportunity_compensation",
        schema="opportunities",
    )
    op.drop_table("opportunity_compensation", schema="opportunities")
