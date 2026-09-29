"""Classify each opportunity's area (`role-family-v1`) with its evidence.

Revision ID: 20260925_0027
Revises: 20260925_0026
Create Date: 2026-09-25 12:00:00

Card F17-02. `role_family` is a filter, never a matching factor. Existing rows are filled
with `UNKNOWN` and a `NULL` version; the retroactive job (`scripts/reclassify_role_families.py`)
classifies them from the title and the department the ATS declared.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0027"
down_revision = "20260925_0026"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"

_ROLE_FAMILIES = (
    "SOFTWARE_ENGINEERING",
    "DATA",
    "INFRASTRUCTURE",
    "SECURITY",
    "QA",
    "PRODUCT",
    "DESIGN",
    "SALES",
    "MARKETING",
    "OPERATIONS",
    "PEOPLE",
    "FINANCE",
    "LEGAL",
    "SUPPORT",
    "OTHER",
    "UNKNOWN",
)


def upgrade() -> None:
    op.add_column(
        "opportunity",
        sa.Column(
            "role_family",
            sa.String(32),
            nullable=False,
            server_default="UNKNOWN",
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "opportunity",
        sa.Column("role_family_evidence", postgresql.JSONB(astext_type=sa.Text())),
        schema=SCHEMA,
    )
    op.add_column(
        "opportunity",
        sa.Column("role_family_version", sa.String(32)),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_opportunity_role_family",
        "opportunity",
        "role_family IN (" + ", ".join(f"'{value}'" for value in _ROLE_FAMILIES) + ")",
        schema=SCHEMA,
    )
    op.create_index(
        "ix_opportunity_role_family",
        "opportunity",
        ["role_family"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_role_family", table_name="opportunity", schema=SCHEMA)
    op.drop_constraint(
        "ck_opportunity_role_family", "opportunity", schema=SCHEMA, type_="check"
    )
    op.drop_column("opportunity", "role_family_version", schema=SCHEMA)
    op.drop_column("opportunity", "role_family_evidence", schema=SCHEMA)
    op.drop_column("opportunity", "role_family", schema=SCHEMA)
