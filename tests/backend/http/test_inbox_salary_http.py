"""The /inbox salary contract: a bound needs a currency and a period (D1)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
def client() -> Iterator[TestClient]:
    owner = f"test-d1-{uuid4().hex}"
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        app = create_development_app(Settings(database_url=os.environ["DATABASE_URL"]))
        app.dependency_overrides[get_session] = lambda: session
        app.dependency_overrides[authenticated_identity] = lambda: RequestIdentity(
            sub=owner, is_owner=False
        )
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client


@pytest.mark.parametrize(
    "params",
    [
        {"salary_min": "5000"},
        {"salary_max": "5000"},
        {"salary_min": "5000", "salary_currency": "BRL"},
        {"salary_min": "5000", "salary_period": "MONTH"},
        {"salary_min": "5000", "salary_currency": "reais", "salary_period": "MONTH"},
        {"salary_min": "5000", "salary_currency": "brl", "salary_period": "MONTH"},
        {"salary_min": "5000", "salary_currency": "BRL", "salary_period": "UNKNOWN"},
        {"salary_min": "5000", "salary_currency": "BRL", "salary_period": "FORTNIGHT"},
    ],
)
def test_inbox_rejects_an_incomplete_or_invalid_salary_unit(
    client: TestClient, params: dict[str, str]
) -> None:
    response = client.get("/inbox", params={"all_areas": "true", **params})

    assert response.status_code == 422


def test_inbox_accepts_a_complete_salary_unit_and_exposes_salary_match(
    client: TestClient,
) -> None:
    response = client.get(
        "/inbox",
        params={
            "all_areas": "true",
            "only_recent": "false",
            "salary_min": "5000",
            "salary_currency": "BRL",
            "salary_period": "MONTH",
        },
    )

    assert response.status_code == 200
    assert all(item["salary_match"] in {"matched", "unknown"} for item in response.json()["items"])


def test_inbox_without_salary_filter_has_null_salary_match(client: TestClient) -> None:
    response = client.get("/inbox", params={"all_areas": "true", "only_recent": "false"})

    assert response.status_code == 200
    assert all(item["salary_match"] is None for item in response.json()["items"])
