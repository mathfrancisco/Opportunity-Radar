"""Run completeness, its announced-vs-seen counter, and an occurrence's last complete run.

Revision ID: 20260925_0025
Revises: 20260925_0024
Create Date: 2026-09-25 13:00:00

Card F17-07. `source_run.items_announced` is what the source's own API said the board
holds, when it says so; `source_run.complete` is whether that run read the whole board
(SUCCEEDED, unbounded by max_items, and items_seen at or past items_announced when a
total is known). `source_occurrence.last_seen_run_id` is the run that last normalized the
occurrence, which is what closure compares against the two most recent complete runs of
its source. `opportunity.closure_evidence` records the run ids behind an automatic close
or reopen.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0025"
down_revision = "20260925_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column("items_announced", sa.Integer()),
        schema="acquisition",
    )
    op.add_column(
        "source_run",
        sa.Column(
            "complete",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="acquisition",
    )
    op.add_column(
        "source_occurrence",
        sa.Column("last_seen_run_id", postgresql.UUID(as_uuid=True)),
        schema="opportunities",
    )
    op.create_foreign_key(
        "fk_source_occurrence_last_seen_run",
        "source_occurrence",
        "source_run",
        ["last_seen_run_id"],
        ["id"],
        source_schema="opportunities",
        referent_schema="acquisition",
        ondelete="SET NULL",
    )
    op.add_column(
        "opportunity",
        sa.Column("closure_evidence", postgresql.JSONB()),
        schema="opportunities",
    )


def downgrade() -> None:
    op.drop_column("opportunity", "closure_evidence", schema="opportunities")
    op.drop_constraint(
        "fk_source_occurrence_last_seen_run",
        "source_occurrence",
        schema="opportunities",
        type_="foreignkey",
    )
    op.drop_column("source_occurrence", "last_seen_run_id", schema="opportunities")
    op.drop_column("source_run", "complete", schema="acquisition")
    op.drop_column("source_run", "items_announced", schema="acquisition")
