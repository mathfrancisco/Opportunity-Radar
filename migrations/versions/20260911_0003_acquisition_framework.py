"""Create the Acquisition framework tables.

Revision ID: 20260911_0003
Revises: 20260910_0002
Create Date: 2026-09-11 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260911_0003"
down_revision = "20260910_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_company_normalized_name",
        "company",
        ["normalized_name"],
        schema="company_radar",
    )
    op.add_column(
        "company_source",
        sa.Column("evidence_note", sa.Text()),
        schema="company_radar",
    )
    op.create_table(
        "source_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_radar.company_source.id", ondelete="SET NULL"),
        ),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule", sa.String(255)),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "rate_limit_policy",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "configuration",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "evidence_status",
            sa.String(32),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "terms_reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "collector_local_tested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("last_health_status", sa.String(32)),
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("priority >= 0", name="ck_source_definition_priority"),
        sa.CheckConstraint(
            "evidence_status IN ('unverified', 'confirmed', 'ats_identified', "
            "'careers_page', 'dynamic_review', 'redirect_review', 'access_pending')",
            name="ck_source_definition_evidence_status",
        ),
        sa.UniqueConstraint(
            "source_type",
            "name",
            name="uq_source_definition_type_name",
        ),
        schema="acquisition",
    )
    op.create_index(
        "ix_source_definition_company_source",
        "source_definition",
        ["company_source_id"],
        schema="acquisition",
    )

    op.create_table(
        "source_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_persisted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_invalid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_summary", sa.Text()),
        sa.Column("checkpoint_before", sa.Text()),
        sa.Column("checkpoint_after", sa.Text()),
        sa.Column("correlation_id", sa.String(255)),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'PARTIAL', "
            "'FAILED', 'CANCELLED')",
            name="ck_source_run_status",
        ),
        sa.CheckConstraint(
            "items_seen >= 0 AND items_persisted >= 0 AND items_skipped >= 0 "
            "AND items_invalid >= 0 AND http_requests >= 0 AND retry_count >= 0",
            name="ck_source_run_counters",
        ),
        schema="acquisition",
    )
    op.create_index(
        "ix_source_run_source_started",
        "source_run",
        ["source_definition_id", "started_at"],
        schema="acquisition",
    )
    op.create_index(
        "uq_source_run_active",
        "source_run",
        ["source_definition_id"],
        unique=True,
        schema="acquisition",
        postgresql_where=sa.text("status IN ('PENDING', 'RUNNING')"),
    )

    op.create_table(
        "raw_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(512)),
        sa.Column("canonical_url", sa.String(2048)),
        sa.Column("identity_key", sa.String(2048), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(255)),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("parser_version", sa.String(128)),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.UniqueConstraint(
            "source_definition_id",
            "identity_key",
            "payload_hash",
            name="uq_raw_item_source_identity_hash",
        ),
        schema="acquisition",
    )
    op.create_index(
        "ix_raw_item_source_run",
        "raw_item",
        ["source_run_id"],
        schema="acquisition",
    )

    op.create_table(
        "source_checkpoint",
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "checkpoint_type",
            sa.String(32),
            nullable=False,
            server_default="cursor",
        ),
        sa.Column("cursor", sa.Text()),
        sa.Column("updated_since", sa.DateTime(timezone=True)),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        sa.Column(
            "promoted_by_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_run.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "promoted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_table("source_checkpoint", schema="acquisition")
    op.drop_index(
        "ix_raw_item_source_run",
        table_name="raw_item",
        schema="acquisition",
    )
    op.drop_table("raw_item", schema="acquisition")
    op.drop_index(
        "uq_source_run_active",
        table_name="source_run",
        schema="acquisition",
    )
    op.drop_index(
        "ix_source_run_source_started",
        table_name="source_run",
        schema="acquisition",
    )
    op.drop_table("source_run", schema="acquisition")
    op.drop_index(
        "ix_source_definition_company_source",
        table_name="source_definition",
        schema="acquisition",
    )
    op.drop_table("source_definition", schema="acquisition")
    op.drop_column("company_source", "evidence_note", schema="company_radar")
    op.drop_constraint(
        "uq_company_normalized_name",
        "company",
        schema="company_radar",
        type_="unique",
    )
