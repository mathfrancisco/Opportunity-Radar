"""Add `platform.ai_quota_usage`, the persistent per-model quota counter.

Revision ID: 20260926_0030
Revises: 20260925_0051
Create Date: 2026-09-26 00:00:00

Card F20-12. The API and the worker can both call Groq, and the worker can restart;
an in-memory counter would double-spend the shared quota or forget the day's usage. One
row per `(model, window_kind, window_start)` lets `QuotaGuard.reserve` do a single
atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE ... RETURNING` per window instead of
a read-then-write that a concurrent caller could race.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0030"
down_revision = "20260925_0051"
branch_labels = None
depends_on = None

SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        "ai_quota_usage",
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("window_kind", sa.String(8), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requests", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("remaining_requests_reported", sa.Integer),
        sa.Column("remaining_tokens_reported", sa.Integer),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("model", "window_kind", "window_start"),
        sa.CheckConstraint(
            "window_kind IN ('minute', 'day')", name="ck_ai_quota_usage_window_kind"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("ai_quota_usage", schema=SCHEMA)
