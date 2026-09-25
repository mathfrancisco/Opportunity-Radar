"""Editing one preference must never erase the rest of the profile (card F18-07).

The tests run on top of whatever profile the database already holds: they read the
current lock instead of truncating, and they read version state from the tables, since
other suites seed bare versions the listing endpoint was never meant to serve.
"""

from __future__ import annotations

import os
from functools import cache
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    ProfileSnapshot,
    ProfileVersionStatus,
    Skill,
)
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_FULL_PROFILE: dict[str, Any] = {
    "skills": [
        {
            "canonical_name": "Python",
            "level": "advanced",
            "last_used_at": "2026-08-01",
            "experience_months": 60,
        },
        {
            "canonical_name": "React",
            "level": "intermediate",
            "last_used_at": "2025-12-01",
            "experience_months": 24,
        },
    ],
    "experiences": [
        {
            "company_name": "Acme",
            "title": "Backend Engineer",
            "started_on": "2022-01-01",
            "ended_on": "2024-06-30",
            "summary": "Payments APIs.",
        },
        {
            "company_name": "Globex",
            "title": "Staff Engineer",
            "started_on": "2024-07-01",
        },
    ],
    "projects": [
        {
            "name": "Radar",
            "started_on": "2025-01-01",
            "description": "Job radar.",
            "url": "https://example.com/radar",
        }
    ],
    "preferences": {
        "work_modes": ["REMOTE"],
        "contracts": ["FULL_TIME"],
        "countries": ["BR"],
        "timezone_start_hour": 9,
        "timezone_end_hour": 18,
        "compensation_min": "100000",
        "compensation_currency": "USD",
        "compensation_period": "YEAR",
        "target_role_families": ["SOFTWARE_ENGINEERING", "DATA"],
    },
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(database_url=os.environ["DATABASE_URL"])))


@cache
def _engine() -> Engine:
    return create_database_engine(os.environ["DATABASE_URL"])


def _session() -> Session:
    return Session(_engine())


def _lock() -> int:
    with _session() as session:
        return session.scalar(select(CareerProfileModel.version).limit(1)) or 0


def _version_states() -> tuple[int, list[tuple[UUID, str]]]:
    """What a failed write must not change: the lock, which versions exist and their status."""
    with _session() as session:
        rows = session.execute(
            select(ProfileVersionModel.id, ProfileVersionModel.status).order_by(
                ProfileVersionModel.number
            )
        ).all()
    return _lock(), [(row.id, row.status) for row in rows]


def _activate_full_profile(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/profile/versions",
        json={"expected_profile_version": _lock(), "activate": True, **_FULL_PROFILE},
    )
    assert response.status_code == 201, response.text
    active: dict[str, Any] = response.json()
    assert active["status"] == "ACTIVE"
    return active


def _edit(client: TestClient, base: dict[str, Any], changes: dict[str, Any]) -> httpx.Response:
    return client.post(
        "/profile/versions",
        json={
            "expected_profile_version": base["profile_lock_version"],
            "base_version_id": base["id"],
            "activate": True,
            **changes,
        },
    )


