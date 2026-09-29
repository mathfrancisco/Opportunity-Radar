"""Add recency-filter columns to `opportunities.opportunity` and `source_occurrence`.

Revision ID: 20260928_0053
Revises: 20260926_0052
Create Date: 2026-09-28 00:00:00

Card F20-61. The default search shows only a posting from the last 14 days
(`published_at` when the source has one, `first_seen_at` as a marked-estimate fallback
otherwise), with an exception for a time-boxed entry program (estágio/trainee/
early-careers/residência) or a posting whose explicit application-window deadline
(`valid_through`, schema.org `JobPosting.validThrough`) is still in the future.

`first_seen_at` is denormalized onto `opportunity` (mirroring the earliest
`source_occurrence.first_seen_at` that created it) so the recency filter can run as a
plain column comparison in the Inbox/Overview query, without a correlated subquery over
every opportunity on every listing. It is backfilled from the existing occurrences
(`MIN(first_seen_at)` per opportunity), falling back to `created_at` for the (expected
to be empty) case of an opportunity with no occurrence row, then made `NOT NULL` —
every real opportunity has at least one occurrence.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260928_0053"
down_revision = "20260926_0052"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"
OPPORTUNITY = "opportunity"
OCCURRENCE = "source_occurrence"


def upgrade() -> None:
    op.add_column(
        OPPORTUNITY,
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        OPPORTUNITY,
        sa.Column("valid_through", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    op.add_column(
        OPPORTUNITY,
        sa.Column(
            "recency_exempt_program",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        OCCURRENCE,
        sa.Column("source_valid_through", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )

    op.execute(
        f"""
        UPDATE {SCHEMA}.{OPPORTUNITY} AS o
        SET first_seen_at = earliest.first_seen_at
        FROM (
            SELECT opportunity_id, MIN(first_seen_at) AS first_seen_at
            FROM {SCHEMA}.{OCCURRENCE}
            GROUP BY opportunity_id
        ) AS earliest
        WHERE earliest.opportunity_id = o.id
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.{OPPORTUNITY}
        SET first_seen_at = created_at
        WHERE first_seen_at IS NULL
        """
    )
    op.alter_column(
        OPPORTUNITY,
        "first_seen_at",
        nullable=False,
        server_default=sa.func.now(),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_opportunity_first_seen", OPPORTUNITY, ["first_seen_at"], schema=SCHEMA
    )
    op.create_index(
        "ix_opportunity_valid_through", OPPORTUNITY, ["valid_through"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_valid_through", table_name=OPPORTUNITY, schema=SCHEMA)
    op.drop_index("ix_opportunity_first_seen", table_name=OPPORTUNITY, schema=SCHEMA)
    op.drop_column(OCCURRENCE, "source_valid_through", schema=SCHEMA)
    op.drop_column(OPPORTUNITY, "recency_exempt_program", schema=SCHEMA)
    op.drop_column(OPPORTUNITY, "valid_through", schema=SCHEMA)
    op.drop_column(OPPORTUNITY, "first_seen_at", schema=SCHEMA)
