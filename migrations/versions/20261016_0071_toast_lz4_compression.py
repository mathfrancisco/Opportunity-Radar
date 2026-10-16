"""Compress large text and jsonb columns with lz4 (R55-E6).

Revision ID: 20261016_0071
Revises: 20261008_0069

REBASE NOTE: the ingestion PR (r55/e1-e3-ingest) adds 20261016_0070. When it lands on main,
change `down_revision` below to "20261016_0070" so Alembic keeps a single head.

`ALTER COLUMN ... SET COMPRESSION lz4` (PostgreSQL 14+) only affects values written after
it; existing rows keep their pglz-compressed form until they are rewritten, so the saving
builds up as the 7-day window turns over. It takes a brief ACCESS EXCLUSIVE lock and does not
rewrite the table. Servers older than 14, or built without lz4, are skipped with a NOTICE:
compression is an optimisation, never a reason for the deployment to fail.

Downgrade restores the server default (`pglz` via DEFAULT), also for new values only.
"""

from __future__ import annotations

from alembic import op

revision = "20261016_0071"
down_revision = "20261008_0069"
branch_labels = None
depends_on = None

#: (schema, table, column) of the columns that hold large documents.
_COLUMNS = (
    ("acquisition", "raw_item_payload", "payload"),
    ("opportunities", "opportunity", "description"),
)


def _set_compression(method: str) -> None:
    for schema, table, column in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF current_setting('server_version_num')::int >= 140000 THEN
                    ALTER TABLE {schema}.{table} ALTER COLUMN {column} SET COMPRESSION {method};
                ELSE
                    RAISE NOTICE 'skip {schema}.{table}.{column}: needs PostgreSQL 14+';
                END IF;
            EXCEPTION WHEN feature_not_supported OR invalid_parameter_value THEN
                RAISE NOTICE 'skip {schema}.{table}.{column}: {method} unavailable';
            END
            $$
            """
        )


def upgrade() -> None:
    _set_compression("lz4")


def downgrade() -> None:
    _set_compression("DEFAULT")
