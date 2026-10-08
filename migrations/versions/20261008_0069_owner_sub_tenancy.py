"""Add immutable Clerk ownership to the personal-data roots.

Revision ID: 20261008_0069
Revises: 20261006_0068

The migration deliberately requires an environment-supplied backfill subject.  It never
tries to infer an identity from a profile, e-mail, or other personal content.  Operators
must run the audited backfill only after a tested restore; Package 2 exercises this only
against synthetic `_test` databases.

Downgrade is intentionally data-preserving: application rollback may move the Alembic
revision back, but it must not discard `owner_sub` or reopen an existing row to a different
owner.  The preceding application version ignores these extra columns and constraints.
"""

from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import op

revision = "20261008_0069"
down_revision = "20261006_0068"
branch_labels = None
depends_on = None

_PERSONAL_TABLES = (
    ("profile", "career_profile"),
    ("crm", "application_process"),
    ("dashboard", "saved_search"),
    ("opportunities", "relevance_mark"),
    ("matching", "match_assessment"),
)


def _backfill_owner_sub() -> str:
    """Return the explicit migration subject without logging its value."""
    owner_sub = os.environ.get("OWNER_SUB_BACKFILL", "").strip()
    if not owner_sub:
        raise RuntimeError(
            "OWNER_SUB_BACKFILL is required for the controlled owner_sub migration"
        )
    return owner_sub


def _add_owner_column(schema: str, table: str) -> None:
    op.execute(
        f"ALTER TABLE {schema}.{table} "
        "ADD COLUMN IF NOT EXISTS owner_sub VARCHAR(255)"
    )


def _backfill_and_audit(schema: str, table: str, owner_sub: str) -> None:
    connection = op.get_bind()
    qualified = f"{schema}.{table}"
    connection.execute(
        sa.text(f"UPDATE {qualified} SET owner_sub = :owner_sub WHERE owner_sub IS NULL"),
        {"owner_sub": owner_sub},
    )
    missing = connection.execute(
        sa.text(f"SELECT count(*) FROM {qualified} WHERE owner_sub IS NULL")
    ).scalar_one()
    if missing:
        raise RuntimeError(f"owner_sub audit failed for {qualified}: {missing} rows are unowned")
    op.execute(f"ALTER TABLE {qualified} ALTER COLUMN owner_sub SET NOT NULL")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_sub "
        f"ON {qualified} (owner_sub)"
    )


def _ensure_immutable_owner_sub() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION platform.prevent_owner_sub_change()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.owner_sub IS DISTINCT FROM OLD.owner_sub THEN
                RAISE EXCEPTION 'owner_sub is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for schema, table in _PERSONAL_TABLES:
        trigger = f"trg_{table}_owner_sub_immutable"
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {schema}.{table}")
        op.execute(
            f"CREATE TRIGGER {trigger} BEFORE UPDATE OF owner_sub ON {schema}.{table} "
            "FOR EACH ROW EXECUTE FUNCTION platform.prevent_owner_sub_change()"
        )


def _replace_profile_singleton_constraint() -> None:
    op.execute(
        "ALTER TABLE profile.career_profile "
        "DROP CONSTRAINT IF EXISTS uq_career_profile_singleton_key"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_career_profile_owner_singleton_key'
                  AND conrelid = 'profile.career_profile'::regclass
            ) THEN
                ALTER TABLE profile.career_profile
                    ADD CONSTRAINT uq_career_profile_owner_singleton_key
                    UNIQUE (owner_sub, singleton_key);
            END IF;
        END
        $$
        """
    )


def upgrade() -> None:
    owner_sub = _backfill_owner_sub()
    for schema, table in _PERSONAL_TABLES:
        _add_owner_column(schema, table)
    for schema, table in _PERSONAL_TABLES:
        _backfill_and_audit(schema, table, owner_sub)
    _replace_profile_singleton_constraint()
    _ensure_immutable_owner_sub()


def downgrade() -> None:
    """Keep ownership data/constraints intact so application rollback stays safe."""
