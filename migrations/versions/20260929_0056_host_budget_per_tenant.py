"""Split the aggregate host budget rows of per-tenant source types into one row per tenant.

Revision ID: 20260929_0056
Revises: 20260929_0055
Create Date: 2026-09-29 00:00:00

Card F48-08. `acquisition.host_budget_state` was keyed by `source_type` for Workday,
Teamtailor, Factorial and JobPosting, so fifteen Workday tenants shared one bucket (518 of a
200 ceiling in one hour). The service now keys those types per tenant (`workday:<tenant>:
<region>`, `teamtailor:<company>`, `factorial:<company>`, `jobposting:<host>`).

Upgrade: for each existing aggregate row, create one row per configured source tenant with a
fresh window and zero spend (the aggregate spend cannot be attributed to a tenant, and the
old value only reflected extraction calls that never worked), keeping the cooldown, then drop
the aggregate row. Workday tenants get a ceiling of at least 500. Downgrade: fold the tenant
rows back into one aggregate row per type (spend summed, latest cooldown) and drop them.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260929_0056"
down_revision = "20260929_0055"
branch_labels = None
depends_on = None

_TABLE = "acquisition.host_budget_state"
_WORKDAY_MIN_CEILING = 500

# The same keys `opportunity_radar.acquisition.concurrency.source_host_key` builds.
_TENANT_KEY_SQL = {
    "workday": (
        "'workday:' || coalesce(sd.configuration ->> 'tenant_identifier', '') "
        "|| ':' || coalesce(sd.configuration ->> 'api_region', '')"
    ),
    "teamtailor": "'teamtailor:' || coalesce(sd.configuration ->> 'company_identifier', '')",
    "factorial": "'factorial:' || coalesce(sd.configuration ->> 'company_identifier', '')",
    "jobposting": (
        "'jobposting:' || coalesce("
        "lower(substring(coalesce(sd.configuration ->> 'page_url', '') "
        "from '://(?:[^/@?#]*@)?([^/:?#]+)')), "
        "coalesce(sd.configuration ->> 'page_url', ''))"
    ),
}


def upgrade() -> None:
    for source_type, key_sql in _TENANT_KEY_SQL.items():
        ceiling_sql = (
            f"greatest(agg.requests_ceiling, {_WORKDAY_MIN_CEILING})"
            if source_type == "workday"
            else "agg.requests_ceiling"
        )
        op.execute(
            sa.text(
                f"""
                INSERT INTO {_TABLE}
                    (host, window_start, requests_used, requests_ceiling,
                     cooldown_until, exploration_reserve_ratio)
                SELECT DISTINCT left({key_sql}, 255), now(), 0, {ceiling_sql},
                       agg.cooldown_until, agg.exploration_reserve_ratio
                FROM acquisition.source_definition sd
                JOIN {_TABLE} agg ON agg.host = :source_type
                WHERE sd.source_type = :source_type
                ON CONFLICT (host) DO NOTHING
                """
            ).bindparams(source_type=source_type)
        )
        op.execute(
            sa.text(f"DELETE FROM {_TABLE} WHERE host = :source_type").bindparams(
                source_type=source_type
            )
        )


def downgrade() -> None:
    for source_type in _TENANT_KEY_SQL:
        op.execute(
            sa.text(
                f"""
                INSERT INTO {_TABLE}
                    (host, window_start, requests_used, requests_ceiling,
                     cooldown_until, exploration_reserve_ratio)
                SELECT :source_type, min(window_start), sum(requests_used), 200,
                       max(cooldown_until), min(exploration_reserve_ratio)
                FROM {_TABLE}
                WHERE host LIKE :prefix
                HAVING count(*) > 0
                ON CONFLICT (host) DO NOTHING
                """
            ).bindparams(source_type=source_type, prefix=f"{source_type}:%")
        )
        op.execute(
            sa.text(f"DELETE FROM {_TABLE} WHERE host LIKE :prefix").bindparams(
                prefix=f"{source_type}:%"
            )
        )
