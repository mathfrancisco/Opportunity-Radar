"""R55-A2/A3: the catalogue export/import is idempotent, dry-run-safe and owner-aware."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from opportunity_radar.platform.backup import with_database
from opportunity_radar.platform.database import create_database_engine
from scripts import migrate_catalog
from scripts.restore_check import create_database, drop_database

REPO_ROOT = Path(__file__).resolve().parents[2]
OWNER = "user_synthetic_owner"

integration = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1"
    or os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1",
    reason="catalogue migration tests need the isolated database suite",
)


def test_homologation_gate_matches_the_dashboard_rule() -> None:
    confirmed = {
        "source_type": "greenhouse",
        "evidence_status": "confirmed",
        "reviewed_at": "2026-10-01T00:00:00+00:00",
        "terms_reviewed": True,
        "collector_local_tested": True,
    }
    assert migrate_catalog.is_homologated(confirmed)
    assert not migrate_catalog.is_homologated({**confirmed, "terms_reviewed": False})
    assert not migrate_catalog.is_homologated({**confirmed, "reviewed_at": None})
    assert not migrate_catalog.is_homologated({**confirmed, "evidence_status": "unverified"})
    assert migrate_catalog.is_homologated({"source_type": "manual"})


def test_owner_sub_file_must_not_be_empty(tmp_path: Path) -> None:
    empty = tmp_path / "owner.txt"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(SystemExit):
        migrate_catalog.read_owner_sub(empty)
    empty.write_text(f"{OWNER}\n", encoding="utf-8")
    assert migrate_catalog.read_owner_sub(empty) == OWNER


def _alembic_head(url: str) -> None:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url, "OWNER_SUB_BACKFILL": OWNER},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture
def databases() -> Iterator[tuple[str, str]]:
    """Two scratch databases at head: a stand-in for the local source and the target."""
    admin_url = os.environ["DATABASE_URL"]
    names = [f"r55_catalog_{role}_{uuid4().hex[:10]}_test" for role in ("src", "dst")]
    urls = []
    for name in names:
        create_database(admin_url, name)
        urls.append(with_database(admin_url, name))
        _alembic_head(urls[-1])
    try:
        yield urls[0], urls[1]
    finally:
        for name in names:
            drop_database(admin_url, name)


def _seed_source_database(url: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    ids = {name: uuid4() for name in ("company", "cs", "ready", "unready", "run")}
    engine = create_database_engine(url)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO company_radar.company (id, canonical_name, normalized_name) "
                "VALUES (:id, 'Acme', 'acme')"
            ),
            {"id": ids["company"]},
        )
        c.execute(
            text(
                "INSERT INTO company_radar.company_source "
                "(id, company_id, source_type, endpoint) "
                "VALUES (:id, :company, 'greenhouse', 'https://boards.example/acme')"
            ),
            {"id": ids["cs"], "company": ids["company"]},
        )
        homologated = (
            "enabled, evidence_status, reviewed_at, terms_reviewed, collector_local_tested"
        )
        c.execute(
            text(
                "INSERT INTO acquisition.source_definition "
                f"(id, company_source_id, source_type, name, configuration, {homologated}) "
                "VALUES (:id, :cs, 'greenhouse', 'acme-board', "
                "CAST('{\"board\": \"acme\"}' AS jsonb), true, 'confirmed', now(), true, true)"
            ),
            {"id": ids["ready"], "cs": ids["cs"]},
        )
        c.execute(
            text(
                "INSERT INTO acquisition.source_definition "
                f"(id, source_type, name, configuration, {homologated}) "
                "VALUES (:id, 'lever', 'half-done', CAST('{\"site\": \"x\"}' AS jsonb), "
                "true, 'unverified', NULL, false, false)"
            ),
            {"id": ids["unready"]},
        )
        c.execute(
            text(
                "INSERT INTO acquisition.source_run (id, source_definition_id, status) "
                "VALUES (:id, :source, 'SUCCEEDED')"
            ),
            {"id": ids["run"], "source": ids["ready"]},
        )
        for label, age in (("fresh", 3), ("stale", 8)):
            raw_id = uuid4()
            c.execute(
                text(
                    "INSERT INTO acquisition.raw_item (id, source_run_id, source_definition_id, "
                    "identity_key, payload_hash, fetched_at) "
                    "VALUES (:id, :run, :source, :key, :hash, :fetched)"
                ),
                {
                    "id": raw_id,
                    "run": ids["run"],
                    "source": ids["ready"],
                    "key": f"job-{label}",
                    "hash": uuid4().hex + uuid4().hex,
                    "fetched": now - timedelta(days=age),
                },
            )
            c.execute(
                text(
                    "INSERT INTO acquisition.raw_item_payload (raw_item_id, payload) "
                    "VALUES (:id, CAST('{\"title\": \"role\"}' AS jsonb))"
                ),
                {"id": raw_id},
            )
    engine.dispose()
    return ids


def _counts(url: str) -> dict[str, int]:
    engine = create_database_engine(url)
    try:
        with engine.connect() as c:
            return {
                table: c.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                for table in migrate_catalog.ALL_TABLES
            }
    finally:
        engine.dispose()


def _export(source_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "export.jsonl"
    migrate_catalog.run_export(out=out, container=None, source_url=source_url, job_days=7)
    return out


def _import(target: str, export: Path, **kwargs: Any) -> dict[str, Any]:
    return migrate_catalog.run_import(
        database_url=target, export_path=export, owner_sub=OWNER, **kwargs
    )


@integration
def test_eight_day_old_job_is_excluded_from_the_export(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _ = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    _, tables = migrate_catalog.read_export(export)
    assert [row["identity_key"] for row in tables["acquisition.raw_item"]] == ["job-fresh"]
    assert len(tables["acquisition.raw_item_payload"]) == 1


@integration
def test_dry_run_writes_nothing_and_apply_twice_adds_no_duplicates(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    empty = _counts(target)

    dry = _import(target, export, apply=False)
    assert dry["tables"]["acquisition.source_definition"]["inserted"] == 2
    assert _counts(target) == empty

    first = _import(target, export, apply=True)
    populated = _counts(target)
    assert populated["acquisition.source_definition"] == 2
    assert populated["company_radar.company"] == 1
    assert populated["acquisition.raw_item"] == 1
    assert populated["acquisition.raw_item_payload"] == 1
    assert populated["acquisition.source_run"] == 1
    assert first["tables"]["acquisition.raw_item"]["inserted"] == 1

    second = _import(target, export, apply=True)
    assert _counts(target) == populated
    assert all(v["inserted"] == 0 for v in second["tables"].values())


@integration
def test_sources_arrive_disabled_unless_homologated_and_enabled(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    _import(target, export, apply=True)
    engine = create_database_engine(target)
    with engine.connect() as c:
        states = dict(
            c.execute(text("SELECT name, enabled FROM acquisition.source_definition")).all()
        )
        evidence = c.execute(
            text(
                "SELECT evidence_status FROM acquisition.source_definition "
                "WHERE name = 'acme-board'"
            )
        ).scalar_one()
    engine.dispose()
    assert states == {"acme-board": True, "half-done": False}
    assert evidence == "confirmed"


@integration
def test_all_disabled_flag_disables_everything(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    _import(target, export, apply=True, all_disabled=True)
    engine = create_database_engine(target)
    with engine.connect() as c:
        assert c.execute(
            text("SELECT count(*) FROM acquisition.source_definition WHERE enabled")
        ).scalar_one() == 0
    engine.dispose()


@integration
def test_same_board_under_another_name_is_not_duplicated(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    engine = create_database_engine(target)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO acquisition.source_definition (id, source_type, name, configuration) "
                "VALUES (:id, 'greenhouse', 'renamed-board', "
                "CAST('{\"board\":\"acme\"}' AS jsonb))"
            ),
            {"id": uuid4()},
        )
    engine.dispose()
    export = _export(source, tmp_path, monkeypatch)
    report = _import(target, export, apply=True)
    assert report["tables"]["acquisition.source_definition"]["after"] == 2
    assert report["notes"]["sources_matched_by_config"] == 1
    # Its raw item is adopted by the already-present source rather than lost.
    assert report["tables"]["acquisition.raw_item"]["inserted"] == 1


@integration
def test_owner_sub_is_written_to_migrated_tables_that_carry_it(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)

    plain = _import(target, export, apply=False)
    assert plain["notes"]["owner_sub_tables"] == []  # no catalogue table owns rows at head

    engine = create_database_engine(target)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE company_radar.company ADD COLUMN owner_sub VARCHAR(255)"))
    report = _import(target, export, apply=True)
    with engine.connect() as c:
        owners = c.execute(text("SELECT DISTINCT owner_sub FROM company_radar.company")).all()
    engine.dispose()
    assert report["notes"]["owner_sub_tables"] == ["company_radar.company"]
    assert owners == [(OWNER,)]
    assert OWNER not in json.dumps(report)


@integration
def test_target_not_at_head_is_refused(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    engine = create_database_engine(target)
    with engine.begin() as c:
        c.execute(text("UPDATE public.alembic_version SET version_num = '20261006_0068'"))
    engine.dispose()
    with pytest.raises(SystemExit, match="not head"):
        _import(target, export, apply=True)
    assert _counts(target)["acquisition.source_definition"] == 0
