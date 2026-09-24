"""Record what every analysis cost.

Revision ID: 20260924_0018
Revises: 20260923_0017
Create Date: 2026-09-24 00:00:00

Card F16-03. The Ollama response carries durations and token counts that were being
discarded. The columns are nullable because every row written before this revision has no
measurement, and an unknown cost must read as unknown, not as a free call.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260924_0018"
down_revision = "20260923_0017"
branch_labels = None
depends_on = None

_ANALYSIS_COST = (
    "total_ms",
    "load_ms",
    "prompt_tokens",
    "prompt_eval_ms",
    "output_tokens",
    "eval_ms",
)


def upgrade() -> None:
    for column in _ANALYSIS_COST:
        op.add_column("match_analysis", sa.Column(column, sa.Integer()), schema="matching")


def downgrade() -> None:
    for column in reversed(_ANALYSIS_COST):
        op.drop_column("match_analysis", column, schema="matching")
