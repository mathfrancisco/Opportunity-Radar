"""Count items the ingestion area/country prefilter kept out of storage (R55-B5).

Revision ID: 20261017_0075
Revises: 20261017_0074
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0075"
down_revision = "20261017_0074"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "source_run"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("skipped_off_target", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "skipped_off_target", schema=SCHEMA)
