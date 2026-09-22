"""Persist observed execution state for functional worker jobs."""

import sqlalchemy as sa
from alembic import op

revision = "20260922_0012"
down_revision = "20260921_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_job_state",
        sa.Column("job_name", sa.String(length=64), primary_key=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("last_duration_ms", sa.Integer()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_correlation_id", sa.String(length=64), nullable=False),
        sa.Column("last_error", sa.Text()),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("worker_job_state", schema="platform")
