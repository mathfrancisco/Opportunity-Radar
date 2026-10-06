"""Persist Workday request reservations and detail telemetry.

Revision ID: 20261005_0066
Revises: 20261005_0065
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261005_0066"
down_revision = "20261005_0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_run", sa.Column("detail_requests", sa.Integer()), schema="acquisition")
    op.add_column("source_run", sa.Column("detail_failures", sa.Integer()), schema="acquisition")
    op.add_column("source_run", sa.Column("detail_skipped", sa.Integer()), schema="acquisition")
    op.add_column(
        "source_run", sa.Column("detail_skip_reasons", JSONB()), schema="acquisition"
    )
    # Collapse every old tenant/site budget into its physical hostname. Summing spend,
    # retaining the latest window start, minimum ceiling, and maximum cooldown is
    # intentionally conservative: a migration can temporarily block a host, never grant
    # it duplicate quota. No source-run FK is involved in host reservations.
    op.execute(sa.text("""
        WITH old_rows AS (
            SELECT host,
                   split_part(split_part(host, ':', 2), '/', 1) || '.' ||
                   split_part(host, ':', 3) || '.myworkdayjobs.com' AS target_host,
                   window_start, requests_used, requests_ceiling,
                   cooldown_until, exploration_reserve_ratio
              FROM acquisition.host_budget_state
             WHERE host LIKE 'workday:%/%:%'
        ), grouped AS (
            SELECT target_host AS host, max(window_start) AS window_start,
                   sum(requests_used)::integer AS requests_used,
                   min(requests_ceiling) AS requests_ceiling,
                   max(cooldown_until) AS cooldown_until,
                   max(exploration_reserve_ratio) AS exploration_reserve_ratio
              FROM old_rows GROUP BY target_host
        )
        INSERT INTO acquisition.host_budget_state
            (host, window_start, requests_used, requests_ceiling, cooldown_until,
             exploration_reserve_ratio, updated_at)
        SELECT host, window_start, requests_used, requests_ceiling, cooldown_until,
               exploration_reserve_ratio, now() FROM grouped
        ON CONFLICT (host) DO UPDATE SET
            window_start = GREATEST(
                acquisition.host_budget_state.window_start, EXCLUDED.window_start
            ),
            requests_used = acquisition.host_budget_state.requests_used + EXCLUDED.requests_used,
            requests_ceiling = LEAST(
                acquisition.host_budget_state.requests_ceiling, EXCLUDED.requests_ceiling
            ),
            cooldown_until = GREATEST(
                acquisition.host_budget_state.cooldown_until, EXCLUDED.cooldown_until
            ),
            exploration_reserve_ratio = GREATEST(
                acquisition.host_budget_state.exploration_reserve_ratio,
                EXCLUDED.exploration_reserve_ratio
            ),
            updated_at = now()
    """))
    op.execute(sa.text("DELETE FROM acquisition.host_budget_state WHERE host LIKE 'workday:%/%:%'"))


def downgrade() -> None:
    # Reconstruct each configured Workday site's legacy key from its shared physical
    # host row. Every reconstructed site is exhausted for a fresh window: copying the
    # host's remaining balance to N sites would multiply its allowance after rollback.
    # Starting the window now also keeps an already-rolled-over host from receiving a
    # fresh allowance once per site. Existing legacy-key collisions merge conservatively.
    op.execute(sa.text("""
        WITH source_keys AS (
            SELECT DISTINCT
                   'workday:' || sd.configuration ->> 'tenant_identifier' || ':' ||
                   sd.configuration ->> 'api_region' AS legacy_host,
                   split_part(sd.configuration ->> 'tenant_identifier', '/', 1) || '.' ||
                   sd.configuration ->> 'api_region' || '.myworkdayjobs.com' AS physical_host
              FROM acquisition.source_definition sd
             WHERE sd.source_type = 'workday'
               AND coalesce(sd.configuration ->> 'tenant_identifier', '') LIKE '%/%'
               AND coalesce(sd.configuration ->> 'api_region', '') <> ''
        ), reconstructed AS (
            SELECT sk.legacy_host,
                   max(host.requests_ceiling) AS requests_ceiling,
                   max(host.requests_ceiling) AS requests_used,
                   max(host.cooldown_until) AS cooldown_until,
                   max(host.exploration_reserve_ratio) AS exploration_reserve_ratio
              FROM source_keys sk
              JOIN acquisition.host_budget_state host ON host.host = sk.physical_host
             GROUP BY sk.legacy_host
        )
        INSERT INTO acquisition.host_budget_state
            (host, window_start, requests_used, requests_ceiling, cooldown_until,
             exploration_reserve_ratio, updated_at)
        SELECT legacy_host, now(), requests_used, requests_ceiling, cooldown_until,
               exploration_reserve_ratio, now() FROM reconstructed
        ON CONFLICT (host) DO UPDATE SET
            window_start = now(),
            requests_used = GREATEST(
                acquisition.host_budget_state.requests_used, EXCLUDED.requests_used,
                acquisition.host_budget_state.requests_ceiling
            ),
            requests_ceiling = LEAST(
                acquisition.host_budget_state.requests_ceiling, EXCLUDED.requests_ceiling
            ),
            cooldown_until = GREATEST(
                acquisition.host_budget_state.cooldown_until, EXCLUDED.cooldown_until
            ),
            exploration_reserve_ratio = GREATEST(
                acquisition.host_budget_state.exploration_reserve_ratio,
                EXCLUDED.exploration_reserve_ratio
            ),
            updated_at = now()
    """))
    op.drop_column("source_run", "detail_skip_reasons", schema="acquisition")
    op.drop_column("source_run", "detail_skipped", schema="acquisition")
    op.drop_column("source_run", "detail_failures", schema="acquisition")
    op.drop_column("source_run", "detail_requests", schema="acquisition")
