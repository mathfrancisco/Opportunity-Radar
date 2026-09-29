"""Add `acquisition.host_budget_state` for the shared request budget per host/provider.

Revision ID: 20260926_0040
Revises: 20260926_0037
Create Date: 2026-09-26 00:00:00

Card F20-38. Scheduling decides today's `CollectionGate` per source; nothing tracks how
many requests every source of one host/provider already spent in the current window, so
two sources of the same board could jointly exceed the provider's own rate limit. This
table is the persisted counter `evaluate_gate`/`next_due_at` read via
`SourceSchedulingState.host_budget` (see `acquisition/scheduling.py::HostBudgetState`):
one row per host, `requests_used` reset on window rollover, `cooldown_until` set from a
provider's `Retry-After` and surviving a worker restart because it lives here, not in
memory.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0040"
down_revision = "20260926_0037"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "host_budget_state"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("host", sa.String(255), primary_key=True),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "requests_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("requests_ceiling", sa.Integer(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True)),
        sa.Column(
            "exploration_reserve_ratio",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.10"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "requests_used >= 0", name="ck_host_budget_state_requests_used"
        ),
        sa.CheckConstraint(
            "requests_ceiling >= 0", name="ck_host_budget_state_requests_ceiling"
        ),
        sa.CheckConstraint(
            "exploration_reserve_ratio >= 0 AND exploration_reserve_ratio < 1",
            name="ck_host_budget_state_exploration_reserve_ratio",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
