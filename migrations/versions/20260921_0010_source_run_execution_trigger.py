"""Add the initiation origin for source runs.

Revision ID: 20260921_0010
Revises: 20260918_0009
Create Date: 2026-09-21 00:00:00

Compatibility policy: every run that existed before this column is ON_DEMAND.
The application had no scheduler before F10-03, so this preserves historical
meaning without guessing an origin. The nullable addition, explicit backfill,
and final NOT NULL constraint keep pre-existing rows intact during upgrade.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260921_0010"
down_revision = "20260918_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column(
            "execution_trigger",
            sa.String(length=16),
            nullable=True,
            server_default=sa.text("'ON_DEMAND'"),
        ),
        schema="acquisition",
    )
    op.execute(
        "UPDATE acquisition.source_run "
        "SET execution_trigger = 'ON_DEMAND' "
        "WHERE execution_trigger IS NULL"
    )
    op.alter_column(
        "source_run",
        "execution_trigger",
        existing_type=sa.String(length=16),
        nullable=False,
        schema="acquisition",
    )
    op.create_check_constraint(
        "ck_source_run_execution_trigger",
        "source_run",
        "execution_trigger IN ('ON_DEMAND', 'SCHEDULED')",
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_source_run_execution_trigger",
        "source_run",
        schema="acquisition",
        type_="check",
    )
    op.drop_column("source_run", "execution_trigger", schema="acquisition")
