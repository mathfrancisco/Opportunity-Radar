"""Add profile target titles for keyword search.

Revision ID: 20260926_0035
Revises: 20260926_0034
Create Date: 2026-09-26 00:00:00

Card F20-33. Target titles are explicit profile preferences, not model-generated terms.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0035"
down_revision = "20260926_0034"
branch_labels = None
depends_on = None

SCHEMA = "profile"


def upgrade() -> None:
    op.add_column(
        "employment_preference",
        sa.Column(
            "target_titles",
            postgresql.ARRAY(sa.String(128)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("employment_preference", "target_titles", schema=SCHEMA)
