"""Persist source alert incidents so restarts cannot duplicate a message.

Revision ID: 20260922_0013
Revises: 20260922_0012
Create Date: 2026-09-22 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260922_0013"
down_revision = "20260922_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_alert_incident",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "opened_by_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_run.id", ondelete="SET NULL"),
        ),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("error_summary", sa.Text()),
        sa.Column("alert_sent_at", sa.DateTime(timezone=True)),
        sa.Column(
            "alert_delivery",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column(
            "recovered_by_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_run.id", ondelete="SET NULL"),
        ),
        sa.Column("recovery_sent_at", sa.DateTime(timezone=True)),
        sa.Column("recovery_delivery", sa.String(length=16)),
        sa.Column("correlation_id", sa.String(length=255)),
        sa.CheckConstraint(
            "alert_delivery IN ('PENDING', 'WEBHOOK', 'LOG_ONLY', 'FAILED')",
            name="ck_source_alert_incident_delivery",
        ),
        sa.CheckConstraint(
            "recovery_delivery IS NULL OR recovery_delivery IN "
            "('WEBHOOK', 'LOG_ONLY', 'FAILED')",
            name="ck_source_alert_incident_recovery_delivery",
        ),
        sa.CheckConstraint(
            "consecutive_failures > 0", name="ck_source_alert_incident_failures"
        ),
        schema="acquisition",
    )
    # One open incident per source is what makes the alert deduplicated by episode.
    op.create_index(
        "uq_source_alert_incident_open",
        "source_alert_incident",
        ["source_definition_id"],
        unique=True,
        schema="acquisition",
        postgresql_where=sa.text("recovered_at IS NULL"),
    )
    op.create_index(
        "ix_source_alert_incident_source_opened",
        "source_alert_incident",
        ["source_definition_id", "opened_at"],
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_alert_incident_source_opened",
        table_name="source_alert_incident",
        schema="acquisition",
    )
    op.drop_index(
        "uq_source_alert_incident_open",
        table_name="source_alert_incident",
        schema="acquisition",
    )
    op.drop_table("source_alert_incident", schema="acquisition")
