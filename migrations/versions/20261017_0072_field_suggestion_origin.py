"""Field suggestions carry their origin and may cover country and work authorization (R55-C5).

Revision ID: 20261017_0072
Revises: 20261016_0071

`opportunities.field_suggestion` already holds the model's suggestions for fields the rules
left `UNKNOWN`, apart from the canonical row. This adds the `origin` column (always `ai`
today, so an audit can tell a model suggestion from any future human or rule source) and
opens the `field` check to `country` and `work_authorization`. Nothing here touches a
canonical column or an assessment.

Downgrade deletes every `country` and `work_authorization` suggestion row, accepted ones
included, so their audit trail is lost; a country already written onto
`opportunities.allowed_countries` stays there.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_0072"
down_revision = "20261016_0071"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"
TABLE = "field_suggestion"
_OLD_FIELDS = "field IN ('role_family', 'seniority', 'work_mode')"
_NEW_FIELDS = (
    "field IN ('role_family', 'seniority', 'work_mode', 'country', 'work_authorization')"
)


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("origin", sa.String(16), nullable=False, server_default="ai"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_field_suggestion_origin", TABLE, "origin IN ('ai')", schema=SCHEMA
    )
    op.drop_constraint("ck_field_suggestion_field", TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_field_suggestion_field", TABLE, _NEW_FIELDS, schema=SCHEMA)


def downgrade() -> None:
    op.execute(
        f"DELETE FROM {SCHEMA}.{TABLE} WHERE field IN ('country', 'work_authorization')"
    )
    op.drop_constraint("ck_field_suggestion_field", TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_field_suggestion_field", TABLE, _OLD_FIELDS, schema=SCHEMA)
    op.drop_constraint("ck_field_suggestion_origin", TABLE, schema=SCHEMA, type_="check")
    op.drop_column(TABLE, "origin", schema=SCHEMA)
