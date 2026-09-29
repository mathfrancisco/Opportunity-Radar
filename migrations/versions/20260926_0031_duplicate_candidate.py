"""Add `opportunities.duplicate_candidate` and `opportunity.duplicate_of`.

Revision ID: 20260926_0031
Revises: 20260926_0030
Create Date: 2026-09-26 00:00:00

Card F20-26. The fingerprint includes the publication day on purpose, so the same
vacancy posted on a company board and on a broad source, days apart, becomes two
opportunities. This table records candidate pairs found by the `title_location_window`
rule (SPEC 43 SS9); `embedding` stays in the enum for a later phase with no generator
here. Nothing merges automatically — an operator confirms or rejects each pair.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0031"
down_revision = "20260926_0030"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"


def upgrade() -> None:
    op.add_column(
        "opportunity",
        sa.Column(
            "duplicate_of",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="SET NULL"),
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "duplicate_candidate",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "duplicate_opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule", sa.String(32), nullable=False),
        sa.Column("score", sa.Numeric(4, 3)),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("decided_by", sa.String(255)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "rule IN ('title_location_window', 'embedding')",
            name="ck_duplicate_candidate_rule",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'REJECTED')",
            name="ck_duplicate_candidate_status",
        ),
        sa.CheckConstraint(
            "opportunity_id < duplicate_opportunity_id",
            name="ck_duplicate_candidate_ordered_pair",
        ),
        sa.UniqueConstraint(
            "opportunity_id",
            "duplicate_opportunity_id",
            name="uq_duplicate_candidate_pair",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("duplicate_candidate", schema=SCHEMA)
    op.drop_column("opportunity", "duplicate_of", schema=SCHEMA)
