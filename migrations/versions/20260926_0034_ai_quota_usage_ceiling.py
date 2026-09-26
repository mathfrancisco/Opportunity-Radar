"""Add absolute provider-reported ceilings to `platform.ai_quota_usage`.

Revision ID: 20260926_0034
Revises: 20260926_0033
Create Date: 2026-09-26 00:00:00

Card F20-12. Persist the lowest observed per-window absolute request and token limits.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0034"
down_revision = "20260926_0033"
branch_labels = None
depends_on = None

SCHEMA = "platform"


def upgrade() -> None:
    op.add_column("ai_quota_usage", sa.Column("requests_ceiling", sa.Integer), schema=SCHEMA)
    op.add_column("ai_quota_usage", sa.Column("tokens_ceiling", sa.Integer), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("ai_quota_usage", "tokens_ceiling", schema=SCHEMA)
    op.drop_column("ai_quota_usage", "requests_ceiling", schema=SCHEMA)
