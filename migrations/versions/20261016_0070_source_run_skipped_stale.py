"""Count items the ingestion filter dropped for being older than the freshness window (R55-E1).

Revision ID: 20261016_0070
Revises: 20261008_0069
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261016_0070"
down_revision = "20261008_0069"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "source_run"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("skipped_stale", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "skipped_stale", schema=SCHEMA)
