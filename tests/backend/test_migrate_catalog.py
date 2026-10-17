"""R55-A2/A3: the catalogue export/import is idempotent, dry-run-safe and owner-aware."""

from __future__ import annotations

import json
import os
import stat
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
                "CAST('{\"board_token\": \"acme\"}' AS jsonb), "
                "true, 'confirmed', now(), true, true)"
            ),
            {"id": ids["ready"], "cs": ids["cs"]},
        )
        c.execute(
            text(
                "INSERT INTO acquisition.source_definition "
                f"(id, source_type, name, configuration, {homologated}) "
                "VALUES (:id, 'lever', 'half-done', CAST('{\"site_identifier\": \"x\"}' AS jsonb), "
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


def test_json_scalars_are_serialized_for_json_columns() -> None:
    assert migrate_catalog._bind(5, "jsonb") == "5"
    assert migrate_catalog._bind("x", "jsonb") == '"x"'
    assert migrate_catalog._bind({"a": 1}, "jsonb") == '{"a": 1}'
    assert migrate_catalog._bind(5, "integer") == 5


def test_rows_with_different_keys_are_refused() -> None:
    writer = migrate_catalog._Writer(None, OWNER)  # type: ignore[arg-type]
    with pytest.raises(SystemExit, match="one set of columns"):
        writer.insert("company_radar.company", [{"id": 1}, {"id": 2, "name": "x"}])


def test_source_identity_uses_the_endpoint_not_the_name() -> None:
    one = migrate_catalog.source_identity("greenhouse", "A", {"board_token": " Acme "})
    two = migrate_catalog.source_identity("greenhouse", "B", {"board_token": "acme", "x": 1})
    assert one == two
    assert one != migrate_catalog.source_identity("greenhouse", "A", {"board_token": "other"})
    assert migrate_catalog.source_identity("manual", "A", {}) != migrate_catalog.source_identity(
        "manual", "B", {}
    )
    assert migrate_catalog.source_identity("workday", "A", {"tenant_identifier": "t"}) != (
        migrate_catalog.source_identity(
            "workday", "A", {"tenant_identifier": "t", "api_region": "wd5"}
        )
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
    assert stat.S_IMODE(export.stat().st_mode) == 0o600
    assert not export.with_suffix(export.suffix + ".part").exists()


@integration
def test_failed_export_leaves_no_partial_file(databases: tuple[str, str], tmp_path: Path) -> None:
    source, _ = databases
    out = tmp_path / "export.jsonl"
    engine = create_database_engine(source)
    with engine.begin() as c:
        c.execute(text("DROP TABLE company_radar.company_startup_evidence"))
    engine.dispose()
    with pytest.raises(Exception):
        migrate_catalog.run_export(out=out, container=None, source_url=source, job_days=7)
    assert list(tmp_path.iterdir()) == []


@integration
def test_dry_run_writes_nothing_and_apply_twice_adds_no_duplicates(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    empty = _counts(target)

    dry = _import(target, export, apply=False, enable_limit=1)
    assert dry["tables"]["acquisition.source_definition"]["inserted"] == 2
    assert _counts(target) == empty

    first = _import(target, export, apply=True, enable_limit=1)
    populated = _counts(target)
    assert populated["acquisition.source_definition"] == 2
    assert populated["company_radar.company"] == 1
    assert populated["acquisition.raw_item"] == 1
    assert populated["acquisition.raw_item_payload"] == 1
    assert populated["acquisition.source_run"] == 1
    assert first["tables"]["acquisition.raw_item"]["inserted"] == 1
    assert first["notes"]["sources_new_enabled"] == 1
    assert first["notes"]["sources_new_disabled"] == 1

    second = _import(target, export, apply=True, enable_limit=1)
    assert _counts(target) == populated
    assert all(v["inserted"] == 0 for v in second["tables"].values())
    assert second["notes"]["sources_preexisting"] == 2


@integration
def test_new_sources_are_disabled_by_default(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    default = _import(target, export, apply=True)
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
    assert states == {"acme-board": False, "half-done": False}
    assert evidence == "confirmed"  # homologation state is preserved while disabled
    # Jobs of sources imported disabled are not migrated.
    assert default["tables"]["acquisition.raw_item"]["inserted"] == 0
    assert default["tables"]["acquisition.source_run"]["inserted"] == 0
    assert default["notes"]["sources_enable_candidates_not_enabled"] == 1

    # Existing rows are never touched, so a later larger limit enables nothing already there.
    again = _import(target, export, apply=True, enable_limit=5)
    assert again["notes"]["sources_preexisting"] == 2
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM acquisition.source_definition WHERE enabled")
            ).scalar_one()
            == 0
        )
    engine.dispose()


@integration
def test_enable_limit_only_enables_homologated_sources(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    _import(target, export, apply=True, enable_limit=5)
    engine = create_database_engine(target)
    with engine.connect() as c:
        states = dict(
            c.execute(text("SELECT name, enabled FROM acquisition.source_definition")).all()
        )
    engine.dispose()
    assert states == {"acme-board": True, "half-done": False}


@integration
def test_synthetic_run_is_backdated_and_counts_inserted_rows(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    _import(target, export, apply=True, enable_limit=1)
    engine = create_database_engine(target)
    with engine.connect() as c:
        row = c.execute(
            text(
                "SELECT items_seen, items_persisted, status, "
                "started_at < now() - interval '2 days' AS old FROM acquisition.source_run"
            )
        ).one()
    engine.dispose()
    assert tuple(row) == (1, 1, "SUCCEEDED", True)


@integration
def test_same_board_under_another_name_is_matched_not_adopted(
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
                "CAST('{\"board_token\":\"ACME\"}' AS jsonb))"
            ),
            {"id": uuid4()},
        )
    engine.dispose()
    export = _export(source, tmp_path, monkeypatch)
    report = _import(target, export, apply=True, enable_limit=5)
    assert report["tables"]["acquisition.source_definition"]["after"] == 2
    assert report["notes"]["sources_matched_other_name"] == 1
    # The pre-existing source is not adopted: no run, no raw items, no probes for it.
    assert report["tables"]["acquisition.raw_item"]["inserted"] == 0
    assert report["tables"]["acquisition.source_run"]["inserted"] == 0


@integration
def test_same_name_with_different_endpoint_is_a_conflict_and_is_skipped(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    engine = create_database_engine(target)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO acquisition.source_definition (id, source_type, name, configuration) "
                "VALUES (:id, 'greenhouse', 'acme-board', "
                "CAST('{\"board_token\":\"another-company\"}' AS jsonb))"
            ),
            {"id": uuid4()},
        )
    export = _export(source, tmp_path, monkeypatch)
    report = _import(target, export, apply=True, enable_limit=5)
    with engine.connect() as c:
        config = c.execute(
            text(
                "SELECT configuration->>'board_token' FROM acquisition.source_definition "
                "WHERE name = 'acme-board'"
            )
        ).scalar_one()
    engine.dispose()
    assert config == "another-company"  # never adopted or modified
    assert report["notes"]["source_conflicts"] == 1
    assert report["tables"]["acquisition.raw_item"]["inserted"] == 0
    assert report["tables"]["acquisition.source_probe"]["inserted"] == 0


@integration
def test_preexisting_company_source_gets_no_revisions(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    engine = create_database_engine(source)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO company_radar.company_source_revision "
                "(id, company_source_id, version, changes, evidence_note) "
                "SELECT :id, id, 1, '{}'::jsonb, 'note' FROM company_radar.company_source"
            ),
            {"id": uuid4()},
        )
    engine.dispose()
    export = _export(source, tmp_path, monkeypatch)
    first = _import(target, export, apply=True)
    assert first["tables"]["company_radar.company_source_revision"]["inserted"] == 1
    engine = create_database_engine(target)
    with engine.begin() as c:
        c.execute(text("DELETE FROM company_radar.company_source_revision"))
    engine.dispose()
    second = _import(target, export, apply=True)
    assert second["tables"]["company_radar.company_source_revision"]["inserted"] == 0
    assert second["notes"]["revisions_skipped_preexisting"] == 1


@integration
def test_company_domain_conflict_is_reported(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, target = databases
    _seed_source_database(source)
    src_engine = create_database_engine(source)
    with src_engine.begin() as c:
        c.execute(text("UPDATE company_radar.company SET domain = 'acme.example'"))
    src_engine.dispose()
    dst_engine = create_database_engine(target)
    with dst_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO company_radar.company (id, canonical_name, normalized_name, domain) "
                "VALUES (:id, 'Acme Inc', 'acme-inc', 'acme.example')"
            ),
            {"id": uuid4()},
        )
    dst_engine.dispose()
    export = _export(source, tmp_path, monkeypatch)
    report = _import(target, export, apply=False)
    assert report["notes"]["company_domain_conflicts"] == 1


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
def test_owner_sub_never_appears_in_output_on_a_database_error(
    databases: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source, target = databases
    _seed_source_database(source)
    export = _export(source, tmp_path, monkeypatch)
    engine = create_database_engine(target)
    with engine.begin() as c:
        # Postgres quotes the failing row (owner included) in its error DETAIL.
        c.execute(
            text(
                "ALTER TABLE company_radar.company ADD COLUMN owner_sub VARCHAR(255) "
                "CHECK (owner_sub = 'nobody')"
            )
        )
    engine.dispose()
    owner_file = tmp_path / "owner.txt"
    owner_file.write_text(OWNER, encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", target)
    code = migrate_catalog.main(
        ["import", "--export", str(export), "--owner-sub-file", str(owner_file), "--apply"]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert OWNER not in captured.out + captured.err
    assert "IntegrityError" in captured.err
    assert _counts(target)["company_radar.company"] == 0


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
