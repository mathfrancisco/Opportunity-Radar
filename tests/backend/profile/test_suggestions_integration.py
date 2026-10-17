"""R55-D4 on the real database: suggestions are read-only and owner-scoped."""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine
from tests.backend.support.auth import authenticated_test_client

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

OTHER_OWNER = "user_other_synthetic"


@pytest.fixture
def client() -> TestClient:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        session.execute(
            text(
                "TRUNCATE profile.career_profile, acquisition.source_definition, "
                "opportunities.opportunity, opportunities.relevance_mark CASCADE"
            )
        )
        session.commit()
    return authenticated_test_client(os.environ["DATABASE_URL"])


def _opportunity(client: TestClient, title: str) -> str:
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": f"Suggestion fixture {title}",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    metadata = {
        "title": title,
        "company_name": "Example Corp",
        "location_text": "Remote",
        "employment_type": "full-time",
    }
    url = f"https://example.com/jobs/{title.replace(' ', '-').lower()}"
    collected = client.post(
        f"/sources/{source['id']}/runs",
        json={"inputs": [{"kind": "URL", "value": url, "metadata": metadata}]},
    )
    assert collected.status_code == 201
    assert client.post("/opportunities/normalizations/pending?limit=10").status_code == 200
    page = client.get("/opportunities", params={"page_size": 100}).json()
    return str(next(item["id"] for item in page["items"] if item["title"] == title))


def _profile(client: TestClient, accepted: list[str]) -> dict[str, Any]:
    current = client.get("/profile")
    lock = current.json()["profile_lock_version"] if current.status_code == 200 else 0
    response = client.post(
        "/profile/versions",
        json={
            "expected_profile_version": lock,
            "activate": True,
            "skills": [{"canonical_name": "python"}],
            "preferences": {"accepted_seniorities": accepted},
        },
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_marks_become_a_read_only_suggestion_for_their_owner_only(client: TestClient) -> None:
    assert client.get("/profile/suggestions").json() == {"min_marks": 2, "suggestions": []}
    _profile(client, ["MID", "SENIOR"])
    first = _opportunity(client, "Senior Backend Engineer Alpha")
    second = _opportunity(client, "Senior Backend Engineer Beta")

    for opportunity_id in (first, second):
        marked = client.post(
            f"/opportunities/{opportunity_id}/relevance",
            json={"relevant": False, "reason": "SENIORITY"},
        )
        assert marked.status_code == 200

    versions_before = client.get("/profile/versions").json()
    suggestions = client.get("/profile/suggestions").json()
    assert suggestions["suggestions"] == [
        {"kind": "REMOVE_SENIORITY", "value": "SENIOR", "marks": 2}
    ]

    # Never automatic: reading a suggestion changes neither the active version nor the history.
    assert client.get("/profile/versions").json() == versions_before
    assert client.get("/profile").json()["preferences"]["accepted_seniorities"] == [
        "MID",
        "SENIOR",
    ]

    # The marks belong to their owner: another one sees no suggestion from them.
    other = authenticated_test_client(os.environ["DATABASE_URL"], owner_sub=OTHER_OWNER)
    assert other.get("/profile/suggestions").json()["suggestions"] == []


def test_the_latest_mark_decides_and_a_relevant_mark_withdraws_the_complaint(
    client: TestClient,
) -> None:
    _profile(client, ["MID", "SENIOR"])
    first = _opportunity(client, "Senior Data Engineer Gamma")
    second = _opportunity(client, "Senior Data Engineer Delta")
    for opportunity_id in (first, second):
        client.post(
            f"/opportunities/{opportunity_id}/relevance",
            json={"relevant": False, "reason": "SENIORITY"},
        )
    assert len(client.get("/profile/suggestions").json()["suggestions"]) == 1

    client.post(f"/opportunities/{second}/relevance", json={"relevant": True})

    assert client.get("/profile/suggestions").json()["suggestions"] == []
