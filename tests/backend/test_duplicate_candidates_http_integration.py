"""HTTP-level proof for F20-26's remaining scope: the three duplicate-candidate routes,
the Inbox "possível duplicata" flag, and the `created_at` field the side-by-side detail
comparison uses to know which opportunity `confirm_duplicate` will keep as the survivor.

`tests/backend/opportunities/test_duplicates.py` already covers the service functions
directly; this file proves the same behaviour is reachable through the HTTP contract the
frontend (`apps/web`) actually calls.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.duplicates import find_title_location_window_candidates
from opportunity_radar.opportunities.models import DuplicateCandidateModel, OpportunityModel
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

NOW = datetime.now(UTC)


def _opportunity(
    *, created_at: datetime, published_at: datetime | None, title: str, marker: str
) -> OpportunityModel:
    return OpportunityModel(
        id=uuid4(),
        fingerprint=uuid4().hex + uuid4().hex,
        fingerprint_version="v1",
        canonical_title=f"{title} {marker}",
        normalized_title=f"{title.lower()} {marker}",
        normalized_company_name="acme",
        normalized_location="sao paulo",
        company_name="acme",
        location_text="sao paulo",
        work_mode="UNKNOWN",
        seniority="UNKNOWN",
        contract_type="UNKNOWN",
        lifecycle_status="ACTIVE",
        published_at=published_at,
        created_at=created_at,
        version=1,
    )


def _cleanup(session: Session, opportunity_ids: list) -> None:
    session.execute(
        delete(DuplicateCandidateModel).where(
            DuplicateCandidateModel.opportunity_id.in_(opportunity_ids)
            | DuplicateCandidateModel.duplicate_opportunity_id.in_(opportunity_ids)
        )
    )
    session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
    session.commit()


def test_duplicate_candidate_routes_and_inbox_badge() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    client = TestClient(create_app(Settings(database_url=database_url)))
    marker = uuid4().hex[:10]

    with Session(engine) as session:
        older = _opportunity(
            created_at=NOW - timedelta(days=5),
            published_at=NOW,
            title="Duplicate HTTP Role",
            marker=marker,
        )
        newer = _opportunity(
            created_at=NOW,
            published_at=NOW + timedelta(days=1),
            title="Duplicate HTTP Role",
            marker=marker,
        )
        session.add_all([older, newer])
        session.commit()
        [candidate] = find_title_location_window_candidates(session, newer)
        session.commit()
        older_id, newer_id, candidate_id = older.id, newer.id, candidate.id
        try:
            # `GET .../duplicate-candidates` — the endpoint the detail comparison uses.
            listed = client.get(f"/opportunities/{older_id}/duplicate-candidates")
            assert listed.status_code == 200
            items = listed.json()["items"]
            assert len(items) == 1
            assert items[0]["id"] == str(candidate_id)
            assert items[0]["status"] == "PENDING"
            assert {items[0]["opportunity_id"], items[0]["duplicate_opportunity_id"]} == {
                str(older_id),
                str(newer_id),
            }

            # `created_at` on the detail response — what the UI uses to show the older
            # opportunity as the one `confirm_duplicate` would keep.
            older_detail = client.get(f"/opportunities/{older_id}").json()
            newer_detail = client.get(f"/opportunities/{newer_id}").json()
            assert older_detail["created_at"] < newer_detail["created_at"]

            # The Inbox badge: both sides of a PENDING pair are flagged.
            inbox = client.get("/inbox", params={"all_areas": "true", "search": marker})
            assert inbox.status_code == 200
            by_id = {item["opportunity_id"]: item for item in inbox.json()["items"]}
            assert by_id[str(older_id)]["has_pending_duplicate"] is True
            assert by_id[str(newer_id)]["has_pending_duplicate"] is True

            # Confirm: the older opportunity (lower created_at) is the survivor.
            confirmed = client.post(
                f"/opportunities/duplicate-candidates/{candidate_id}/confirm",
                json={
                    "expected_version_survivor": 1,
                    "expected_version_absorbed": 1,
                    "decided_by": "operator@example.com",
                },
            )
            assert confirmed.status_code == 200
            assert confirmed.json()["status"] == "CONFIRMED"

            # A confirmed candidate no longer sets the pending badge.
            inbox_after = client.get(
                "/inbox", params={"all_areas": "true", "search": marker}
            )
            by_id_after = {
                item["opportunity_id"]: item for item in inbox_after.json()["items"]
            }
            assert by_id_after[str(older_id)]["has_pending_duplicate"] is False
            assert by_id_after[str(newer_id)]["has_pending_duplicate"] is False

            # Idempotent retry, same as the service-level test, but through HTTP.
            retried = client.post(
                f"/opportunities/duplicate-candidates/{candidate_id}/confirm",
                json={
                    "expected_version_survivor": 1,
                    "expected_version_absorbed": 1,
                    "decided_by": "operator@example.com",
                },
            )
            assert retried.status_code == 200
            assert retried.json()["status"] == "CONFIRMED"
        finally:
            _cleanup(session, [older_id, newer_id])


def test_reject_duplicate_candidate_via_http_clears_the_inbox_badge() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    client = TestClient(create_app(Settings(database_url=database_url)))
    marker = uuid4().hex[:10]

    with Session(engine) as session:
        first = _opportunity(
            created_at=NOW, published_at=NOW, title="Reject HTTP Role", marker=marker
        )
        second = _opportunity(
            created_at=NOW,
            published_at=NOW + timedelta(days=1),
            title="Reject HTTP Role",
            marker=marker,
        )
        session.add_all([first, second])
        session.commit()
        [candidate] = find_title_location_window_candidates(session, second)
        session.commit()
        first_id, second_id, candidate_id = first.id, second.id, candidate.id
        try:
            rejected = client.post(
                f"/opportunities/duplicate-candidates/{candidate_id}/reject",
                json={"decided_by": "operator@example.com"},
            )
            assert rejected.status_code == 200
            assert rejected.json()["status"] == "REJECTED"

            inbox = client.get("/inbox", params={"all_areas": "true", "search": marker})
            by_id = {item["opportunity_id"]: item for item in inbox.json()["items"]}
            assert by_id[str(first_id)]["has_pending_duplicate"] is False
            assert by_id[str(second_id)]["has_pending_duplicate"] is False

            # Confirming a rejected pair is refused, not silently accepted.
            confirm_after_reject = client.post(
                f"/opportunities/duplicate-candidates/{candidate_id}/confirm",
                json={
                    "expected_version_survivor": 1,
                    "expected_version_absorbed": 1,
                    "decided_by": "operator@example.com",
                },
            )
            assert confirm_after_reject.status_code == 422
        finally:
            _cleanup(session, [first_id, second_id])


def test_confirm_unknown_candidate_returns_404() -> None:
    database_url = os.environ["DATABASE_URL"]
    client = TestClient(create_app(Settings(database_url=database_url)))
    missing = client.post(
        "/opportunities/duplicate-candidates/00000000-0000-0000-0000-000000000000/confirm",
        json={
            "expected_version_survivor": 1,
            "expected_version_absorbed": 1,
            "decided_by": "operator@example.com",
        },
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "duplicate_candidate_not_found"
