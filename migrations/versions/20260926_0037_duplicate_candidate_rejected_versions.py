"""Add rejected-version columns to `opportunities.duplicate_candidate`.

Revision ID: 20260926_0037
Revises: 20260926_0036
Create Date: 2026-09-26 00:00:00

Card F20-26, merge contract: "recusa e contextualizada por versao, com politica para
revisao apos mudanca material". A rejected pair stores both opportunities' `version` at
the moment of rejection; `find_title_location_window_candidates` compares the current
versions against these and only keeps the pair suppressed while neither side changed.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0037"
down_revision = "20260926_0036"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"
TABLE = "duplicate_candidate"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("rejected_version_opportunity", sa.Integer()),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("rejected_version_duplicate_opportunity", sa.Integer()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column(TABLE, "rejected_version_duplicate_opportunity", schema=SCHEMA)
    op.drop_column(TABLE, "rejected_version_opportunity", schema=SCHEMA)
