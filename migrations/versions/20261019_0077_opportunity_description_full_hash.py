"""Add a hash of the full cleaned description to the opportunity (R55-E6).

Revision ID: 20261019_0077
Revises: 20261018_0076

The stored description is cleaned and capped, so the churn guard could not see a change
made only past the cap. `opportunities.opportunity.description_full_hash` keeps the sha256
(hex, 64 chars) of the full cleaned description, written when the cap cut the text. Nullable
and not backfilled: old rows keep the previous comparison until they are next reprocessed.
Downgrade drops the column; the guard then falls back to the stored text.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261019_0077"
down_revision = "20261018_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunity",
        sa.Column("description_full_hash", sa.String(length=64), nullable=True),
        schema="opportunities",
    )


def downgrade() -> None:
    op.drop_column("opportunity", "description_full_hash", schema="opportunities")
