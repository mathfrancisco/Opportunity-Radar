"""Run telemetry for the collection-gap alarm and a short history of worker passes.

Revision ID: 20260929_0055
Revises: 20260929_0054
Create Date: 2026-09-29 00:00:00

Card F48-07. `source_run.bytes_received` and `newest_item_age_seconds` are nullable: a run
recorded before this revision, or one that saw no dated item, has no value, and zero would
claim otherwise. `platform.worker_pass_history` keeps one row per pass of a worker job
(duration, outcome and, for the collection job, how many sources were DUE); the worker
prunes it, so it never grows without bound.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260929_0055"
down_revision = "20260929_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column("bytes_received", sa.BigInteger(), nullable=True),
        schema="acquisition",
    )
    op.add_column(
        "source_run",
        sa.Column("newest_item_age_seconds", sa.Integer(), nullable=True),
        schema="acquisition",
    )
    op.create_check_constraint(
        "ck_source_run_telemetry",
        "source_run",
        "(bytes_received IS NULL OR bytes_received >= 0) "
        "AND (newest_item_age_seconds IS NULL OR newest_item_age_seconds >= 0)",
        schema="acquisition",
    )
    op.create_table(
        "worker_pass_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_name", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("success", sa.Boolean()),
        sa.Column("due_sources", sa.Integer()),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="platform",
    )
    op.create_index(
        "ix_worker_pass_history_job_started",
        "worker_pass_history",
        ["job_name", "started_at"],
        schema="platform",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worker_pass_history_job_started",
        table_name="worker_pass_history",
        schema="platform",
    )
    op.drop_table("worker_pass_history", schema="platform")
    op.drop_constraint(
        "ck_source_run_telemetry", "source_run", schema="acquisition", type_="check"
    )
    op.drop_column("source_run", "newest_item_age_seconds", schema="acquisition")
    op.drop_column("source_run", "bytes_received", schema="acquisition")
