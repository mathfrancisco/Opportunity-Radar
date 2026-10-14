"""Integration proof for F20-48: a database populated before Phase 20 upgrades to head
without losing history, and an interrupted backfill resumes without duplicating.

Card F20-48 depends on F20-41, F20-12 and F20-19, and this test reuses rather than
reimplements each of them:

- F20-41's backup/restore tooling: `scripts.restore_check.create_database`/
  `drop_database` and `platform.backup.with_database`/`postgres_dsn` create and tear
  down the scratch database on the same Postgres server the rest of the integration
  suite already uses, exactly as `test_backup_restore_integration.py` does.
- F20-12 (`platform.ai_quota_usage`) and F20-19 (`platform.ai_call_record`) are part of
  what `alembic upgrade head` must create on top of the pre-Phase-20 schema; a broken
  migration for either shows up here as a failed upgrade, not only in their own suites.
- F17-06's resumable batch reprocessing (`OpportunityService.normalize_pending`,
  `tests/backend/test_reprocessing_batches_integration.py`) is the "backfill" this
  card's third acceptance criterion asks to interrupt and resume; this test drives that
  existing mechanism against data that survived a real upgrade, it does not add a
  second implementation of resumable batching.

`tests/backend/fixtures/pre_f20_dump.sql` is a small, fully synthetic dump (no real
company, candidate or job posting data) taken at revision `20260925_0029` — the
revision immediately before the Phase 20 migrations (`0030` quota, `0031` telemetry,
`0032` onward). It carries a profile, 20 opportunities collected and normalized through
the real HTTP API, 20 deterministic match assessments, and 20 match analyses recorded
with `model_id="qwen3:8b-q4_K_M"` (the Ollama model Phase 16/17 used before Groq), plus
3 applications — built the same way `docs/44-roadmap-fase-20/evidencias/
upgrade-banco-populado-2026-09-27.md` documents, then `alembic downgrade 20260925_0029`
stripped every column and table the Phase 20 migrations would later add. That downgrade
is what makes the fixture authentic: the data was real (synthetic, but produced by the
real collection/normalization/matching flow), the schema gap is exactly what a database
that stopped receiving migrations before Phase 20 would have.

A separate, larger proof against the actual pre-Phase-20 production dump
(`data/backups/f20-02-pre-skills-v3-2026-09-27.dump`, restored into the isolated compose
project `-p f20up`, never `opportunity-radar`) is documented in the evidence file: it is
not checked into this repository and cannot run in CI, but it exercises the identical
upgrade-then-resume path this test exercises against the committed fixture.

Gated behind `RUN_DATABASE_INTEGRATION=1`, same as the rest of the database integration
suite; skips itself if `psql` is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import NORMALIZER_VERSION, OpportunityService
from opportunity_radar.platform.backup import postgres_dsn, with_database
from opportunity_radar.platform.database import create_database_engine
from scripts.restore_check import create_database, drop_database

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
    pytest.mark.skipif(
        shutil.which("psql") is None, reason="psql is not on PATH in this environment"
    ),
]

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "pre_f20_dump.sql"
PRE_PHASE_20_REVISION = "20260925_0029"

#: The literal `normalizer_version` this fixture's 20 `normalization_result` rows were
#: dumped with. A `pg_dump` fixture cannot reference the `NORMALIZER_VERSION` constant
#: directly, so `_restore_fixture` substitutes this literal for the constant's current
#: value before handing the SQL to `psql`. Bumping `NORMALIZER_VERSION` in
#: `opportunities/service.py` used to silently break `test_interrupted_backfill_
#: resumes_without_duplicating` (every fixture row would look "pending" for the new
#: version, not only the 5 the test forces back to pending) — this substitution, plus
#: `test_fixture_carries_the_dumped_normalizer_version_literal` below, keeps that
#: coupling visible instead of silent.
FIXTURE_DUMPED_NORMALIZER_VERSION = "v6"

#: Counted before and after the upgrade; acceptance criterion 1 requires every one of
#: these to come back identical. Mirrors the vertical-flow tables `platform/backup.py`
#: already tracks, minus the Phase 20 tables that do not exist before the upgrade.
COUNT_QUERIES: dict[str, str] = {
    "companies": "SELECT count(*) FROM company_radar.company",
    "profile_versions": "SELECT count(*) FROM profile.profile_version",
    "source_definitions": "SELECT count(*) FROM acquisition.source_definition",
    "source_runs": "SELECT count(*) FROM acquisition.source_run",
    "raw_items": "SELECT count(*) FROM acquisition.raw_item",
    "opportunities": "SELECT count(*) FROM opportunities.opportunity",
    "source_occurrences": "SELECT count(*) FROM opportunities.source_occurrence",
    "match_assessments": "SELECT count(*) FROM matching.match_assessment",
    "match_analyses": "SELECT count(*) FROM matching.match_analysis",
    "applications": "SELECT count(*) FROM crm.application_process",
}


def _fixture_sql_for_current_normalizer_version() -> str:
    """The fixture's SQL, with its dumped `normalizer_version` literal rewritten to
    whatever `NORMALIZER_VERSION` is today.

    The literal only ever appears as the `normalizer_version` field of a
    `normalization_result` COPY row (`\\tSUCCEEDED\\tv6\\tNEW\\t`); nothing else in the
    dump matches that exact sequence, so this substitution cannot touch an unrelated
    `v6`/`v1`/`v2` elsewhere in the file (fingerprint_version, role_family_version,
    mapping_version, …).
    """
    marker = f"\tSUCCEEDED\t{FIXTURE_DUMPED_NORMALIZER_VERSION}\tNEW\t"
    replacement = f"\tSUCCEEDED\t{NORMALIZER_VERSION}\tNEW\t"
    sql = FIXTURE_PATH.read_text(encoding="utf-8")
    assert sql.count(marker) == 20, (
        "expected exactly the fixture's 20 normalization_result rows to carry the "
        f"dumped normalizer_version literal {FIXTURE_DUMPED_NORMALIZER_VERSION!r}; the "
        "fixture file changed shape and this substitution needs to be revisited"
    )
    return sql.replace(marker, replacement)


def _restore_fixture(url: str) -> None:
    """Load the plain-SQL fixture into an empty database with `psql`.

    The fixture is a full `pg_dump --format=plain` of a database at
    `20260925_0029` (schema + data), not just data: restoring it into an empty
    database is what proves the upgrade path starts from a database that predates
    every Phase 20 migration, the same way an operator's real, unmigrated database
    would. Its `normalizer_version` literal is rewritten to the current
    `NORMALIZER_VERSION` before it reaches `psql` — see
    `_fixture_sql_for_current_normalizer_version`.
    """
    sql = _fixture_sql_for_current_normalizer_version()
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sql", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(sql)
        rewritten_path = handle.name
    try:
        command_line = [
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "--quiet",
            postgres_dsn(url),
            "-f",
            rewritten_path,
        ]
        result = subprocess.run(command_line, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(f"psql failed to restore the fixture: {result.stderr}")
    finally:
        os.unlink(rewritten_path)


def _alembic_upgrade_head(url: str) -> None:
    """Run the real `alembic upgrade head` as a subprocess, against `url`.

    `migrations/env.py` reads `DATABASE_URL` from the environment, and — like the
    CI job's own "Verify migration round trip" step — this is the exact command CI
    and an operator run, not a reimplementation of it. A subprocess also keeps
    Alembic's `fileConfig(...)` call (`migrations/env.py`) from reconfiguring this
    test process's own logging handlers, which would otherwise break `caplog` in
    tests that run afterwards in the same pytest session.
    """
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"alembic upgrade head failed: {result.stderr}")


def _snapshot(url: str) -> dict[str, int]:
    engine = create_database_engine(url)
    try:
        with engine.connect() as connection:
            return {
                label: int(connection.execute(text(query)).scalar_one())
                for label, query in COUNT_QUERIES.items()
            }
    finally:
        engine.dispose()


def _current_revision(url: str) -> str:
    engine = create_database_engine(url)
    try:
        revision_query = text("SELECT version_num FROM alembic_version")
        with engine.connect() as connection:
            return str(connection.execute(revision_query).scalar_one())
    finally:
        engine.dispose()


@pytest.fixture
def scratch_database() -> Any:
    url = os.environ["DATABASE_URL"]
    name = f"f2048_upgrade_{uuid4().hex[:12]}_test"
    create_database(url, name)
    scratch_url = with_database(url, name)
    try:
        yield scratch_url
    finally:
        drop_database(url, name)


def test_pre_phase_20_database_upgrades_to_head_without_losing_history(
    scratch_database: str,
) -> None:
    _restore_fixture(scratch_database)
    assert _current_revision(scratch_database) == PRE_PHASE_20_REVISION

    before = _snapshot(scratch_database)
    assert before["opportunities"] == 20
    assert before["match_analyses"] == 20
    assert before["applications"] == 3

    _alembic_upgrade_head(scratch_database)

    after = _snapshot(scratch_database)
    assert after == before, f"counts changed across the upgrade: before={before}, after={after}"

    # Acceptance criterion: Groq/Phase-20 tables the upgrade must have created exist and
    # start empty — the upgrade adds capability, it does not fabricate history.
    engine = create_database_engine(scratch_database)
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT count(*) FROM platform.ai_quota_usage")
            ).scalar_one() == 0
            assert connection.execute(
                text("SELECT count(*) FROM platform.ai_call_record")
            ).scalar_one() == 0
    finally:
        engine.dispose()


def test_old_ollama_analyses_remain_legible_after_the_upgrade(scratch_database: str) -> None:
    _restore_fixture(scratch_database)
    _alembic_upgrade_head(scratch_database)

    engine = create_database_engine(scratch_database)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT model_id, status, summary, prompt_version, schema_version "
                    "FROM matching.match_analysis ORDER BY id"
                )
            ).all()
    finally:
        engine.dispose()

    assert len(rows) == 20
    for model_id, status, summary, prompt_version, schema_version in rows:
        # Old rows keep the Ollama model_id verbatim: the upgrade never rewrites history
        # to look as if Groq had always been the provider.
        assert model_id == "qwen3:8b-q4_K_M"
        assert status == "AI_COMPLETED"
        assert summary is not None and "F20-48" in summary
        assert prompt_version == "v1"
        assert schema_version == "v1"


def test_interrupted_backfill_resumes_without_duplicating(scratch_database: str) -> None:
    """Acceptance criterion 3: a backfill that stops partway through and restarts
    finishes the rest exactly once, on data that just came through a real upgrade.

    This reuses F17-06's own resumability (`OpportunityService.normalize_pending`
    only ever selects raw items that have no `NormalizationResultModel` row for the
    current `NORMALIZER_VERSION`, see `opportunities/repository.py:pending_raw_item_ids`)
    rather than adding a second retry/checkpoint mechanism: the "interruption" here is
    simulated the same way `test_reprocessing_batches_integration.py` already does it —
    calling the batch repeatedly with a limit smaller than the backlog, each call
    independent of the last, exactly what a worker restarting between batches looks like.
    """
    _restore_fixture(scratch_database)
    _alembic_upgrade_head(scratch_database)

    engine = create_database_engine(scratch_database)
    try:
        with engine.connect() as connection:
            raw_item_ids = [
                row[0]
                for row in connection.execute(
                    text("SELECT id FROM acquisition.raw_item ORDER BY fetched_at LIMIT 5")
                ).all()
            ]
            opportunity_count_before = int(
                connection.execute(
                    text("SELECT count(*) FROM opportunities.opportunity")
                ).scalar_one()
            )
            occurrence_count_before = int(
                connection.execute(
                    text("SELECT count(*) FROM opportunities.source_occurrence")
                ).scalar_one()
            )

        assert len(raw_item_ids) == 5

        # Force these five back to "pending" for the current normalizer version, as if
        # the upgrade had just bumped it and a backfill needed to run — the real
        # scenario `docs/38-roadmap-ia-e-busca/fase-17/f17-06-normalizacao-mais-precisa.md`
        # describes ("subir a versão do normalizador reprocessa todo RawItem").
        with engine.begin() as connection:
            for raw_item_id in raw_item_ids:
                connection.execute(
                    text(
                        "DELETE FROM opportunities.normalization_result "
                        "WHERE raw_item_id = :raw_item_id AND normalizer_version = :version"
                    ),
                    {"raw_item_id": raw_item_id, "version": NORMALIZER_VERSION},
                )

        total_processed = 0
        batches = 0
        with Session(engine) as session:
            service = OpportunityService(session)
            # Small batches, one call per simulated restart, until the backlog is empty.
            for _ in range(10):
                batch = service.normalize_pending(limit=2)
                total_processed += batch.processed
                batches += 1
                if batch.processed == 0:
                    break

        assert total_processed == 5, "the backfill must process each pending item exactly once"
        assert batches > 1, "the test must exercise more than one resumed batch"

        with engine.connect() as connection:
            opportunity_count_after = int(
                connection.execute(
                    text("SELECT count(*) FROM opportunities.opportunity")
                ).scalar_one()
            )
            occurrence_count_after = int(
                connection.execute(
                    text("SELECT count(*) FROM opportunities.source_occurrence")
                ).scalar_one()
            )

        # No duplicate opportunities or occurrences: re-normalizing an already-seen raw
        # item finds its existing occurrence by source/external identity and refreshes
        # it in place (`OpportunityService.normalize`), it never creates a second one.
        assert opportunity_count_after == opportunity_count_before
        assert occurrence_count_after == occurrence_count_before

        # Resuming again after the backlog is empty is idempotent: nothing left to do,
        # and nothing gets reprocessed a second time.
        with Session(engine) as session:
            service = OpportunityService(session)
            final = service.normalize_pending(limit=10)
        assert final.processed == 0
    finally:
        engine.dispose()
