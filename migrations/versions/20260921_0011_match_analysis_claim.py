"""Add the exclusive claim over the semantic analysis of an assessment.

Revision ID: 20260921_0011
Revises: 20260921_0010
Create Date: 2026-09-21 00:00:00

Purely additive: a new table, no column or constraint change on existing ones, so no
backfill is required and no historical analysis row is touched. The claim is operational
state, not history — dropping the table on downgrade loses nothing auditable.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260921_0011"
down_revision = "20260921_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_analysis_claim",
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching.match_assessment.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > claimed_at", name="ck_match_analysis_claim_window"
        ),
        schema="matching",
    )
    op.create_index(
        "ix_match_analysis_claim_expires_at",
        "match_analysis_claim",
        ["expires_at"],
        schema="matching",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_match_analysis_claim_expires_at",
        table_name="match_analysis_claim",
        schema="matching",
    )
    op.drop_table("match_analysis_claim", schema="matching")
