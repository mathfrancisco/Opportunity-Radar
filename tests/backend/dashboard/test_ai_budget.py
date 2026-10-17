"""Card R55-C6: `GET /ai-budget` answers today requests and tokens per route model."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from tests.backend.support.auth import authenticated_test_client

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def test_the_endpoint_lists_every_route_model_with_the_1000_a_day_limit() -> None:
    settings = Settings(database_url=os.environ["DATABASE_URL"])
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_quota_usage"))
        connection.execute(
            text(
                "INSERT INTO platform.ai_quota_usage "
                "(model, window_kind, window_start, requests, tokens, updated_at) "
                "VALUES (:model, 'day', date_trunc('day', now() AT TIME ZONE 'UTC') "
                "AT TIME ZONE 'UTC', 120, 40000, now())"
            ),
            {"model": settings.groq_reasoning_model},
        )
    client = authenticated_test_client(
        owner_sub="ai-budget-test-owner", database_url=os.environ["DATABASE_URL"]
    )

    response = client.get("/ai-budget")

    assert response.status_code == 200
    body = response.json()
    models = {item["model"]: item for item in body["models"]}
    assert settings.groq_reasoning_model in models and settings.groq_fast_model in models
    big = models[settings.groq_reasoning_model]
    assert big["provider_requests_limit"] == 1000
    assert big["requests_used"] == 120 and big["requests_remaining"] == 880
    assert big["tokens_used"] == 40000
    assert big["tokens_remaining"] == settings.ai_daily_tokens_soft_limit - 40000
    assert models[settings.groq_fast_model]["requests_used"] == 0
    assert body["interactive_reserve_requests"] == settings.ai_interactive_reserve_requests
    assert body["resets_at"] > body["day"]


def test_analysis_metrics_carries_the_per_task_block() -> None:
    client = authenticated_test_client(
        owner_sub="ai-budget-test-owner", database_url=os.environ["DATABASE_URL"]
    )

    body = client.get("/analysis-metrics").json()

    assert isinstance(body["ai"]["by_task"], list)


def test_a_non_owner_cannot_read_the_ai_budget() -> None:
    from tests.backend.support.auth import auth_headers, shared_keypair

    client = authenticated_test_client(
        owner_sub="ai-budget-test-owner", database_url=os.environ["DATABASE_URL"]
    )
    private_key, _ = shared_keypair()

    response = client.get("/ai-budget", headers=auth_headers(private_key, "someone-else"))

    assert response.status_code == 403
