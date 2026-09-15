"""Database-backed proof of normalization, dedupe, provenance, and lifecycle."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import NormalizationResultModel
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


def test_normalizes_and_deduplicates_manual_evidence_with_provenance() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE acquisition.source_definition CASCADE"))

    client = TestClient(create_app(Settings(database_url=database_url)))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Opportunity normalization fixture",
            "enabled": True,
            "evidence_status": "confirmed",
            "collector_local_tested": True,
        },
    ).json()
    canonical_metadata = {
        "title": "Senior Backend Engineer",
        "company_name": "Example Corp",
        "location_text": "Remote",
        "employment_type": "full-time",
        "salaryRange": {"min": 100000, "max": 150000, "currency": "USD"},
        "skills": ["Python", "ReactJS"],
    }
    collected = client.post(
        f"/sources/{source['id']}/runs",
        json={
            "inputs": [
                {
                    "kind": "URL",
                    "value": "https://example.com/jobs/backend-1?utm_source=manual",
                    "metadata": canonical_metadata,
                },
                {
                    "kind": "TEXT",
                    "value": "Original remote backend role description",
                    "metadata": canonical_metadata,
                },
                {
                    "kind": "FILE",
                    "value": "legacy-job.txt",
                    "content_base64": (
                        "T3JpZ2luYWwgcmVtb3RlIGJhY2tlbmQg"
                        "cm9sZSBkZXNjcmlwdGlvbg=="
                    ),
                    "content_type": "text/plain",
                    "metadata": canonical_metadata,
                },
                {
                    "kind": "URL",
                    "value": "https://example.com/jobs/missing-title",
                },
            ]
        },
    )
    assert collected.status_code == 201
    assert collected.json()["items_persisted"] == 4

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE acquisition.raw_item "
                "SET metadata = metadata - 'collected_item_v1' "
                "WHERE canonical_url LIKE 'https://example.com/jobs/backend-1%' "
                "OR payload->>'filename' = 'legacy-job.txt'"
            )
        )

    normalized = client.post("/opportunities/normalizations/pending?limit=10")
    assert normalized.status_code == 200
    assert normalized.json() == {
        "processed": 4,
        "succeeded": 3,
        "review_required": 0,
        "failed": 1,
    }

    page = client.get("/opportunities")
    assert page.status_code == 200
    assert page.json()["total"] == 1
    opportunity = page.json()["items"][0]
    assert opportunity["fingerprint_version"] == "v1"
    assert opportunity["work_mode"] == "REMOTE"
    assert opportunity["seniority"] == "SENIOR"
    assert opportunity["contract_type"] == "FULL_TIME"
    assert len(opportunity["compensations"]) == 3
    assert all(
        Decimal(item["minimum"]) == Decimal("100000")
        for item in opportunity["compensations"]
    )
    assert all(
        Decimal(item["maximum"]) == Decimal("150000")
        for item in opportunity["compensations"]
    )
    assert all(item["currency"] == "USD" for item in opportunity["compensations"])
    assert all(item["period"] == "UNKNOWN" for item in opportunity["compensations"])
    assert {item["canonical_name"] for item in opportunity["skills"]} == {
        "python",
        "react",
    }
    assert all(item["taxonomy_version"] == "skills-v1" for item in opportunity["skills"])
    assert len(opportunity["occurrences"]) == 3
    assert {item["raw_item_id"] for item in opportunity["occurrences"]}

    detail = client.get(f"/opportunities/{opportunity['id']}")
    assert detail.status_code == 200
    decisions = {
        item["identity_decision"]
        for item in detail.json()["normalization_results"]
    }
    assert decisions == {"NEW", "MERGED"}
    assert all(
        len(item["evidence"]) == 3 for item in detail.json()["skills"]
    )

    with Session(engine) as session:
        succeeded_raw_item_id = session.scalar(
            select(NormalizationResultModel.raw_item_id)
            .where(NormalizationResultModel.status == "SUCCEEDED")
            .limit(1)
        )
        failed = session.scalar(
            select(NormalizationResultModel).where(
                NormalizationResultModel.status == "FAILED"
            )
        )
    assert succeeded_raw_item_id is not None
    repeated = client.post(
        f"/opportunities/normalizations/{succeeded_raw_item_id}"
    )
    assert repeated.status_code == 200
    assert repeated.json()["result"]["identity_decision"] in {"NEW", "MERGED"}
    assert failed is not None
    assert failed.opportunity_id is None

    activated = client.patch(
        f"/opportunities/{opportunity['id']}/status",
        json={"status": "ACTIVE", "expected_version": opportunity["version"]},
    )
    assert activated.status_code == 200
    assert activated.json()["lifecycle_status"] == "ACTIVE"
    stale_write = client.patch(
        f"/opportunities/{opportunity['id']}/status",
        json={"status": "CLOSED", "expected_version": opportunity["version"]},
    )
    assert stale_write.status_code == 409
    invalid_transition = client.patch(
        f"/opportunities/{opportunity['id']}/status",
        json={"status": "REJECTED", "expected_version": activated.json()["version"]},
    )
    assert invalid_transition.status_code == 422
