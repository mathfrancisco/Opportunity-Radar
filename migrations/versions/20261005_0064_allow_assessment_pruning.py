"""Let the retention job delete superseded assessments.

Revision ID: 20261005_0064
Revises: 20261005_0063
Create Date: 2026-10-05 00:00:00

Card F50-08: assessments and their factors stay immutable. The only exception is a DELETE
inside a transaction that set `matching.allow_prune` to `on`, which only the assessment
retention job does. UPDATE is refused in every case.
"""

from alembic import op

revision = "20261005_0064"
down_revision = "20261005_0063"
branch_labels = None
depends_on = None


def _guard(function: str, message: str, *, allow_prune: bool) -> str:
    prune = (
        """
            IF TG_OP = 'DELETE'
               AND current_setting('matching.allow_prune', true) = 'on' THEN
                RETURN OLD;
            END IF;"""
        if allow_prune
        else ""
    )
    return f"""
        CREATE OR REPLACE FUNCTION matching.{function}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN{prune}
            RAISE EXCEPTION '{message}';
        END;
        $$;
        """


_GUARDS = (
    ("prevent_match_assessment_mutation", "match assessments are immutable"),
    ("prevent_match_factor_mutation", "match factors are immutable"),
)


def upgrade() -> None:
    for function, message in _GUARDS:
        op.execute(_guard(function, message, allow_prune=True))


def downgrade() -> None:
    for function, message in _GUARDS:
        op.execute(_guard(function, message, allow_prune=False))
