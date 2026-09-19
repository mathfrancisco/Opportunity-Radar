"""Track candidacies and their immutable stage history.

Revision ID: 20260918_0009
Revises: 20260917_0008
Create Date: 2026-09-18 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260918_0009"
down_revision = "20260917_0008"
branch_labels = None
depends_on = None

STAGES = (
    "'INTERESTED', 'APPLIED', 'SCREENING', 'INTERVIEW', 'TECHNICAL', 'FINAL', "
    "'OFFER', 'REJECTED', 'WITHDRAWN', 'CLOSED'"
)
OUTCOMES = "'REJECTED', 'WITHDRAWN', 'CLOSED'"


def upgrade() -> None:
    op.create_table(
        "application_process",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("current_stage", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("outcome", sa.String(16)),
        sa.Column("next_action", sa.String(500)),
        sa.Column("next_action_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(f"current_stage IN ({STAGES})", name="ck_application_stage"),
        sa.CheckConstraint("status IN ('ACTIVE', 'CLOSED')", name="ck_application_status"),
        sa.CheckConstraint(
            f"outcome IS NULL OR outcome IN ({OUTCOMES})", name="ck_application_outcome"
        ),
        sa.CheckConstraint(
            "(status = 'CLOSED') = (closed_at IS NOT NULL)",
            name="ck_application_closed_at",
        ),
        sa.CheckConstraint(
            "(status = 'CLOSED') = (outcome IS NOT NULL)",
            name="ck_application_closed_outcome",
        ),
        sa.CheckConstraint("version > 0", name="ck_application_version"),
        schema="crm",
    )
    op.create_index(
        "uq_application_active",
        "application_process",
        ["opportunity_id", "profile_version_id"],
        unique=True,
        schema="crm",
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_application_stage_updated",
        "application_process",
        ["current_stage", "updated_at"],
        schema="crm",
    )
    op.create_index(
        "ix_application_next_action_at",
        "application_process",
        ["next_action_at"],
        schema="crm",
    )
    op.create_table(
        "stage_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("crm.application_process.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_stage", sa.String(16)),
        sa.Column("to_stage", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(64)),
        sa.Column("source", sa.String(16), nullable=False, server_default="MANUAL"),
        sa.Column("notes", sa.Text()),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(f"to_stage IN ({STAGES})", name="ck_stage_history_to_stage"),
        sa.CheckConstraint(
            f"from_stage IS NULL OR from_stage IN ({STAGES})",
            name="ck_stage_history_from_stage",
        ),
        sa.CheckConstraint(
            "from_stage IS NULL OR from_stage <> to_stage",
            name="ck_stage_history_moves",
        ),
        sa.CheckConstraint(
            "source IN ('MANUAL', 'SYSTEM')", name="ck_stage_history_source"
        ),
        schema="crm",
    )
    op.create_index(
        "ix_stage_history_application",
        "stage_history",
        ["application_id", "occurred_at"],
        schema="crm",
    )
    # History explains how the application reached its stage. Editing an entry would let
    # that explanation drift from what actually happened, so only inserts are allowed.
    op.execute(
        """
        CREATE FUNCTION crm.prevent_stage_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'stage history is immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_stage_history_immutable
        BEFORE UPDATE ON crm.stage_history
        FOR EACH ROW EXECUTE FUNCTION crm.prevent_stage_history_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_stage_history_immutable ON crm.stage_history"
    )
    op.execute("DROP FUNCTION IF EXISTS crm.prevent_stage_history_mutation()")
    op.drop_index(
        "ix_stage_history_application", table_name="stage_history", schema="crm"
    )
    op.drop_table("stage_history", schema="crm")
    op.drop_index(
        "ix_application_next_action_at", table_name="application_process", schema="crm"
    )
    op.drop_index(
        "ix_application_stage_updated", table_name="application_process", schema="crm"
    )
    op.drop_index("uq_application_active", table_name="application_process", schema="crm")
    op.drop_table("application_process", schema="crm")
