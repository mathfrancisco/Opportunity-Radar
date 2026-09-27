"""Add F20-39 resume provenance between runs of the same source.

Revision ID: 20260926_0043
Revises: 20260926_0042

A run that ends PARTIAL still commits a real, persisted prefix of evidence atomically
with its own row. This column records, only as provenance, which earlier run a later
run explicitly continues (the caller supplies the explicit cursor separately) — it is
never used to derive a cursor or to change dedupe/completeness on its own.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0043"
down_revision = "20260926_0042"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "source_run"
COLUMN = "resumed_from_run_id"
CONSTRAINT = "fk_source_run_resumed_from_run_id"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column(COLUMN, postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        CONSTRAINT,
        TABLE,
        TABLE,
        [COLUMN],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_column(TABLE, COLUMN, schema=SCHEMA)
