"""Persist source HTTP throttling and rate-limit observability.

Revision ID: 20260913_0004
Revises: 20260911_0003
Create Date: 2026-09-13 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260913_0004"
down_revision = "20260911_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_definition",
        sa.Column("last_http_attempt_at", sa.DateTime(timezone=True)),
        schema="acquisition",
    )
    op.add_column(
        "source_run",
        sa.Column(
            "rate_limit_events",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        schema="acquisition",
    )
    op.drop_constraint(
        "ck_source_run_counters",
        "source_run",
        schema="acquisition",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_run_counters",
        "source_run",
        "items_seen >= 0 AND items_persisted >= 0 AND items_skipped >= 0 "
        "AND items_invalid >= 0 AND http_requests >= 0 AND retry_count >= 0 "
        "AND rate_limit_events >= 0",
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_source_run_counters",
        "source_run",
        schema="acquisition",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_run_counters",
        "source_run",
        "items_seen >= 0 AND items_persisted >= 0 AND items_skipped >= 0 "
        "AND items_invalid >= 0 AND http_requests >= 0 AND retry_count >= 0",
        schema="acquisition",
    )
    op.drop_column("source_run", "rate_limit_events", schema="acquisition")
    op.drop_column(
        "source_definition", "last_http_attempt_at", schema="acquisition"
    )
