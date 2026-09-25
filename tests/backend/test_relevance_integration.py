"""Database-backed proof of relevance marking, /search-metrics, and the reference script.

Card F17-01: the operator marks a vaga relevant or not (history append-only, current mark
is the latest), the /search-metrics endpoint reports coverage and precision with `null`
where there is not enough data, and the reference script round-trips an opportunity id
through its canonical URL.
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from scripts.search_reference import add_relevant, canonical_url, resolve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _create_opportunity(client: TestClient, *, url: str, title: str) -> dict:
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": f"Relevance fixture {url}",
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
    collected = client.post(
        f"/sources/{source['id']}/runs",
        json={"inputs": [{"kind": "URL", "value": url, "metadata": metadata}]},
    )
    assert collected.status_code == 201
    normalized = client.post("/opportunities/normalizations/pending?limit=10")
    assert normalized.status_code == 200
    page = client.get("/opportunities", params={"page_size": 100})
    return next(item for item in page.json()["items"] if item["title"] == title)


def test_relevance_mark_history_and_current_and_precision(tmp_path) -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE acquisition.source_definition, "
                "opportunities.opportunity, opportunities.relevance_mark CASCADE"
            )
        )

    client = TestClient(create_app(Settings(database_url=database_url)))

    relevant_job = _create_opportunity(
        client, url="https://example.com/jobs/relevance-1", title="Relevant Role"
    )
    irrelevant_job = _create_opportunity(
        client, url="https://example.com/jobs/relevance-2", title="Irrelevant Role"
    )

    # No marks yet: precision is null, not a frail number.
    metrics = client.get("/search-metrics", params={"window": "7d"}).json()
    assert metrics["precision"]["marked_count"] == 0
    assert metrics["precision"]["precision"] is None

    # History is append-only; the current mark is the latest.
    first = client.post(
        f"/opportunities/{relevant_job['id']}/relevance",
        json={"relevant": False, "reason": "AREA"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/opportunities/{relevant_job['id']}/relevance",
        json={"relevant": True},
    )
    assert second.status_code == 200
    assert second.json()["relevant"] is True
    assert second.json()["id"] != first.json()["id"]

    detail = client.get(f"/opportunities/{relevant_job['id']}").json()
    assert detail["relevance_mark"]["relevant"] is True

    client.post(
        f"/opportunities/{irrelevant_job['id']}/relevance",
        json={"relevant": False, "reason": "SENIORITY"},
    )

    metrics = client.get("/search-metrics", params={"window": "7d"}).json()
    assert metrics["precision"]["marked_count"] == 2
    assert metrics["precision"]["relevant_count"] == 1
    assert metrics["precision"]["precision"] == "0.5"

    # Invalid reasons are rejected, not silently accepted.
    invalid = client.post(
        f"/opportunities/{relevant_job['id']}/relevance",
        json={"relevant": False, "reason": "NOT_A_REASON"},
    )
    assert invalid.status_code == 422

    # 404 on an opportunity that does not exist.
    missing = client.post(
        "/opportunities/00000000-0000-0000-0000-000000000000/relevance",
        json={"relevant": True},
    )
    assert missing.status_code == 404

    # Reference script round-trips an opportunity id through its canonical URL.
    reference_path = tmp_path / "queries.json"
    with Session(engine) as session:
        opportunity_id = UUID(relevant_job["id"])
        url_before = canonical_url(session, opportunity_id)
        assert url_before is not None
        add_relevant(
            session,
            query="vaga relevante de teste",
            opportunity_id=opportunity_id,
            path=reference_path,
        )
        resolved = resolve(session, reference_path)
        entry = next(item for item in resolved if item["query"] == "vaga relevante de teste")
        assert entry["unresolved"] == []
        assert entry["relevant"][0]["opportunity_id"] == str(opportunity_id)