def _sorted(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    # The API does not promise an order for skills, experiences or projects.
    return sorted(items, key=lambda item: str(item[key]))


def _skill(version: dict[str, Any], name: str) -> dict[str, Any]:
    return next(skill for skill in version["skills"] if skill["canonical_name"] == name)


def test_changing_only_countries_preserves_the_rest_of_the_profile(client: TestClient) -> None:
    base = _activate_full_profile(client)
    assert _skill(base, "python")["last_used_at"] == "2026-08-01"

    # What an older client sends: skill names only, no experiences, projects or dates.
    response = _edit(
        client,
        base,
        {
            "skills": [{"canonical_name": "Python"}, {"canonical_name": "react"}],
            "preferences": {"countries": ["PT"]},
        },
    )

    assert response.status_code == 201, response.text
    edited = response.json()
    assert edited["status"] == "ACTIVE"
    assert edited["id"] != base["id"]
    assert edited["number"] == base["number"] + 1
    # Create, publish and activate are one write: the lock moves once.
    assert edited["profile_lock_version"] == base["profile_lock_version"] + 1
    assert _sorted(edited["skills"], "canonical_name") == _sorted(base["skills"], "canonical_name")
    assert _sorted(edited["experiences"], "company_name") == _sorted(
        base["experiences"], "company_name"
    )
    assert edited["projects"] == base["projects"]
    assert edited["preferences"] == {**base["preferences"], "countries": ["PT"]}
    assert client.get("/profile").json()["id"] == edited["id"]

    # The previous version is archived, not rewritten: still readable, exactly as it was.
    with _session() as session:
        previous = ProfileService(session).get_version(UUID(base["id"]))
    assert previous.status is ProfileVersionStatus.ARCHIVED
    assert previous.snapshot.preferences.countries == ("BR",)
    assert len(previous.snapshot.experiences) == 2


def test_explicit_empty_or_null_values_clear_what_they_name(client: TestClient) -> None:
    base = _activate_full_profile(client)

    response = _edit(
        client,
        base,
        {
            "skills": [
                {"canonical_name": "python", "last_used_at": None},
                {"canonical_name": "react"},
            ],
            "experiences": [],
            "projects": [],
            "preferences": {"target_role_families": []},
        },
    )

    assert response.status_code == 201, response.text
    edited = response.json()
    assert edited["experiences"] == []
    assert edited["projects"] == []
    assert edited["preferences"] == {**base["preferences"], "target_role_families": []}
    assert _skill(edited, "python") == {**_skill(base, "python"), "last_used_at": None}
    assert _skill(edited, "react") == _skill(base, "react")


def test_a_refused_save_leaves_no_version_and_keeps_the_active_one(client: TestClient) -> None:
    base = _activate_full_profile(client)
    before = _version_states()

    invalid = _edit(
        client,
        base,
        {
            "experiences": [
                {
                    "company_name": "Acme",
                    "title": "Engineer",
                    "started_on": "2024-02-01",
                    "ended_on": "2024-01-01",
                }
            ]
        },
    )
    stale = _edit(
        client,
        {**base, "profile_lock_version": base["profile_lock_version"] - 1},
        {"preferences": {"countries": ["PT"]}},
    )

    assert invalid.status_code == 422
    assert stale.status_code == 409
    assert _version_states() == before
    assert client.get("/profile").json()["id"] == base["id"]


def test_a_failure_after_the_draft_rolls_the_whole_write_back(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _activate_full_profile(client)
    before = _version_states()

    def fail(self: ProfileService, version: ProfileVersionModel) -> None:
        raise RuntimeError("activation failed")

    monkeypatch.setattr(ProfileService, "_mark_active", fail)
    snapshot = ProfileSnapshot(
        skills=(Skill("python"),),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(countries=("PT",)),
    )
    with _session() as session:
        with pytest.raises(RuntimeError, match="activation failed"):
            ProfileService(session).create_active_version(snapshot, base["profile_lock_version"])
        # A later commit by the same caller must find nothing of the failed write to persist.
        session.commit()

    assert _version_states() == before
    assert client.get("/profile").json()["id"] == base["id"]


def test_second_edit_from_the_same_version_conflicts_and_loses_nothing(
    client: TestClient,
) -> None:
    base = _activate_full_profile(client)
    before = _version_states()

    first = _edit(client, base, {"preferences": {"countries": ["PT"]}})
    second = _edit(client, base, {"preferences": {"work_modes": ["HYBRID"]}})

    assert first.status_code == 201, first.text
    assert second.status_code == 409
    assert "another edit" in second.json()["detail"]
    active = client.get("/profile").json()
    assert active["id"] == first.json()["id"]
    assert active["preferences"]["countries"] == ["PT"]
    assert active["preferences"]["work_modes"] == ["REMOTE"]
    assert len(active["experiences"]) == 2
    assert len(active["projects"]) == 1
    assert len(_version_states()[1]) == len(before[1]) + 1


def test_target_role_families_round_trip_and_refuse_unknown_codes(client: TestClient) -> None:
    base = _activate_full_profile(client)
    families = ["SOFTWARE_ENGINEERING", "DATA"]
    assert base["preferences"]["target_role_families"] == families
    assert client.get("/profile").json()["preferences"]["target_role_families"] == families
    before = _version_states()

    # UNKNOWN is not a preference, an invented code is refused, and a repeat is a mistake.
    for refused in (["UNKNOWN"], ["ENGINEERING"], ["DATA", "DATA"]):
        response = _edit(client, base, {"preferences": {"target_role_families": refused}})
        assert response.status_code == 422, refused

    assert _version_states() == before


def test_an_unknown_base_version_is_not_found(client: TestClient) -> None:
    before = _version_states()

    response = client.post(
        "/profile/versions",
        json={
            "expected_profile_version": _lock(),
            "base_version_id": str(uuid4()),
            "activate": True,
        },
    )

    assert response.status_code == 404
    assert _version_states() == before
