"""F48-06/07: the funnel endpoint and the `/source-health` collection alarm over HTTP."""

from __future__ import annotations

import os

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


def test_funnel_metrics_endpoint_answers_stages_north_star_and_guards() -> None:
    response = _client().get("/funnel-metrics")

    assert response.status_code == 200
    body = response.json()
    assert [stage["key"] for stage in body["stages"]][:3] == [
        "sources_enabled",
        "sources_collected",
        "raw_items",
    ]
    assert body["north_star"]["stock"] >= body["north_star"]["new_in_window"] >= 0
    assert "unique_company_title" in body["north_star"]["stack"]
    assert "sources_on_schedule" in body["guards"]
    assert "false_closures" in body["not_measured"]


def test_source_health_carries_the_collection_gap_and_run_telemetry_fields() -> None:
    response = _client().get("/source-health")

    assert response.status_code == 200
    body = response.json()
    gap = body["collection_gap"]
    assert set(gap) >= {"alarming", "global_overdue", "factor", "overdue_sources"}
    assert gap["overdue_sources"] == sum(item["collection_overdue"] for item in body["items"])
    for item in body["items"]:
        assert "last_run_bytes_received" in item
        assert "last_run_newest_item_age_seconds" in item
