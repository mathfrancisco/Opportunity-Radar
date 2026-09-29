"""Add the accepted seniorities preference to the profile.

Revision ID: 20260929_0058
Revises: 20260929_0057
Create Date: 2026-09-29 00:00:00

Card F48-13. Existing versions are backfilled with INTERN, JUNIOR, MID and UNKNOWN (decision
2 of the spec); SENIOR and above rank lower but are never excluded by the matching rules.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260929_0058"
down_revision = "20260929_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employment_preference",
        sa.Column(
            "accepted_seniorities",
            postgresql.ARRAY(sa.String(16)),
            nullable=False,
            server_default=sa.text("'{INTERN,JUNIOR,MID,UNKNOWN}'::varchar[]"),
        ),
        schema="profile",
    )


def downgrade() -> None:
    op.drop_column("employment_preference", "accepted_seniorities", schema="profile")
