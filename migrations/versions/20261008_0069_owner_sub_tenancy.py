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
    # A controlled downgrade installs a temporary legacy-write default.  The current
    # application must never rely on it, so remove it again before re-enabling tenancy.
    op.execute(f"ALTER TABLE {schema}.{table} ALTER COLUMN owner_sub DROP DEFAULT")


def _backfill_and_audit(schema: str, table: str, owner_sub: str) -> None:
    connection = op.get_bind()
    qualified = f"{schema}.{table}"
    immutable_assessment = schema == "matching" and table == "match_assessment"
    if immutable_assessment:
        # The assessment history is immutable.  This single transaction is the explicit
        # schema migration exception; re-enable the pre-existing guard before returning.
        op.execute(
            "ALTER TABLE matching.match_assessment "
            "DISABLE TRIGGER trg_match_assessment_immutable"
        )
    try:
        connection.execute(
            sa.text(f"UPDATE {qualified} SET owner_sub = :owner_sub WHERE owner_sub IS NULL"),
            {"owner_sub": owner_sub},
        )
        missing = connection.execute(
            sa.text(f"SELECT count(*) FROM {qualified} WHERE owner_sub IS NULL")
        ).scalar_one()
        if missing:
            raise RuntimeError(
                f"owner_sub audit failed for {qualified}: {missing} rows are unowned"
            )
        op.execute(f"ALTER TABLE {qualified} ALTER COLUMN owner_sub SET NOT NULL")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_sub "
            f"ON {qualified} (owner_sub)"
        )
    finally:
        if immutable_assessment:
            op.execute(
                "ALTER TABLE matching.match_assessment "
                "ENABLE TRIGGER trg_match_assessment_immutable"
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
    """Make the preceding single-owner app writable without discarding ownership.

    The old application does not supply ``owner_sub``.  A rollback therefore requires the
    same explicitly audited subject and is refused if data belongs to more than that one
    subject.  This keeps the old global profile singleton invariant and prevents silently
    routing legacy writes to an arbitrary tenant.
    """
    owner_sub = _backfill_owner_sub()
    connection = op.get_bind()
    for schema, table in _PERSONAL_TABLES:
        qualified = f"{schema}.{table}"
        other_owners = connection.execute(
            sa.text(
                f"SELECT count(*) FROM {qualified} "
                "WHERE owner_sub IS DISTINCT FROM :owner_sub"
            ),
            {"owner_sub": owner_sub},
        ).scalar_one()
        if other_owners:
            raise RuntimeError(
                f"controlled rollback refused for {qualified}: ownership is not single-subject"
            )

    # Keep the value out of generated DDL/log output while making it available to the
    # legacy application's INSERTs for the duration of this transaction.
    connection.execute(
        sa.text("SELECT set_config('app.owner_sub_backfill', :owner_sub, true)"),
        {"owner_sub": owner_sub},
    )
    for schema, table in _PERSONAL_TABLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                EXECUTE format(
                    'ALTER TABLE %I.%I ALTER COLUMN owner_sub SET DEFAULT %L',
                    '{schema}', '{table}', current_setting('app.owner_sub_backfill')
                );
            END
            $$
            """
        )

    # Revision 0068 expects the original global singleton constraint.  Preserve the
    # owner-aware constraint as well, but restore the older contract only after the
    # single-subject audit above made it valid.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_career_profile_singleton_key'
                  AND conrelid = 'profile.career_profile'::regclass
            ) THEN
                ALTER TABLE profile.career_profile
                    ADD CONSTRAINT uq_career_profile_singleton_key
                    UNIQUE (singleton_key);
            END IF;
        END
        $$
        """
    )
