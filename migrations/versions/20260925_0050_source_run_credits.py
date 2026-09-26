"""Persist provider credits spent per source run.

Revision ID: 20260925_0050
Revises: 20260925_0029
Create Date: 2026-09-25 14:00:00

Card F20-43 follow-up. `SourceRun.credits_used` existed in the domain
(`opportunity_radar.acquisition.domain.SourceRun.credits_used`) but had no column on
`SourceRunModel`, so `record_credits()` was silently lost on every flush. This adds
`source_run.credits_used`, not null, defaulting to 0 for pre-existing rows (no run before
this revision spent anything we can recover), with its own check constraint — kept
separate from `ck_source_run_counters`, which only covers HTTP counters, because credits
are a different unit (provider spend, not HTTP calls).
"""

import sqlalchemy as sa
from alembic import op

revision = "20260925_0050"
down_revision = "20260925_0029"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column(
            "credits_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_source_run_credits_used",
        "source_run",
        "credits_used >= 0",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_source_run_credits_used",
        "source_run",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("source_run", "credits_used", schema=SCHEMA)
