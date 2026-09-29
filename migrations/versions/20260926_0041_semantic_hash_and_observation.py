"""Add F20-39 semantic evidence and per-run presence observations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0041"
down_revision = "20260926_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("raw_item", sa.Column("semantic_hash", sa.String(64)), schema="acquisition")
    op.add_column(
        "raw_item", sa.Column("semantic_hash_version", sa.String(32)), schema="acquisition"
    )
    op.create_table(
        "source_occurrence_observation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_occurrence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.source_occurrence.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "source_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.raw_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("content_hash_matched", sa.Boolean(), nullable=False),
        sa.UniqueConstraint(
            "raw_item_id", "source_run_id", name="uq_source_occurrence_observation_raw_item_run"
        ),
        schema="opportunities",
    )
    op.create_index(
        "ix_source_occurrence_observation_raw_item",
        "source_occurrence_observation",
        ["raw_item_id"],
        schema="opportunities",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_occurrence_observation_raw_item",
        table_name="source_occurrence_observation",
        schema="opportunities",
    )
    op.drop_table("source_occurrence_observation", schema="opportunities")
    op.drop_column("raw_item", "semantic_hash_version", schema="acquisition")
    op.drop_column("raw_item", "semantic_hash", schema="acquisition")
