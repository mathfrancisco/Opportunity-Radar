"""Record which board and filters a stored validator describes (F51-13).

Revision ID: 20261006_0068
Revises: 20261005_0067
"""

import sqlalchemy as sa
from alembic import op

revision = "20261006_0068"
down_revision = "20261005_0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_checkpoint",
        sa.Column("scope_hash", sa.String(length=64), nullable=True),
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_column("source_checkpoint", "scope_hash", schema="acquisition")
