"""Invalid saved-search filters are a 422 on create and on count, never a 500."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.models import SavedSearchModel
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
