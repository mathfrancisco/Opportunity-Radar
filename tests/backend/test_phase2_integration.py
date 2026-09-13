"""Database-backed proof of manual acquisition and immutable raw evidence."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import RawItemModel, SourceRunModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def test_manual_acquisition_is_idempotent_and_visible() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE acquisition.source_definition CASCADE"))

    client = TestClient(create_app(Settings(database_url=database_url)))
    created = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Manual MVP intake",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    )
    assert created.status_code == 201
    source = created.json()
    assert source["source_type"] == "manual"
    assert source["terms_reviewed"] is False
    source_detail = client.get(f"/sources/{source['id']}")
    assert source_detail.status_code == 200
    assert source_detail.json()["name"] == source["name"]

    payload = {
        "correlation_id": "phase-2-ci",
        "inputs": [
            {"kind": "URL", "value": "https://example.com/jobs/backend-1"},
            {"kind": "TEXT", "value": "Remote Python backend position"},
            {
                "kind": "FILE",
                "value": "job.txt",
                "content_base64": "UmVtb3RlIGZpbGUgam9i",
                "content_type": "text/plain",
            },
        ],
    }
    first = client.post(f"/sources/{source['id']}/runs", json=payload)
    repeated = client.post(f"/sources/{source['id']}/runs", json=payload)

    assert first.status_code == 201
    assert first.json()["status"] == "SUCCEEDED"
    assert first.json()["items_seen"] == 3
    assert first.json()["items_persisted"] == 3
    assert repeated.status_code == 201
    assert repeated.json()["items_persisted"] == 0
    assert repeated.json()["items_skipped"] == 3

    runs = client.get(f"/source-runs?source_id={source['id']}")
    assert runs.status_code == 200
    assert runs.json()["total"] == 2
    assert runs.json()["items"][0]["source_name"] == "Manual MVP intake"

    run_detail = client.get(f"/source-runs/{first.json()['id']}")
    assert run_detail.status_code == 200
    assert run_detail.json()["correlation_id"] == "phase-2-ci"

    with Session(engine) as session:
        raw_items = session.scalar(select(func.count(RawItemModel.id)))
        persisted_runs = session.scalar(select(func.count(SourceRunModel.id)))
    assert raw_items == 3
    assert persisted_runs == 2


def test_confirmed_external_source_requires_explicit_activation_gates() -> None:
    database_url = os.environ["DATABASE_URL"]
    client = TestClient(create_app(Settings(database_url=database_url)))
    invalid_policy = client.post(
        "/sources",
        json={
            "source_type": "ashby",
            "name": "CI invalid Ashby policy",
            "configuration": {"board_identifier": "ci-board"},
            "rate_limit_policy": {"unbounded_delay": True},
        },
    )
    assert invalid_policy.status_code == 422

    created = client.post(
        "/sources",
        json={
            "source_type": "ashby",
            "name": "CI Ashby activation",
            "configuration": {
                "board_identifier": "ci-board",
                "company_name": "CI Company",
            },
            "rate_limit_policy": {
                "max_retries": 2,
                "requests_per_second": 0.5,
                "max_retry_delay_seconds": 30,
            },
            "evidence_status": "confirmed",
        },
    )

    assert created.status_code == 201
    source = created.json()
    rejected = client.patch(
        f"/sources/{source['id']}",
        json={
            "enabled": True,
            "terms_reviewed": False,
            "collector_local_tested": True,
            "expected_version": source["version"],
        },
    )
    assert rejected.status_code == 422

    activated = client.patch(
        f"/sources/{source['id']}",
        json={
            "enabled": True,
            "terms_reviewed": True,
            "collector_local_tested": True,
            "reviewed_at": "2026-09-13T12:00:00Z",
            "expected_version": source["version"],
        },
    )
    assert activated.status_code == 200
    assert activated.json()["enabled"] is True
    assert activated.json()["version"] == source["version"] + 1
