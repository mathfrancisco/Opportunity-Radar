"""Record what each analysis sent and was keyed by.

Revision ID: 20260925_0023
Revises: 20260925_0020
Create Date: 2026-09-25 12:00:00

Cards F16-05, F16-07, F16-08 and F16-11. `analysis-key-v2` covers the payload actually
sent, the prompt's content, the model and every option that changes the answer; the
row keeps the payload, the inference settings, the retrieved decisions and the token
budget alongside it, so an answer can be audited against its own input. All nullable:
rows written before carry the pre-v2 key and `key_version` NULL, and stay readable.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0023"
down_revision = "20260925_0020"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("key_version", sa.String(length=32)),
    ("payload_hash", sa.String(length=64)),
    ("payload", postgresql.JSONB()),
    ("inference", postgresql.JSONB()),
    ("context_refs", postgresql.JSONB()),
    ("prompt_budget", sa.Integer()),
)


def upgrade() -> None:
    for name, column_type in _COLUMNS:
        op.add_column("match_analysis", sa.Column(name, column_type), schema="matching")
    # The persistent cache looks rows up by key and identity version together.
    op.create_index(
        "ix_match_analysis_key_version",
        "match_analysis",
        ["cache_key", "key_version"],
        schema="matching",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_match_analysis_key_version", table_name="match_analysis", schema="matching"
    )
    for name, _ in reversed(_COLUMNS):
        op.drop_column("match_analysis", name, schema="matching")
