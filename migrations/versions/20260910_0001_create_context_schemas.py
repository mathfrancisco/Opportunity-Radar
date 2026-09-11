"""Create bounded-context schemas.

Revision ID: 20260910_0001
Revises:
Create Date: 2026-09-10 00:00:00
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260910_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = (
    "profile",
    "company_radar",
    "acquisition",
    "opportunities",
    "matching",
    "crm",
    "platform",
)


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}"')
