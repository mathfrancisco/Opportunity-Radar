from __future__ import annotations

from pathlib import Path

import yaml

from scripts.check_tenancy_release_gate import owner_scoped_api_is_proven


def test_tenancy_release_gate_blocks_until_explicitly_enabled() -> None:
    assert not owner_scoped_api_is_proven(None)
    assert not owner_scoped_api_is_proven("")
    assert not owner_scoped_api_is_proven("false")
    assert not owner_scoped_api_is_proven("yes")
    assert not owner_scoped_api_is_proven("1")


def test_tenancy_release_gate_accepts_only_explicit_true() -> None:
    assert owner_scoped_api_is_proven("true")
    assert owner_scoped_api_is_proven(" TRUE ")


def test_owner_backfill_is_empty_by_default_and_only_reaches_migrate() -> None:
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["migrate"]["environment"]["OWNER_SUB_BACKFILL"] == "${OWNER_SUB_BACKFILL:-}"
    for service in ("api", "worker", "frontend"):
        assert "OWNER_SUB_BACKFILL" not in services[service].get("environment", {})


def test_ci_overlay_uses_only_synthetic_owner_and_test_database() -> None:
    compose = yaml.safe_load(Path("compose.ci.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    database_url = (
        "postgresql+psycopg://opportunity_radar:ci-password@postgres:5432/"
        "opportunity_radar_test"
    )

    assert services["postgres"]["environment"]["POSTGRES_DB"] == "opportunity_radar_test"
    assert services["migrate"]["environment"]["OWNER_SUB_BACKFILL"] == "ci-owner-sub"
    for service in ("migrate", "api", "worker"):
        assert services[service]["environment"]["DATABASE_URL"] == database_url
    for service in ("api", "worker", "frontend"):
        assert "OWNER_SUB_BACKFILL" not in services.get(service, {}).get("environment", {})


def test_publish_job_runs_release_gate_before_registry_login_or_image_push() -> None:
    workflow = yaml.safe_load(
        Path(".github/workflows/pipeline.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["publish"]["steps"]
    gate_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "python scripts/check_tenancy_release_gate.py"
    )
    login_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "Log in to GHCR"
    )
    publish_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "Build and publish image"
    )

    assert "${{ vars.TENANCY_OWNER_API_READY }}" in steps[gate_index]["env"][
        "TENANCY_OWNER_API_READY"
    ]
    assert gate_index < login_index < publish_index
