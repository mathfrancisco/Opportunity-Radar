"""Proof that `pre_f20_dump.sql`'s `normalizer_version` literal tracks the constant.

`tests/backend/test_upgrade_populated_integration.py` restores this fixture and then
relies on `NORMALIZER_VERSION` to identify which raw items are "pending" (see
`test_interrupted_backfill_resumes_without_duplicating`). The fixture is a `pg_dump`
snapshot and cannot reference the constant directly, so its 20 `normalization_result`
rows carry a literal (`v6`) that `_fixture_sql_for_current_normalizer_version` rewrites
to whatever `NORMALIZER_VERSION` is today before the SQL reaches `psql`.

This test needs no database and no `psql`: it only proves the substitution runs. If
someone reverts it — restores the raw fixture text unchanged, or bumps
`NORMALIZER_VERSION` without updating the substitution — this fails the moment the
constant no longer matches the dumped literal, instead of failing silently and only much
later inside the gated integration suite.
"""

from __future__ import annotations

from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from tests.backend.test_upgrade_populated_integration import (
    FIXTURE_DUMPED_NORMALIZER_VERSION,
    _fixture_sql_for_current_normalizer_version,
)


def test_restored_sql_carries_the_current_normalizer_version_not_the_dumped_literal() -> None:
    sql = _fixture_sql_for_current_normalizer_version()

    current_marker = f"\tSUCCEEDED\t{NORMALIZER_VERSION}\tNEW\t"
    assert sql.count(current_marker) == 20

    if NORMALIZER_VERSION != FIXTURE_DUMPED_NORMALIZER_VERSION:
        stale_marker = f"\tSUCCEEDED\t{FIXTURE_DUMPED_NORMALIZER_VERSION}\tNEW\t"
        assert stale_marker not in sql, (
            "the fixture's dumped normalizer_version literal survived the "
            "substitution; NORMALIZER_VERSION moved on and this fixture would break "
            "test_interrupted_backfill_resumes_without_duplicating"
        )
