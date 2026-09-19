"""Persist the advisory semantic analysis of a matching assessment.

Revision ID: 20260917_0008
Revises: 20260916_0007
Create Date: 2026-09-17 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260917_0008"
down_revision = "20260916_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_analysis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching.match_assessment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_code", sa.String(32)),
        sa.Column("detail", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "strengths",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "risks",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "inferences",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "unknowns",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("recommended_review", sa.Boolean()),
        sa.Column("model_id", sa.String(128)),
        sa.Column("prompt_version", sa.String(64)),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('AI_PENDING', 'AI_COMPLETED', 'AI_FAILED', 'AI_SKIPPED')",
            name="ck_match_analysis_status",
        ),
        sa.CheckConstraint(
            "status <> 'AI_COMPLETED' OR (summary IS NOT NULL AND model_id IS NOT NULL "
            "AND recommended_review IS NOT NULL)",
            name="ck_match_analysis_completed_payload",
        ),
        sa.CheckConstraint(
            "status <> 'AI_FAILED' OR failure_code IS NOT NULL",
            name="ck_match_analysis_failed_code",
        ),
        sa.CheckConstraint(
            "char_length(cache_key) = 64", name="ck_match_analysis_cache_key"
        ),
        schema="matching",
    )
    op.create_index(
        "ix_match_analysis_assessment_analyzed",
        "match_analysis",
        ["assessment_id", "analyzed_at"],
        schema="matching",
    )
    op.create_index(
        "ix_match_analysis_cache_key",
        "match_analysis",
        ["cache_key"],
        schema="matching",
    )
    # An analysis row is evidence of what the model answered at a point in time. Retrying
    # appends a new row; it never edits the earlier one. DELETE stays open so the cascade
    # from an assessment remains possible.
    op.execute(
        """
        CREATE FUNCTION matching.prevent_match_analysis_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'match analyses are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_match_analysis_immutable
        BEFORE UPDATE ON matching.match_analysis
        FOR EACH ROW EXECUTE FUNCTION matching.prevent_match_analysis_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_match_analysis_immutable ON matching.match_analysis"
    )
    op.execute("DROP FUNCTION IF EXISTS matching.prevent_match_analysis_mutation()")
    op.drop_index(
        "ix_match_analysis_cache_key", table_name="match_analysis", schema="matching"
    )
    op.drop_index(
        "ix_match_analysis_assessment_analyzed",
        table_name="match_analysis",
        schema="matching",
    )
    op.drop_table("match_analysis", schema="matching")
