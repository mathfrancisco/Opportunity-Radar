"""Let an operator correct a researched ATS record without losing what it said before.

Revision ID: 20260923_0016
Revises: 20260922_0015
Create Date: 2026-09-23 00:00:00

`company_source` was written only by the research importer, so it never needed a version
or a history. Once the interface can register and correct one, two things become true at
the same time: two edits can race, and a corrected external key is exactly what a
reviewer needs to see later when deciding whether the proposed source deserves to be
homologated. The version guards the first; the revision table keeps the second.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260923_0016"
down_revision = "20260922_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_source",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        schema="company_radar",
    )
    op.add_column(
        "company_source",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="company_radar",
    )
    op.add_column(
        "company_source",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="company_radar",
    )
    op.create_table(
        "company_source_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company_radar.company_source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The version the record reached with this change; version 1 is the creation.
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # {"field": {"from": old, "to": new}} for every field this change touched.
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        sa.Column("evidence_note", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "company_source_id",
            "version",
            name="uq_company_source_revision_source_version",
        ),
        schema="company_radar",
    )


def downgrade() -> None:
    op.drop_table("company_source_revision", schema="company_radar")
    op.drop_column("company_source", "updated_at", schema="company_radar")
    op.drop_column("company_source", "created_at", schema="company_radar")
    op.drop_column("company_source", "version", schema="company_radar")
