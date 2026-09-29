"""Add `opportunities.field_suggestion`.

Revision ID: 20260926_0052
Revises: 20260926_0044
Create Date: 2026-09-26 00:00:00

Card F20-23. `role-family-v1`, `seniority-v2` and `regions-v1` leave a job's area,
seniority or work mode `UNKNOWN` when the deterministic rules find no confident answer.
This table holds a `fast`-model suggestion for one of those fields, kept fully separate
from the canonical `opportunity` column (F18-06/F20-24's rule): a suggestion only becomes
the canonical value once an operator accepts it through `opportunities.suggestions`. The
unique constraint on `(opportunity_id, opportunity_version, field)` is what makes the
suggestion job idempotent per version — reclassifying after the posting changed gets a
new row instead of overwriting the one an operator may still be reviewing.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0052"
down_revision = "20260926_0044"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"


def upgrade() -> None:
    op.create_table(
        "field_suggestion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(32), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
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
            "field IN ('role_family', 'seniority', 'work_mode')",
            name="ck_field_suggestion_field",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_field_suggestion_status",
        ),
        sa.UniqueConstraint(
            "opportunity_id",
            "opportunity_version",
            "field",
            name="uq_field_suggestion_opportunity_version_field",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_field_suggestion_status",
        "field_suggestion",
        ["status"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_field_suggestion_status", table_name="field_suggestion", schema=SCHEMA)
    op.drop_table("field_suggestion", schema=SCHEMA)
