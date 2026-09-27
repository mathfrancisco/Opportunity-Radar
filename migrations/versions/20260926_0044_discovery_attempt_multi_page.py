"""Add multi-page discovery columns to `company_radar.discovery_attempt`.

Revision ID: 20260926_0044
Revises: 20260926_0043
Create Date: 2026-09-27 00:00:00

Card F20-36. `discovery_attempt` (F20-27, migration 20260926_0032) recorded one
single-request GET per attempt. Limited discovery follows a small, budgeted crawl
(robots.txt, sitemap(s), a handful of same-allowlist pages) and needs to record why it
stopped, how much it examined, and when it may retry — without breaking the F20-27 rows
that never had any of this (`server_default` keeps existing rows valid).

Numbering note: the card's own text suggested `20260926_0040`, written before F20-38
(host budget) claimed that number. The actual head at the time this card landed was
`20260926_0043`; this migration follows it. If another Bloco D/C card lands first with a
lower free number, renumber this file on merge rather than fight over the slot.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0044"
down_revision = "20260926_0043"
branch_labels = None
depends_on = None

SCHEMA = "company_radar"
TABLE = "discovery_attempt"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("stop_reason", sa.String(32)), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("urls_examined", sa.Integer()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("http_requests", sa.Integer()), schema=SCHEMA)
    op.add_column(
        TABLE, sa.Column("next_attempt_at", sa.DateTime(timezone=True)), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column(TABLE, "next_attempt_at", schema=SCHEMA)
    op.drop_column(TABLE, "http_requests", schema=SCHEMA)
    op.drop_column(TABLE, "urls_examined", schema=SCHEMA)
    op.drop_column(TABLE, "stop_reason", schema=SCHEMA)
