"""HTTP-level proof for card F20-61's endpoint contract: `/inbox` and `/opportunities`
filter by recency (30 days by default; `recency_window_days` and `open_at_source` lenses,
F48-16), expose an explicit `only_recent` parameter for
the client's "mostrar tudo" toggle, and mark the fallback date as estimated.

`tests/backend/opportunities/test_recency_filter.py` already proves the pure
`recency_decision` calculation directly; this file proves the same behaviour is
reachable through the HTTP contract the frontend (`apps/web`) actually calls.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import recency_basis_of
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

NOW = datetime.now(UTC)


def _opportunity(
    *,
    title: str,
    marker: str,
    published_at: datetime | None,
    recency_exempt_program: bool = False,
    valid_through: datetime | None = None,
    source_updated_at: datetime | None = None,
    recency_basis: str | None = None,
    id: UUID | None = None,
) -> OpportunityModel:
    return OpportunityModel(
        id=id or uuid4(),
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
        contract_type="INTERNSHIP" if recency_exempt_program else "UNKNOWN",
        recency_exempt_program=recency_exempt_program,
        lifecycle_status="ACTIVE",
        published_at=published_at,
        source_updated_at=source_updated_at,
        recency_basis=recency_basis
        or recency_basis_of(published_at=published_at, source_updated_at=source_updated_at).value,
        valid_through=valid_through,
        version=1,
    )


def _cleanup(session: Session, opportunity_ids: list[UUID]) -> None:
    session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
    session.commit()


def test_inbox_filters_by_recency_by_default_and_shows_all_when_toggled_off() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    client = TestClient(create_app(Settings(database_url=database_url)))
    marker = uuid4().hex[:10]

    with Session(engine) as session:
        recent = _opportunity(
            title="Recent Role", marker=marker, published_at=NOW - timedelta(days=1)
        )
        stale = _opportunity(
            title="Stale Role", marker=marker, published_at=NOW - timedelta(days=45)
        )
        program = _opportunity(
            title="Trainee Program",
            marker=marker,
            published_at=NOW - timedelta(days=60),
            recency_exempt_program=True,
        )
        open_deadline = _opportunity(
            title="Open Deadline Role",
            marker=marker,
            published_at=NOW - timedelta(days=45),
            valid_through=NOW + timedelta(days=5),
        )
        estimated = _opportunity(title="Estimated Role", marker=marker, published_at=None)
        session.add_all([recent, stale, program, open_deadline, estimated])
        session.commit()
        ids = {
            "recent": recent.id,
            "stale": stale.id,
            "program": program.id,
            "open_deadline": open_deadline.id,
            "estimated": estimated.id,
        }
        try:
            # Card F20-61 criterion: no `only_recent` param means the server's own
            # default already applies the filter.
            default_response = client.get(
                "/inbox", params={"all_areas": "true", "search": marker}
            )
            assert default_response.status_code == 200
            default_ids = {item["opportunity_id"] for item in default_response.json()["items"]}
            assert str(ids["recent"]) in default_ids
            assert str(ids["program"]) in default_ids
            assert str(ids["open_deadline"]) in default_ids
            assert str(ids["stale"]) not in default_ids
            # `estimated` has no `published_at`; its `first_seen_at` fallback was set at
            # insert time (server_default `now()`), so it is inside the window too.
            assert str(ids["estimated"]) in default_ids

            estimated_item = next(
                item
                for item in default_response.json()["items"]
                if item["opportunity_id"] == str(ids["estimated"])
            )
            assert estimated_item["date_is_estimated"] is True
            recent_item = next(
                item
                for item in default_response.json()["items"]
                if item["opportunity_id"] == str(ids["recent"])
            )
            assert recent_item["date_is_estimated"] is False

            # Explicit `only_recent=false` — the client's "mostrar tudo" toggle — shows
            # every opportunity regardless of age, contract type or `valid_through`.
            all_response = client.get(
                "/inbox",
                params={"all_areas": "true", "search": marker, "only_recent": "false"},
            )
            assert all_response.status_code == 200
            all_ids = {item["opportunity_id"] for item in all_response.json()["items"]}
            assert str(ids["stale"]) in all_ids
            assert all(str(value) in all_ids for value in ids.values())
        finally:
            _cleanup(session, list(ids.values()))


def test_opportunities_list_filters_by_recency_by_default() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    client = TestClient(create_app(Settings(database_url=database_url)))
    marker = uuid4().hex[:10]

    with Session(engine) as session:
        recent = _opportunity(
            title="Recent Catalog Role", marker=marker, published_at=NOW - timedelta(days=1)
        )
        stale = _opportunity(
            title="Stale Catalog Role", marker=marker, published_at=NOW - timedelta(days=45)
        )
        session.add_all([recent, stale])
        session.commit()
        ids = [recent.id, stale.id]
        try:
            default_response = client.get("/opportunities", params={"page_size": 100})
            assert default_response.status_code == 200
            default_ids = {item["id"] for item in default_response.json()["items"]}
            assert str(recent.id) in default_ids
            assert str(stale.id) not in default_ids

            all_response = client.get(
                "/opportunities", params={"page_size": 100, "only_recent": "false"}
            )
            assert all_response.status_code == 200
            all_ids = {item["id"] for item in all_response.json()["items"]}
            assert str(recent.id) in all_ids
            assert str(stale.id) in all_ids
        finally:
            _cleanup(session, ids)


def test_inbox_window_lenses_and_recency_basis() -> None:
    """F48-16: 30-day default on the reference date, 14-day "Novas" lens, and the API
    exposes `recency_basis` (`updated` counts as estimated)."""
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    client = TestClient(create_app(Settings(database_url=database_url)))
    marker = uuid4().hex[:10]

    with Session(engine) as session:
        published_20d = _opportunity(
            title="Published 20d", marker=marker, published_at=NOW - timedelta(days=20)
        )
        # Old published_at would hide it; no published_at + fresh update keeps it in.
        updated_3d = _opportunity(
            title="Updated 3d",
            marker=marker,
            published_at=None,
            source_updated_at=NOW - timedelta(days=3),
        )
        published_45d = _opportunity(
            title="Published 45d", marker=marker, published_at=NOW - timedelta(days=45)
        )
        session.add_all([published_20d, updated_3d, published_45d])
        session.commit()
        ids = [published_20d.id, updated_3d.id, published_45d.id]
        try:
            base = {"all_areas": "true", "search": marker}
            default_items = {
                item["opportunity_id"]: item
                for item in client.get("/inbox", params=base).json()["items"]
            }
            assert str(published_20d.id) in default_items
            assert str(updated_3d.id) in default_items
            assert str(published_45d.id) not in default_items
            assert default_items[str(published_20d.id)]["recency_basis"] == "published"
            assert default_items[str(published_20d.id)]["date_is_estimated"] is False
            assert default_items[str(updated_3d.id)]["recency_basis"] == "updated"
            assert default_items[str(updated_3d.id)]["date_is_estimated"] is True

            novas = {
                item["opportunity_id"]
                for item in client.get(
                    "/inbox", params={**base, "recency_window_days": 14}
                ).json()["items"]
            }
            assert novas == {str(updated_3d.id)}

            detail = client.get(f"/opportunities/{updated_3d.id}").json()
            assert detail["recency_basis"] == "updated"
            assert detail["date_is_estimated"] is True
        finally:
            _cleanup(session, ids)
