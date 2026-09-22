"""Split the immutable RawItem envelope from the payload that may later expire.

Revision ID: 20260922_0014
Revises: 20260922_0013
Create Date: 2026-09-22 00:00:00

The steps are ordered so that no window exists in which content is unreachable: the new
structure is created, every existing payload is copied into it, the copy is validated row
by row, and only then does the column stop being the source of truth. IDs, hashes and
provenance are untouched throughout — a RawItem is never recreated.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260922_0014"
down_revision = "20260922_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_item_payload",
        sa.Column(
            "raw_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.raw_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "stored_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="acquisition",
    )
    # Idempotent by construction: the primary key is the raw item, so re-running the
    # backfill against a partially migrated database adds the missing rows and no others.
    op.execute(
        """
        INSERT INTO acquisition.raw_item_payload (raw_item_id, payload, stored_at)
        SELECT id, payload, fetched_at FROM acquisition.raw_item
        ON CONFLICT (raw_item_id) DO NOTHING
        """
    )
    _assert_every_payload_was_copied()
    op.drop_column("raw_item", "payload", schema="acquisition")


def _assert_every_payload_was_copied() -> None:
    """Fail the migration rather than drop a column whose content did not survive it."""
    connection = op.get_bind()
    orphaned = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM acquisition.raw_item AS item
            LEFT JOIN acquisition.raw_item_payload AS body
                ON body.raw_item_id = item.id
            WHERE body.raw_item_id IS NULL
            """
        )
    ).scalar_one()
    if orphaned:
        raise RuntimeError(
            f"{orphaned} raw item(s) have no payload row; refusing to drop the column"
        )
    mismatched = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM acquisition.raw_item AS item
            JOIN acquisition.raw_item_payload AS body ON body.raw_item_id = item.id
            WHERE body.payload IS DISTINCT FROM item.payload
            """
        )
    ).scalar_one()
    if mismatched:
        raise RuntimeError(
            f"{mismatched} migrated payload(s) differ from the original content"
        )


def downgrade() -> None:
    op.add_column(
        "raw_item",
        sa.Column("payload", postgresql.JSONB()),
        schema="acquisition",
    )
    op.execute(
        """
        UPDATE acquisition.raw_item AS item
        SET payload = body.payload
        FROM acquisition.raw_item_payload AS body
        WHERE body.raw_item_id = item.id AND body.payload IS NOT NULL
        """
    )
    # An expired payload has no content to restore, so the column it goes back into
    # cannot claim to be complete. Empty object, not a lie about what was collected.
    op.execute(
        "UPDATE acquisition.raw_item SET payload = '{}'::jsonb WHERE payload IS NULL"
    )
    op.alter_column("raw_item", "payload", nullable=False, schema="acquisition")
    op.drop_table("raw_item_payload", schema="acquisition")
