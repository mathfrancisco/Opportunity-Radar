"""Index source occurrences by opportunity.

Revision ID: 20261004_0061
Revises: 20260929_0060
Create Date: 2026-10-04 00:00:00

The Inbox groups postings by their first occurrence source (card F48-10), a correlated
lookup by `opportunity_id` per listed row. The foreign key had no index, so each lookup
scanned the whole table: with 25k opportunities the Inbox, the overview and the search
metrics took over two minutes.
"""

from alembic import op

revision = "20261004_0061"
down_revision = "20260929_0060"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"
OCCURRENCE = "source_occurrence"


def upgrade() -> None:
    op.create_index(
        "ix_source_occurrence_opportunity", OCCURRENCE, ["opportunity_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_source_occurrence_opportunity", table_name=OCCURRENCE, schema=SCHEMA)
