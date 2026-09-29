"""Permit append-only raw evidence variants from distinct parser interpretations.

Revision ID: 20260926_0042
Revises: 20260926_0041

The former key collapsed every identical body for an identity into one row.  That lost
the evidence envelope when a parser version or its extracted boundary changed.  The
expanded key preserves those envelopes.  Downgrade deliberately refuses a populated
variant set because restoring the former key would otherwise discard evidence.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260926_0042"
down_revision = "20260926_0041"
branch_labels = None
depends_on = None

SCHEMA = "acquisition"
TABLE = "raw_item"
CONSTRAINT = "uq_raw_item_source_identity_hash"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="unique")
    op.execute(
        """
        ALTER TABLE acquisition.raw_item
        ADD CONSTRAINT uq_raw_item_source_identity_hash
        UNIQUE NULLS NOT DISTINCT (
            source_definition_id,
            identity_key,
            payload_hash,
            semantic_hash,
            semantic_hash_version
        )
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    collisions = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT 1
                FROM acquisition.raw_item
                GROUP BY source_definition_id, identity_key, payload_hash
                HAVING count(*) > 1
            ) AS conflicting_envelopes
            """
        )
    ).scalar_one()
    if collisions:
        raise RuntimeError(
            "refusing raw_item parser-variant downgrade: "
            f"{collisions} old-key collision group(s) would lose append-only evidence"
        )
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="unique")
    op.create_unique_constraint(
        CONSTRAINT,
        TABLE,
        ["source_definition_id", "identity_key", "payload_hash"],
        schema=SCHEMA,
    )
