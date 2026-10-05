"""Materialise the latest assessment per posting and profile version.

Revision ID: 20261005_0063
Revises: 20261005_0062
Create Date: 2026-10-05 00:00:00

Card F50-10: the Inbox recomputed the newest assessment of every posting (DISTINCT ON over
the whole `match_assessment` history) on each request. This table points at that newest row
per (posting, profile version) and is kept up to date when an assessment is written. It
copies only what the Inbox orders, filters and tests for currency by; whether the pointed
assessment is still current is decided at read time, never stored here.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261005_0063"
down_revision = "20261005_0062"
branch_labels = None
depends_on = None

SCHEMA = "matching"
TABLE = "current_assessment"

#: The newest row: the highest posting version (a rewrite supersedes whatever came before),
#: then `assessed_at`, then `id`.
BACKFILL_SQL = f"""
    INSERT INTO {SCHEMA}.{TABLE} (
        opportunity_id, profile_version_id, assessment_id, opportunity_version,
        rules_version, taxonomy_version, verdict, eligibility, score, confidence, assessed_at
    )
    SELECT DISTINCT ON (opportunity_id, profile_version_id)
        opportunity_id, profile_version_id, id, opportunity_version,
        rules_version, taxonomy_version, verdict, eligibility, score, confidence, assessed_at
    FROM {SCHEMA}.match_assessment
    ORDER BY opportunity_id, profile_version_id, opportunity_version DESC,
        assessed_at DESC, id DESC
"""


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        # RESTRICT: a pointed row is the newest by construction and retention keeps it, so
        # a delete that reaches it is a bug to surface, not a pointer to drop silently.
        # Rows that are not pointed are not referenced and delete freely.
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column("rules_version", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("eligibility", sa.String(16), nullable=False),
        sa.Column("score", sa.Numeric(7, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "opportunity_id", "profile_version_id", name="pk_current_assessment"
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"],
            ["opportunities.opportunity.id"],
            name="fk_current_assessment_opportunity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["profile_version_id"],
            ["profile.profile_version.id"],
            name="fk_current_assessment_profile_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            [f"{SCHEMA}.match_assessment.id"],
            name="fk_current_assessment_assessment",
            ondelete="RESTRICT",
        ),
        schema=SCHEMA,
    )
    # The FK's own lookup when an assessment is deleted, and the Inbox's analysis join.
    op.create_index(
        "ix_current_assessment_assessment", TABLE, ["assessment_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_current_assessment_profile_verdict",
        TABLE,
        ["profile_version_id", "verdict"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_current_assessment_profile_score",
        TABLE,
        ["profile_version_id", sa.text("score DESC")],
        schema=SCHEMA,
    )
    op.execute(BACKFILL_SQL)


def downgrade() -> None:
    op.drop_table(TABLE, schema=SCHEMA)
