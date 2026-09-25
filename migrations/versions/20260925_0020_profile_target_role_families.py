"""Let a profile version declare the areas it is interested in.

Revision ID: 20260925_0020
Revises: 20260924_0019
Create Date: 2026-09-25 09:00:00

Card F17-02. `target_role_families` lists the `role-family-v1` areas the Inbox shows by
default. An empty array means every area, which is what every existing version meant, so
the column is filled with it instead of guessing an interest nobody declared.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0020"
down_revision = "20260924_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employment_preference",
        sa.Column(
            "target_role_families",
            postgresql.ARRAY(sa.String(32)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
        schema="profile",
    )


def downgrade() -> None:
    op.drop_column("employment_preference", "target_role_families", schema="profile")
