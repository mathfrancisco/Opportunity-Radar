"""Database-backed proof that a source's cron schedule can be edited over HTTP."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from opportunity_radar.platform.config import Settings
from opportunity_radar.presentation.http.app import create_development_app as create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _client() -> TestClient:
    return TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def _source(client: TestClient) -> dict[str, object]:
    created = client.post(
        "/sources",
        json={
            "source_type": "greenhouse",
            "name": _unique("Schedule board"),
            "configuration": {"board_token": f"sched{uuid4().hex[:8]}"},
            "schedule": "0 0 * * *",
        },
    )
    assert created.status_code == 201
    return created.json()


def test_valid_schedule_is_updated_and_bumps_the_version() -> None:
    client = _client()
    source = _source(client)

    updated = client.patch(
        f"/sources/{source['id']}/schedule",
        json={"schedule": "0 */3 * * *", "expected_version": source["version"]},
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["schedule"] == "0 */3 * * *"
    assert body["version"] == source["version"] + 1


def test_invalid_cron_is_rejected_with_422_and_names_the_field() -> None:
    client = _client()
    source = _source(client)

    rejected = client.patch(
        f"/sources/{source['id']}/schedule",
        json={"schedule": "not a cron", "expected_version": source["version"]},
    )

    assert rejected.status_code == 422
    detail = rejected.json()["detail"]
    assert detail["code"] == "INVALID_CONFIGURATION"
    assert detail["field"] == "schedule"


def test_null_schedule_unschedules_the_source() -> None:
    client = _client()
    source = _source(client)

    updated = client.patch(
        f"/sources/{source['id']}/schedule",
        json={"schedule": None, "expected_version": source["version"]},
    )

    assert updated.status_code == 200
    assert updated.json()["schedule"] is None


def test_unknown_source_is_404() -> None:
    client = _client()

    missing = client.patch(
        f"/sources/{uuid4()}/schedule",
        json={"schedule": "0 0 * * *", "expected_version": 1},
    )

    assert missing.status_code == 404


def test_stale_expected_version_is_a_conflict() -> None:
    client = _client()
    source = _source(client)

    first = client.patch(
        f"/sources/{source['id']}/schedule",
        json={"schedule": "0 */6 * * *", "expected_version": source["version"]},
    )
    assert first.status_code == 200

    stale = client.patch(
        f"/sources/{source['id']}/schedule",
        json={"schedule": "0 */2 * * *", "expected_version": source["version"]},
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
