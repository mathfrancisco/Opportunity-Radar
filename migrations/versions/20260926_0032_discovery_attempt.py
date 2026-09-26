"""Add `company_radar.discovery_attempt`.

Revision ID: 20260926_0032
Revises: 20260926_0031
Create Date: 2026-09-26 00:00:00

Card F20-27. One row per `discover_ats` GET against a company's careers page, whether or
not it found an ATS, so a company is never re-checked before the revisit interval
(default 30 days). Discovery never creates a `SourceRun` or `RawItem`: this is research,
not collection.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260926_0032"
down_revision = "20260926_0031"
branch_labels = None
depends_on = None

SCHEMA = "company_radar"


def upgrade() -> None:
    op.create_table(
        "discovery_attempt",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.company.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked_url", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("ats_found", sa.String(50)),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_discovery_attempt_company_attempted",
        "discovery_attempt",
        ["company_id", "attempted_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discovery_attempt_company_attempted",
        table_name="discovery_attempt",
        schema=SCHEMA,
    )
    op.drop_table("discovery_attempt", schema=SCHEMA)
