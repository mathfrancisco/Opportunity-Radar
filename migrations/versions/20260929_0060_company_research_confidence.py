"""Separate research maturity from company priority.

Revision ID: 20260929_0060
Revises: 20260929_0058
Create Date: 2026-09-29 00:00:00

Card F48-14. `company.priority` was filled from how mature the research catalogue was
(`low` unless an ATS or JSON API was identified). The maturity now lives in its own column,
backfilled from the current priority, which is what the importer wrote. Priorities are not
rewritten here: `scripts/reclassify_company_priority.py` does that, with a dry run.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260929_0060"
down_revision = "20260929_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company",
        sa.Column(
            "research_confidence",
            sa.String(20),
            nullable=False,
            server_default="normal",
        ),
        schema="company_radar",
    )
    op.execute(
        "UPDATE company_radar.company SET research_confidence = priority "
        "WHERE priority IN ('low', 'normal', 'high')"
    )


def downgrade() -> None:
    op.drop_column("company", "research_confidence", schema="company_radar")
