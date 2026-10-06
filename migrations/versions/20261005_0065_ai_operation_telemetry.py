"""Persist logical AI operations and correlate provider attempts.

Revision ID: 20261005_0065
Revises: 20261005_0064
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "20261005_0065"
down_revision = "20261005_0064"
branch_labels = None
depends_on = None

SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        "ai_operation_record",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("task", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("error_kind", sa.String(32)),
        sa.Column("prompt_version", sa.String(32)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_operation_record_started_at",
        "ai_operation_record",
        ["started_at"],
        schema=SCHEMA,
    )
    op.create_table(
        "ai_suggestion_defer",
        sa.Column("opportunity_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("route_hash", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.opportunity.id"], ondelete="CASCADE",
            name="fk_ai_suggestion_defer_opportunity",
        ),
        sa.PrimaryKeyConstraint(
            "opportunity_id", "content_hash", "prompt_version", "route_hash",
            name="pk_ai_suggestion_defer",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_suggestion_defer_next_attempt", "ai_suggestion_defer",
        ["next_attempt_at"], schema=SCHEMA,
    )
    op.add_column(
        "ai_call_record",
        sa.Column("operation_id", PGUUID(as_uuid=True)),
        schema=SCHEMA,
    )
    op.add_column(
        "ai_call_record", sa.Column("operation_ordinal", sa.Integer), schema=SCHEMA
    )
    op.add_column(
        "ai_call_record", sa.Column("transport_started", sa.Boolean), schema=SCHEMA
    )
    op.add_column(
        "ai_call_record",
        sa.Column(
            "attempt_state", sa.String(16), nullable=False, server_default="completed"
        ),
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        "uq_ai_call_record_operation_ordinal",
        "ai_call_record",
        ["operation_id", "operation_ordinal"],
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_ai_call_record_operation_id",
        "ai_call_record",
        "ai_operation_record",
        ["operation_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_call_record_operation_id",
        "ai_call_record",
        ["operation_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_suggestion_defer_next_attempt", table_name="ai_suggestion_defer",
        schema=SCHEMA,
    )
    op.drop_table("ai_suggestion_defer", schema=SCHEMA)
    op.drop_constraint(
        "uq_ai_call_record_operation_ordinal", "ai_call_record", schema=SCHEMA,
        type_="unique",
    )
    op.drop_index("ix_ai_call_record_operation_id", table_name="ai_call_record", schema=SCHEMA)
    op.drop_constraint(
        "fk_ai_call_record_operation_id", "ai_call_record", schema=SCHEMA, type_="foreignkey"
    )
    op.drop_column("ai_call_record", "operation_id", schema=SCHEMA)
    op.drop_column("ai_call_record", "operation_ordinal", schema=SCHEMA)
    op.drop_column("ai_call_record", "transport_started", schema=SCHEMA)
    op.drop_column("ai_call_record", "attempt_state", schema=SCHEMA)
    op.drop_index(
        "ix_ai_operation_record_started_at",
        table_name="ai_operation_record",
        schema=SCHEMA,
    )
    op.drop_table("ai_operation_record", schema=SCHEMA)
