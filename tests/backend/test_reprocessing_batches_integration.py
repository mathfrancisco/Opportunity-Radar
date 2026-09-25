"""Database-backed proof of F17-06: normalization batches are resumable.

Criterion: "Reinício retoma lotes; repetição sem mudança não invalida avaliações." A
batch limited below the backlog size must pick up exactly where the previous call left
off — never reprocess an already-normalized raw item, never skip one.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.service import OpportunityService
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


def test_normalize_pending_resumes_a_batch_without_repeating_or_skipping() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    _reset(engine)
    client = TestClient(create_app(Settings(database_url=database_url)))
    source = client.post(
        "/sources",
        json={
            "source_type": "manual",
            "name": "Resumable batch fixture",
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
                    "value": "https://example.com/jobs/batch-1",
                    "metadata": {"title": "Backend Engineer One", "company_name": "Co"},
                },
                {
                    "kind": "URL",
                    "value": "https://example.com/jobs/batch-2",
                    "metadata": {"title": "Backend Engineer Two", "company_name": "Co"},
                },
            ]
        },
    )
    assert collected.status_code == 201

    with Session(engine) as session:
        service = OpportunityService(session)

        first = service.normalize_pending(limit=1)
        assert first.processed == 1

        second = service.normalize_pending(limit=1)
        assert second.processed == 1

        third = service.normalize_pending(limit=1)
        assert third.processed == 0

        total = session.scalar(select(OpportunityModel).limit(1))
        assert total is not None
        opportunities = list(session.scalars(select(OpportunityModel)))
        assert len(opportunities) == 2
