"""Let a raw payload expire, and record every expiry that happens.

Revision ID: 20260922_0015
Revises: 20260922_0014
Create Date: 2026-09-22 00:00:00

The payload column only becomes nullable once the history table that accounts for a
missing body exists, so there is no moment at which content can disappear unexplained.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260922_0015"
down_revision = "20260922_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payload_retention_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "raw_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.raw_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "expired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("retention_policy_version", sa.String(length=32), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "source_definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("acquisition.source_definition.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # One expiry per raw item: re-running retention cannot write a second history row.
        sa.UniqueConstraint("raw_item_id", name="uq_payload_retention_event_raw_item"),
        schema="acquisition",
    )
    op.create_index(
        "ix_payload_retention_event_expired_at",
        "payload_retention_event",
        ["expired_at"],
        schema="acquisition",
    )
    op.add_column(
        "raw_item_payload",
        sa.Column("expired_at", sa.DateTime(timezone=True)),
        schema="acquisition",
    )
    op.add_column(
        "raw_item_payload",
        sa.Column("retention_policy_version", sa.String(length=32)),
        schema="acquisition",
    )
    op.alter_column("raw_item_payload", "payload", nullable=True, schema="acquisition")
    # An absent body and an unexplained absence are different states, and only the first
    # one is allowed to exist.
    op.create_check_constraint(
        "ck_raw_item_payload_expiry",
        "raw_item_payload",
        "(payload IS NOT NULL AND expired_at IS NULL) "
        "OR (payload IS NULL AND expired_at IS NOT NULL)",
        schema="acquisition",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_raw_item_payload_expiry",
        "raw_item_payload",
        type_="check",
        schema="acquisition",
    )
    # Expired rows have no content to put back; the empty object keeps the NOT NULL
    # promise without pretending the payload survived.
    op.execute(
        "UPDATE acquisition.raw_item_payload SET payload = '{}'::jsonb "
        "WHERE payload IS NULL"
    )
    op.alter_column("raw_item_payload", "payload", nullable=False, schema="acquisition")
    op.drop_column("raw_item_payload", "retention_policy_version", schema="acquisition")
    op.drop_column("raw_item_payload", "expired_at", schema="acquisition")
    op.drop_index(
        "ix_payload_retention_event_expired_at",
        table_name="payload_retention_event",
        schema="acquisition",
    )
    op.drop_table("payload_retention_event", schema="acquisition")
