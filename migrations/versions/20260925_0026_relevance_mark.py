"""Add the append-only operator relevance mark.

Revision ID: 20260925_0026
Revises: 20260925_0025
Create Date: 2026-09-25 12:00:00

Card F17-01. The current mark for an opportunity is the most recent row; history is
never updated or deleted, so precision can be recomputed against a past profile version.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0026"
down_revision = "20260925_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relevance_mark",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relevant", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(16)),
        sa.Column("note", sa.Text()),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "marked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "reason IS NULL OR reason IN "
            "('AREA', 'SENIORITY', 'LOCATION', 'COMPANY', 'COMPENSATION', 'OTHER')",
            name="ck_relevance_mark_reason",
        ),
        schema="opportunities",
    )
    op.create_index(
        "ix_relevance_mark_opportunity_marked_at",
        "relevance_mark",
        ["opportunity_id", "marked_at"],
        schema="opportunities",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_relevance_mark_opportunity_marked_at",
        table_name="relevance_mark",
        schema="opportunities",
    )
    op.drop_table("relevance_mark", schema="opportunities")
