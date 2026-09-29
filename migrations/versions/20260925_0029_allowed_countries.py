"""Add `allowed_countries` and its `regions-v1` version to `opportunity`.

Revision ID: 20260925_0029
Revises: 20260925_0028
Create Date: 2026-09-25 13:00:00

Card F17-06. `allowed_countries` holds ISO 3166-1 alpha-2 codes (or the `ANY` sentinel
for Anywhere/Worldwide) the `regions-v1` table resolves from `location_text`. `NULL`
means unknown — never read as "no country allowed": office location is never allowed
country. Existing rows stay `NULL` until reprocessed; renormalization is a later task.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0029"
down_revision = "20260925_0028"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"


def upgrade() -> None:
    op.add_column(
        "opportunity",
        sa.Column("allowed_countries", postgresql.ARRAY(sa.String(8))),
        schema=SCHEMA,
    )
    op.add_column(
        "opportunity",
        sa.Column("allowed_countries_version", sa.String(32)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_opportunity_allowed_countries",
        "opportunity",
        ["allowed_countries"],
        schema=SCHEMA,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_allowed_countries", table_name="opportunity", schema=SCHEMA
    )
    op.drop_column("opportunity", "allowed_countries_version", schema=SCHEMA)
    op.drop_column("opportunity", "allowed_countries", schema=SCHEMA)
