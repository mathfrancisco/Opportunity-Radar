"""Add `company_radar.company_startup_evidence` (append-only startup evidence).

Revision ID: 20260929_0054
Revises: 20260928_0053
Create Date: 2026-09-29 00:00:00

Card F20-54. Signal type, strength, source text/URL, optional YC batch and capture date,
one row per sighting. No backfill: the card defines no source for existing companies.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260929_0054"
down_revision = "20260928_0053"
branch_labels = None
depends_on = None

SCHEMA = "company_radar"
TABLE = "company_startup_evidence"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal", sa.String(20), nullable=False),
        sa.Column("strength", sa.String(10), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("batch", sa.String(20)),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], [f"{SCHEMA}.company.id"], ondelete="CASCADE"
        ),
        sa.CheckConstraint(
            "signal IN ('yc_batch', 'seed_stage', 'series_a', 'other')",
            name="ck_company_startup_evidence_signal",
        ),
        sa.CheckConstraint(
            "strength IN ('strong', 'weak')",
            name="ck_company_startup_evidence_strength",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_company_startup_evidence_company", TABLE, ["company_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_company_startup_evidence_company", table_name=TABLE, schema=SCHEMA)
    op.drop_table(TABLE, schema=SCHEMA)
