"""Add `platform.ai_call_record`, one row per Groq call (no PII).

Revision ID: 20260926_0033
Revises: 20260926_0032
Create Date: 2026-09-26 00:00:00

Card F20-19. `matching.match_analysis` records one row per analysis; with retry and
fallback, one analysis can make several calls. This table is the per-call trail that
explains cost, failure and fallback, purely from shape (task, provider, model, attempt,
outcome class, timing, token counts) — never prompt text, the model's answer, or a
credential.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "20260926_0033"
down_revision = "20260926_0032"
branch_labels = None
depends_on = None

SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        "ai_call_record",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("task", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("attempt", sa.SmallInteger, nullable=False),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error_kind", sa.String(32)),
        sa.Column("http_status", sa.SmallInteger),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column("fallback_used", sa.Boolean, nullable=False),
        sa.Column("cache_hit", sa.Boolean, nullable=False),
        sa.Column("prompt_version", sa.String(32)),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_call_record_created_at",
        "ai_call_record",
        ["created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_call_record_model_created_at",
        "ai_call_record",
        ["model", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_call_record_model_created_at", table_name="ai_call_record", schema=SCHEMA
    )
    op.drop_index("ix_ai_call_record_created_at", table_name="ai_call_record", schema=SCHEMA)
    op.drop_table("ai_call_record", schema=SCHEMA)
