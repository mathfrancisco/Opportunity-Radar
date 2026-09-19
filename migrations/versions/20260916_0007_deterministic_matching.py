"""Create immutable deterministic matching assessments.

Revision ID: 20260916_0007
Revises: 20260915_0006
Create Date: 2026-09-16 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260916_0007"
down_revision = "20260915_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "employment_preference",
        sa.Column("compensation_period", sa.String(16)),
        schema="profile",
    )
    op.create_check_constraint(
        "ck_preference_compensation_period",
        "employment_preference",
        "compensation_period IS NULL OR compensation_period IN "
        "('YEAR', 'MONTH', 'WEEK', 'DAY', 'HOUR')",
        schema="profile",
    )
    op.create_table(
        "match_assessment",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.opportunity.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("opportunity_version", sa.Integer(), nullable=False),
        sa.Column(
            "profile_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile.profile_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("rules_version", sa.String(64), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("opportunity_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("eligibility", sa.String(16), nullable=False),
        sa.Column(
            "eligibility_details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("score", sa.Numeric(7, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("input_hash", name="uq_match_assessment_input_hash"),
        sa.CheckConstraint(
            "char_length(input_hash) = 64", name="ck_match_assessment_input_hash"
        ),
        sa.CheckConstraint(
            "opportunity_version > 0", name="ck_match_assessment_opportunity_version"
        ),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_match_assessment_score"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_match_assessment_confidence"
        ),
        sa.CheckConstraint(
            "eligibility IN ('ELIGIBLE', 'INELIGIBLE', 'UNKNOWN')",
            name="ck_match_assessment_eligibility",
        ),
        sa.CheckConstraint("status IN ('COMPLETED')", name="ck_match_assessment_status"),
        sa.CheckConstraint(
            "verdict IN ('HIGH_PRIORITY', 'RECOMMENDED', 'WATCHLIST', 'LOW_MATCH', "
            "'INELIGIBLE', 'REVIEW_REQUIRED')",
            name="ck_match_assessment_verdict",
        ),
        schema="matching",
    )
    op.create_index(
        "ix_match_assessment_opportunity_profile_created",
        "match_assessment",
        ["opportunity_id", "profile_version_id", "created_at"],
        schema="matching",
    )
    op.create_table(
        "match_factor",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matching.match_assessment.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("factor_code", sa.String(64), nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("raw_score", sa.Numeric(5, 4)),
        sa.Column("contribution", sa.Numeric(7, 4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("missing_policy", sa.String(32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "evidence_refs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "assessment_id", "factor_code", name="uq_match_factor_assessment_code"
        ),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_match_factor_weight"),
        sa.CheckConstraint(
            "raw_score IS NULL OR (raw_score >= 0 AND raw_score <= 1)",
            name="ck_match_factor_raw_score",
        ),
        sa.CheckConstraint(
            "contribution >= 0 AND contribution <= 100",
            name="ck_match_factor_contribution",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_match_factor_confidence"
        ),
        sa.CheckConstraint(
            "status IN ('KNOWN', 'UNKNOWN', 'NOT_APPLICABLE')",
            name="ck_match_factor_status",
        ),
        sa.CheckConstraint(
            "missing_policy IN ('NEUTRAL', 'PENALIZE', 'EXCLUDE_AND_RENORMALIZE', "
            "'REQUIRE_REVIEW')",
            name="ck_match_factor_missing_policy",
        ),
        schema="matching",
    )
    op.create_index(
        "ix_match_factor_assessment",
        "match_factor",
        ["assessment_id"],
        schema="matching",
    )
    op.execute(
        """
        CREATE FUNCTION matching.prevent_match_assessment_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'match assessments are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_match_assessment_immutable
        BEFORE UPDATE OR DELETE ON matching.match_assessment
        FOR EACH ROW EXECUTE FUNCTION matching.prevent_match_assessment_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION matching.prevent_match_factor_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'match factors are immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_match_factor_immutable
        BEFORE UPDATE OR DELETE ON matching.match_factor
        FOR EACH ROW EXECUTE FUNCTION matching.prevent_match_factor_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_match_factor_immutable ON matching.match_factor")
    op.execute("DROP FUNCTION IF EXISTS matching.prevent_match_factor_mutation()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_match_assessment_immutable "
        "ON matching.match_assessment"
    )
    op.execute("DROP FUNCTION IF EXISTS matching.prevent_match_assessment_mutation()")
    op.drop_index("ix_match_factor_assessment", table_name="match_factor", schema="matching")
    op.drop_table("match_factor", schema="matching")
    op.drop_index(
        "ix_match_assessment_opportunity_profile_created",
        table_name="match_assessment",
        schema="matching",
    )
    op.drop_table("match_assessment", schema="matching")
    op.drop_constraint(
        "ck_preference_compensation_period",
        "employment_preference",
        schema="profile",
        type_="check",
    )
    op.drop_column("employment_preference", "compensation_period", schema="profile")
