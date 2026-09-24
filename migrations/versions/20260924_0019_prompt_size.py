"""Record the prompt's size and its token estimate before sending.

Revision ID: 20260924_0019
Revises: 20260924_0018
Create Date: 2026-09-24 12:00:00

Card F16-05. The prompt is measured before it is sent, so the radar can refuse one the
server would truncate. Keeping the size and the estimate next to the real
`prompt_tokens` is what calibrates the characters-per-token ratio. Nullable, like the
cost columns: rows written earlier were never measured.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260924_0019"
down_revision = "20260924_0018"
branch_labels = None
depends_on = None

_PROMPT_SIZE = ("prompt_chars", "prompt_tokens_estimate")


def upgrade() -> None:
    for column in _PROMPT_SIZE:
        op.add_column("match_analysis", sa.Column(column, sa.Integer()), schema="matching")


def downgrade() -> None:
    for column in reversed(_PROMPT_SIZE):
        op.drop_column("match_analysis", column, schema="matching")
