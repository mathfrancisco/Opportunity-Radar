"""Database-backed proof of F17-06: the `regions-v1` snapshot on `opportunity`."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel
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


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE acquisition.source_definition, opportunities.opportunity CASCADE")
        )


def test_normalization_fills_allowed_countries_from_remote_brazil_location() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    _reset(engine)
    client = TestClient(create_app(Settings(database_url=database_url)))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Allowed countries fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    collected = client.post(
        f"/sources/{source['id']}/runs",
        json={
            "inputs": [
                {
                    "kind": "URL",
                    "value": "https://example.com/jobs/backend-1",
                    "metadata": {
                        "title": "Backend Engineer",
                        "company_name": "Example Corp",
                        "location_text": "Remote — Brazil",
                    },
                },
            ]
        },
    )
    assert collected.status_code == 201

    normalized = client.post("/opportunities/normalizations/pending?limit=10")
    assert normalized.status_code == 200

    with Session(engine) as session:
        opportunity = session.scalar(select(OpportunityModel))
        assert opportunity is not None
        assert opportunity.allowed_countries == ["BR"]
        assert opportunity.allowed_countries_version == "regions-v1"


def test_normalization_leaves_allowed_countries_unknown_for_an_unrecognizable_location() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    _reset(engine)
    client = TestClient(create_app(Settings(database_url=database_url)))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Allowed countries unknown fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    collected = client.post(
        f"/sources/{source['id']}/runs",
        json={
            "inputs": [
                {
                    "kind": "URL",
                    "value": "https://example.com/jobs/backend-2",
                    "metadata": {
                        "title": "Backend Engineer",
                        "company_name": "Example Corp",
                        "location_text": "São Paulo, SP",
                    },
                },
            ]
        },
    )
    assert collected.status_code == 201

    normalized = client.post("/opportunities/normalizations/pending?limit=10")
    assert normalized.status_code == 200

    with Session(engine) as session:
        opportunity = session.scalar(select(OpportunityModel))
        assert opportunity is not None
        assert opportunity.allowed_countries is None
        assert opportunity.allowed_countries_version is None
