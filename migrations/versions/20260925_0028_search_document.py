"""Full-text search document for the Inbox (F17-03).

Revision ID: 20260925_0028
Revises: 20260925_0027
Create Date: 2026-09-25 13:00:00

`search_skills` is a denormalized, service-maintained copy of the skill names: a
generated column can only read columns of its own table, so skills (a different table)
cannot feed `search_document` directly. `f_unaccent` wraps the `unaccent` contrib
function as IMMUTABLE — `unaccent` itself is STABLE (it depends on search_path), which
Postgres refuses inside a generated column.

The generated column back-fills automatically for the existing collection as part of the
`ALTER TABLE ... ADD COLUMN ... GENERATED ALWAYS AS (...) STORED`, so no separate backfill
statement is needed. On a large collection this rewrites the table; run outside the
collection window (see the card's implementation notes).
"""

import sqlalchemy as sa
from alembic import op

revision = "20260925_0028"
down_revision = "20260925_0027"
branch_labels = None
depends_on = None

SCHEMA = "opportunities"

_TSVECTOR_EXPRESSION = """
setweight(to_tsvector('portuguese',
    opportunities.f_unaccent(coalesce(canonical_title, ''))), 'A') ||
setweight(to_tsvector('english',
    opportunities.f_unaccent(coalesce(canonical_title, ''))), 'A') ||
setweight(to_tsvector('portuguese',
    opportunities.f_unaccent(coalesce(company_name, ''))), 'A') ||
setweight(to_tsvector('english',
    opportunities.f_unaccent(coalesce(company_name, ''))), 'A') ||
setweight(to_tsvector('portuguese',
    opportunities.f_unaccent(coalesce(search_skills, ''))), 'B') ||
setweight(to_tsvector('english',
    opportunities.f_unaccent(coalesce(search_skills, ''))), 'B') ||
setweight(to_tsvector('portuguese',
    opportunities.f_unaccent(replace(coalesce(role_family, ''), '_', ' '))), 'B') ||
setweight(to_tsvector('english',
    opportunities.f_unaccent(replace(coalesce(role_family, ''), '_', ' '))), 'B') ||
setweight(to_tsvector('portuguese',
    opportunities.f_unaccent(coalesce(description, ''))), 'C') ||
setweight(to_tsvector('english',
    opportunities.f_unaccent(coalesce(description, ''))), 'C') ||
setweight(to_tsvector('portuguese',
    opportunities.f_unaccent(coalesce(location_text, ''))), 'D') ||
setweight(to_tsvector('english',
    opportunities.f_unaccent(coalesce(location_text, ''))), 'D')
""".strip()


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.f_unaccent(text)
        RETURNS text AS $$
            SELECT public.unaccent('public.unaccent', $1)
        $$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        """
    )
    op.add_column(
        "opportunity",
        sa.Column("search_skills", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "opportunity",
        sa.Column(
            "search_document",
            sa.dialects.postgresql.TSVECTOR(),
            sa.Computed(_TSVECTOR_EXPRESSION, persisted=True),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_opportunity_search_document",
        "opportunity",
        ["search_document"],
        schema=SCHEMA,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opportunity_search_document", table_name="opportunity", schema=SCHEMA
    )
    op.drop_column("opportunity", "search_document", schema=SCHEMA)
    op.drop_column("opportunity", "search_skills", schema=SCHEMA)
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.f_unaccent(text)")
