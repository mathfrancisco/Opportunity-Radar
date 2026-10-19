"""Drop the match_factor index that the unique constraint already covers (R55-E6).

Revision ID: 20261018_0076
Revises: 20261017_0075

`uq_match_factor_assessment_code` is a btree on (assessment_id, factor_code), so every
lookup and every FK cascade by `assessment_id` alone is served by its leading column.
`ix_match_factor_assessment` on (assessment_id) is a strict prefix of it: it costs space and
write time on ~57k rows and no query can use it that the unique index cannot.

No data is touched, no rule version changes, no assessment is re-evaluated. Downgrade
recreates the index (a plain build on a table of this size).
"""

from __future__ import annotations

from alembic import op

revision = "20261018_0076"
down_revision = "20261017_0075"
branch_labels = None
depends_on = None

INDEX = "ix_match_factor_assessment"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS matching.{INDEX}")


def downgrade() -> None:
    op.create_index(
        INDEX,
        "match_factor",
        ["assessment_id"],
        schema="matching",
        if_not_exists=True,
    )
