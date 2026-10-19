"""Invalid saved-search filters are a 422 on create and on count, never a 500."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company, CompanyStartupEvidence
from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_development_app
from opportunity_radar.presentation.http.auth import RequestIdentity, authenticated_identity
from opportunity_radar.presentation.http.dependencies import get_session

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


@pytest.fixture
def owner_client() -> Iterator[tuple[TestClient, Session, str]]:
    owner = f"test-f4-{uuid4().hex}"
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        app = create_development_app(Settings(database_url=os.environ["DATABASE_URL"]))
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[authenticated_identity] = lambda: RequestIdentity(
            sub=owner, is_owner=False
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, session, owner


def test_post_saved_search_with_invalid_filter_returns_422(
    owner_client: tuple[TestClient, Session, str],
) -> None:
    client, _, _ = owner_client

    response = client.post("/saved-searches", json={"name": "x", "filters": {"order": 42}})

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_filters"
    assert client.get("/saved-searches").json() == []


def test_new_count_of_legacy_invalid_saved_search_returns_422_not_500(
    owner_client: tuple[TestClient, Session, str],
) -> None:
    client, session, owner = owner_client
    legacy = SavedSearchModel(owner_sub=owner, name="legacy", filters={"order": 42})
    session.add(legacy)
    session.commit()

    response = client.get(f"/saved-searches/{legacy.id}/new-count")

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_filters"
    summary = client.get("/saved-searches/summary").json()
    assert next(i for i in summary if i["id"] == str(legacy.id))["count_error"] == "invalid_filters"


def _http_params(saved_params: dict[str, str]) -> dict[str, str]:
    """What the Inbox page sends for the same URL params (`InboxPage.tsx` useInbox call)."""
    params = {key: value for key, value in saved_params.items() if key != "lens"}
    if saved_params.get("lens") == "novas":
        params["recency_window_days"] = "14"
    if saved_params.get("lens") == "abertas":
        params["open_at_source"] = "true"
    return params


@pytest.mark.parametrize(
    ("params", "expected_total"),
    [
        ({"all_areas": "true"}, 2),
        ({"all_areas": "true", "only_startups": "true"}, 1),
        ({"all_areas": "true", "only_recent": "false"}, 4),
        ({"all_areas": "true", "lens": "novas"}, 2),
        ({"all_areas": "true", "lens": "abertas"}, 2),
        ({"all_areas": "true", "lens": "abertas", "only_startups": "true"}, 1),
    ],
)
def test_saved_search_new_count_equals_inbox_total_for_same_url_params(
    owner_client: tuple[TestClient, Session, str], params: dict[str, str], expected_total: int
) -> None:
    client, session, owner = owner_client
    marker = uuid4().hex[:12]
    now = datetime.now(UTC)
    opened_before_seed = now - timedelta(hours=1)
    company = Company(
        canonical_name=f"Startup {marker}", normalized_name=f"startup {marker}"
    )
    session.add(company)
    session.flush()
    session.add(
        CompanyStartupEvidence(
            company_id=company.id, signal="other", strength="weak", source_text="test"
        )
    )

    def opportunity(label: str, *, age_days: int, startup: bool) -> OpportunityModel:
        return OpportunityModel(
            id=uuid4(),
            fingerprint=uuid4().hex + uuid4().hex,
            fingerprint_version="v1",
            canonical_title=f"Role {label} {marker}",
            normalized_title=f"role {label} {marker}",
            canonical_company_id=company.id if startup else None,
            work_mode="UNKNOWN",
            seniority="UNKNOWN",
            contract_type="UNKNOWN",
            lifecycle_status="ACTIVE",
            published_at=now - timedelta(days=age_days),
            version=1,
        )

    startup_recent = opportunity("a", age_days=1, startup=True)
    startup_old = opportunity("b", age_days=60, startup=True)
    plain_recent = opportunity("c", age_days=1, startup=False)
    plain_old_open = opportunity("d", age_days=90, startup=False)
    opportunities = [startup_recent, startup_old, plain_recent, plain_old_open]
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="manual",
        name=f"parity {marker}",
        enabled=True,
        configuration={},
        rate_limit_policy={},
    )
    session.add(source)
    session.commit()
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="SCHEDULED",
        status="SUCCEEDED",
        started_at=now - timedelta(minutes=30),
        complete=True,
    )
    session.add(run)
    session.add_all(opportunities)
    session.flush()
    raw_ids = []
    for open_item in (startup_recent, plain_old_open):
        raw = RawItemModel(
            id=uuid4(),
            source_run_id=run.id,
            source_definition_id=source.id,
            external_id=f"ext-{uuid4().hex[:8]}",
            identity_key=f"external:{uuid4().hex[:8]}",
            payload_hash=uuid4().hex + uuid4().hex,
            item_metadata={},
        )
        session.add(raw)
        session.flush()
        raw_ids.append(raw.id)
        session.add(
            SourceOccurrenceModel(
                id=uuid4(),
                opportunity_id=open_item.id,
                raw_item_id=raw.id,
                source_definition_id=source.id,
                external_id=raw.external_id,
                first_seen_at=run.started_at,
                last_seen_at=run.started_at,
                last_seen_run_id=run.id,
            )
        )
    saved = SavedSearchModel(
        owner_sub=owner,
        name="parity",
        term=marker,
        filters=params,
        last_opened_at=opened_before_seed,
    )
    session.add(saved)
    session.commit()
    try:
        inbox_total = client.get(
            "/inbox", params={**_http_params(params), "search": marker, "limit": 200}
        ).json()["total"]
        count = client.get(f"/saved-searches/{saved.id}/new-count").json()["new_count"]
        assert inbox_total == expected_total
        assert count == inbox_total
    finally:
        session.execute(delete(SavedSearchModel).where(SavedSearchModel.id == saved.id))
        session.execute(
            delete(SourceOccurrenceModel).where(
                SourceOccurrenceModel.source_definition_id == source.id
            )
        )
        session.execute(
            delete(OpportunityModel).where(OpportunityModel.id.in_([o.id for o in opportunities]))
        )
        session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_ids)))
        session.execute(
            delete(SourceRunModel).where(SourceRunModel.source_definition_id == source.id)
        )
        session.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id))
        session.execute(delete(Company).where(Company.id == company.id))
        session.commit()
