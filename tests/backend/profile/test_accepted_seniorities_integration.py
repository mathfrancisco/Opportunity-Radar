"""F48-13 on the real database: the preference persists, and the seed script is safe."""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_development_app as create_app
from opportunity_radar.profile.models import CareerProfileModel
from scripts.seed_profile_target_areas import SEED_ROLE_FAMILIES, seed

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))


def _session() -> Session:
    return Session(create_database_engine(os.environ["DATABASE_URL"]))


def _lock() -> int:
    with _session() as session:
        return session.scalar(select(CareerProfileModel.version).limit(1)) or 0


def _activate(client: TestClient, preferences: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/profile/versions",
        json={
            "expected_profile_version": _lock(),
            "activate": True,
            "skills": [{"canonical_name": "python"}],
            "preferences": preferences,
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_omitted_preference_defaults_and_explicit_choice_round_trips(client: TestClient) -> None:
    default = _activate(client, {"work_modes": ["REMOTE"]})
    assert default["preferences"]["accepted_seniorities"] == [
        "INTERN",
        "JUNIOR",
        "MID",
        "UNKNOWN",
    ]

    chosen = _activate(client, {"accepted_seniorities": ["MID", "SENIOR"]})
    assert chosen["preferences"]["accepted_seniorities"] == ["MID", "SENIOR"]
    assert client.get("/profile").json()["preferences"]["accepted_seniorities"] == [
        "MID",
        "SENIOR",
    ]

    stated_nothing = _activate(client, {"accepted_seniorities": []})
    assert stated_nothing["preferences"]["accepted_seniorities"] == []


def test_unknown_seniority_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/profile/versions",
        json={
            "expected_profile_version": _lock(),
            "preferences": {"accepted_seniorities": ["WIZARD"]},
        },
    )
    assert response.status_code == 422


def test_seed_dry_run_writes_nothing_and_real_run_never_overwrites(client: TestClient) -> None:
    _activate(client, {"target_role_families": []})
    lock_before = _lock()

    with _session() as session:
        assert seed(session, dry_run=True)["result"] == "would write"
    assert _lock() == lock_before

    with _session() as session:
        assert seed(session, dry_run=False)["result"] == "written"
    active = client.get("/profile").json()
    assert active["preferences"]["target_role_families"] == list(SEED_ROLE_FAMILIES)
    assert active["skills"][0]["canonical_name"] == "python"

    edited = _activate(client, {"target_role_families": ["DESIGN"]})
    lock_after_edit = _lock()
    with _session() as session:
        assert seed(session, dry_run=False)["result"].startswith("skipped")
    assert _lock() == lock_after_edit
    assert client.get("/profile").json()["id"] == edited["id"]
