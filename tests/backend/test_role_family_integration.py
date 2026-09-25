"""Database-backed proof of F17-02: persisted classification and retroactive job."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.service import reclassify_role_families
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


def test_new_normalization_persists_area_evidence_and_version() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    _reset(engine)
    client = TestClient(create_app(Settings(database_url=database_url)))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Role family fixture",
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
                    "value": "https://example.com/jobs/data-eng-1",
                    "metadata": {
                        "title": "Data Engineer",
                        "company_name": "Example Corp",
                        "location_text": "Remote",
                        "department": "Data",
                    },
                },
            ]
        },
    )
    assert collected.status_code == 201

    normalized = client.post("/opportunities/normalizations/pending?limit=10")
    assert normalized.status_code == 200

    page = client.get("/opportunities")
    opportunity = page.json()["items"][0]
    assert opportunity["role_family"] == "DATA"
    assert opportunity["role_family_version"] == "role-family-v1"
    assert opportunity["role_family_evidence"]["rule"]


def test_reclassify_role_families_updates_only_stale_rows() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    _reset(engine)
    with Session(engine) as session:
        # Simulates a row from before this card: UNKNOWN, no version, a classifiable title.
        legacy = OpportunityModel(
            fingerprint="legacy-fingerprint",
            fingerprint_version="v1",
            canonical_title="Account Executive",
            normalized_title="account executive",
            work_mode="UNKNOWN",
            seniority="UNKNOWN",
            contract_type="UNKNOWN",
            lifecycle_status="ACTIVE",
            version=1,
            role_family="UNKNOWN",
            role_family_version=None,
        )
        already_current = OpportunityModel(
            fingerprint="current-fingerprint",
            fingerprint_version="v1",
            canonical_title="Backend Engineer",
            normalized_title="backend engineer",
            work_mode="UNKNOWN",
            seniority="UNKNOWN",
            contract_type="UNKNOWN",
            lifecycle_status="ACTIVE",
            version=1,
            role_family="SOFTWARE_ENGINEERING",
            role_family_version="role-family-v1",
            role_family_evidence={"rule": "title", "term": "engineer", "origin": "title"},
        )
        session.add_all([legacy, already_current])
        session.commit()
        legacy_id, current_id = legacy.id, already_current.id

        report = reclassify_role_families(session)
        assert report["total"] == 1
        assert report["updated"] == 1

        session.expire_all()
        reclassified = session.get(OpportunityModel, legacy_id)
        assert reclassified.role_family == "SALES"
        assert reclassified.role_family_version == "role-family-v1"

        # The already-current row was not touched a second time.
        untouched = session.get(OpportunityModel, current_id)
        assert untouched.role_family_evidence == {
            "rule": "title",
            "term": "engineer",
            "origin": "title",
        }

        # Re-running is a no-op: nothing left on a stale version.
        assert reclassify_role_families(session)["total"] == 0
