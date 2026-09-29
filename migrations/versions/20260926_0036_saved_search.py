"""Add saved searches for the dashboard.

Revision ID: 20260926_0036
Revises: 20260926_0035
Create Date: 2026-09-26 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0036"
down_revision = "20260926_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE SCHEMA IF NOT EXISTS "dashboard"')
    op.create_table(
        "saved_search",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("term", sa.String(), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_saved_search"),
        schema="dashboard",
    )


def downgrade() -> None:
    op.drop_table("saved_search", schema="dashboard")
    op.execute('DROP SCHEMA IF EXISTS "dashboard"')
