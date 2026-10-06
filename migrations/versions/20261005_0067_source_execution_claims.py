"""Add source-scoped execution leases and fencing generations.

Revision ID: 20261005_0067
Revises: 20261005_0066
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261005_0067"
down_revision = "20261005_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_run",
        sa.Column("fencing_token", sa.BigInteger(), nullable=True),
        schema="acquisition",
    )
    op.create_table(
        "source_execution_claim",
        sa.Column("source_definition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("fencing_token >= 0", name="ck_source_execution_claim_token"),
        sa.CheckConstraint("task_key <> ''", name="ck_source_execution_claim_task"),
        sa.ForeignKeyConstraint(
            ["source_definition_id"], ["acquisition.source_definition.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["acquisition.source_run.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("source_definition_id", "task_key"),
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_table("source_execution_claim", schema="acquisition")
    op.drop_column("source_run", "fencing_token", schema="acquisition")
