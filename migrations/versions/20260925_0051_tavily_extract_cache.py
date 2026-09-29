"""Cache table for Tavily `/extract` results, keyed by canonical URL hash.

Revision ID: 20260925_0051
Revises: 20260925_0050
Create Date: 2026-09-25 14:30:00

Card F20-45. `acquisition.tavily_extract_cache.url_hash` is a sha256 of
`canonicalize_url(url)` (F20-44) so the same URL — differing only in query string,
fragment, or host case — never lands in two rows. `expires_at` makes an expired row a
miss, not an error: extraction is retried, not refused.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260925_0051"
down_revision = "20260925_0050"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "tavily_extract_cache"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("url_hash", sa.String(64), primary_key=True),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("raw_content", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success', 'failed')",
            name="ck_tavily_extract_cache_status",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
