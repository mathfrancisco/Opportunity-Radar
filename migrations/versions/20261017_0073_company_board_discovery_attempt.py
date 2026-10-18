"""Companies remember their last board-discovery attempt (R55-B6).

Revision ID: 20261017_0073
Revises: 20261017_0072

`scripts/discover_boards.py --apply` stamps a company that no board could be found for, so a
rerun within the retry window neither re-probes it nor re-spends Tavily credits on it.
`board_discovery_used_tavily` says whether that attempt included the paid search, so a later
run that does use Tavily still gets its turn after a probe-only attempt. Both columns are
nullable and unused by anything else; downgrade drops them.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0073"
down_revision = "20261017_0072"
branch_labels = None
depends_on = None

SCHEMA = "company_radar"


def upgrade() -> None:
    op.add_column(
        "company",
        sa.Column("board_discovery_attempted_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "company",
        sa.Column("board_discovery_used_tavily", sa.Boolean(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("company", "board_discovery_used_tavily", schema=SCHEMA)
    op.drop_column("company", "board_discovery_attempted_at", schema=SCHEMA)
