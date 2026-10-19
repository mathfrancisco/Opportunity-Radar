"""Remember which fields the model already answered null for (R55-C5 follow-up).

Revision ID: 20261017_0074
Revises: 20261017_0073

A null answer created no suggestion row, so the same opportunity was asked again on every
pass. `platform.ai_suggestion_unanswered` keeps one marker per
(opportunity_id, opportunity_version, field, prompt_version); while it matches, the queue
does not ask again. A new opportunity version or prompt version asks anew.

Operational bookkeeping only (like `platform.ai_suggestion_defer`): no suggestion or
decision lives here. Downgrade drops the table; the only effect is that null answers are
asked once more.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261017_0074"
down_revision = "20261017_0073"
branch_labels = None
depends_on = None

TABLE = "ai_suggestion_unanswered"
SCHEMA = "platform"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("opportunity_version", sa.Integer(), primary_key=True),
        sa.Column("field", sa.String(32), primary_key=True),
        sa.Column("prompt_version", sa.String(32), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
