"""Store one embedding per opportunity, with what produced it.

Revision ID: 20260925_0024
Revises: 20260925_0023
Create Date: 2026-09-25 12:00:00

Card F16-09. The vector is derived data: the job can rebuild every row, so the table is
not evidence and the downgrade loses nothing that matters. Each row names the model, the
version of the text recipe and the opportunity version it was computed from, because a
consumer must only compare vectors of the same space and of the current posting.

`CREATE EXTENSION` needs a superuser (or a trusted extension). The compose and CI users
are superusers; an installation outside compose has to create the extension once as one.
The `vector` column and the HNSW index go through SQL because Alembic does not know the
type, and the migration must not depend on application code that may change later.

The failure table keeps the per-item error of the last attempt, so the worker can cool an
item down, or give up on it, without holding back the rest of its batch.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260925_0024"
down_revision = "20260925_0023"
branch_labels = None
depends_on = None

_SCHEMA = "opportunities"
#: Tied to `OLLAMA_EMBEDDING_DIMENSIONS`; another size needs a new migration and a reindex.
_DIMENSIONS = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "opportunity_embedding",
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.opportunity.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("text_version", sa.String(length=64), nullable=False),
        sa.Column("text_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "content_version > 0", name="ck_opportunity_embedding_content_version"
        ),
        sa.CheckConstraint(
            "char_length(text_hash) = 64", name="ck_opportunity_embedding_text_hash"
        ),
        sa.CheckConstraint("dimensions > 0", name="ck_opportunity_embedding_dimensions"),
        schema=_SCHEMA,
    )
    # The table is new and empty, so NOT NULL needs no backfill.
    op.execute(
        f"ALTER TABLE {_SCHEMA}.opportunity_embedding "
        f"ADD COLUMN embedding vector({_DIMENSIONS}) NOT NULL"
    )
    # Cosine for clarity: `/api/embed` returns unit vectors, so it orders like the inner
    # product would.
    op.execute(
        "CREATE INDEX ix_opportunity_embedding_hnsw "
        f"ON {_SCHEMA}.opportunity_embedding USING hnsw (embedding vector_cosine_ops)"
    )
    op.create_table(
        "opportunity_embedding_failure",
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{_SCHEMA}.opportunity.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("text_version", sa.String(length=64), nullable=False),
        sa.Column("failure_code", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "first_failed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("attempts > 0", name="ck_opportunity_embedding_failure_attempts"),
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("opportunity_embedding_failure", schema=_SCHEMA)
    op.drop_table("opportunity_embedding", schema=_SCHEMA)
    op.execute("DROP EXTENSION IF EXISTS vector")
