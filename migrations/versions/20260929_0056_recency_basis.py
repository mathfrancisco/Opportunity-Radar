"""Add `opportunities.opportunity.recency_basis` (recency reference basis).

Revision ID: 20260929_0056
Revises: 20260929_0054
Create Date: 2026-09-29 00:00:00

Card F48-16. The recency reference is `published_at ?? source_updated_at ??
first_seen_at`; `recency_basis` (`published`, `updated`, `first_seen`) records which one
won so the UI can mark the date "estimada" when it is not `published`. Backfilled from the
two nullable date columns, then made `NOT NULL`.

Chaining note: created off `20260929_0054` independently of the concurrent
`20260929_0055` collection-alarm revision; re-chain `down_revision` on merge.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260929_0056"
down_revision = "20260929_0054"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"
TABLE = "opportunity"
CONSTRAINT = "ck_opportunity_recency_basis"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(
            "recency_basis",
            sa.String(16),
            nullable=False,
            server_default="first_seen",
        ),
        schema=SCHEMA,
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
        SET recency_basis = CASE
            WHEN published_at IS NOT NULL THEN 'published'
            WHEN source_updated_at IS NOT NULL THEN 'updated'
            ELSE 'first_seen'
        END
        """
    )
    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        "recency_basis IN ('published', 'updated', 'first_seen')",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.drop_column(TABLE, "recency_basis", schema=SCHEMA)
