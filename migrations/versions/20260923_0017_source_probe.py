"""Record every live test of a source's collector.

Revision ID: 20260923_0017
Revises: 20260923_0016
Create Date: 2026-09-23 00:00:00

Confirmed evidence used to be written only by the enable script, which kept its proof in
the source configuration and nothing about the attempts that failed. Once the interface
can ask for the same test, each attempt becomes a row: the confirmed status points at the
probe that earned it, and a spacing rule between probes can be checked against history
instead of trusted to the button.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260923_0017"
down_revision = "20260923_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_probe",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("detail", sa.Text()),
        sa.Column(
            "evidence_recorded", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.CheckConstraint(
            "requested_by IN ('interface', 'script')",
            name="ck_source_probe_requested_by",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'PASSED', 'FAILED')",
            name="ck_source_probe_status",
        ),
        schema="acquisition",
    )
    op.create_index(
        "ix_source_probe_source_started",
        "source_probe",
        ["source_definition_id", "started_at"],
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_probe_source_started", table_name="source_probe", schema="acquisition"
    )
    op.drop_table("source_probe", schema="acquisition")
