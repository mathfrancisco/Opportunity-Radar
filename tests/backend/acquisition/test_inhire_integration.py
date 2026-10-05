"""inHire against a real database: the service hands the collector what it already stores, so a
second run with nothing changed makes zero detail requests and creates no new raw item."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.acquisition.inhire import InhireCollector
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.opportunities.models import (
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_FIXTURES = Path(__file__).parents[2] / "fixtures"
_LIST = json.loads((_FIXTURES / "inhire_jobs.json").read_text(encoding="utf-8"))
_DETAIL = json.loads((_FIXTURES / "inhire_job_detail.json").read_text(encoding="utf-8"))


def _cleanup(session: Session, source: SourceDefinitionModel) -> None:
    session.rollback()
    raw_ids = list(
        session.scalars(
            select(RawItemModel.id).where(RawItemModel.source_definition_id == source.id)
        )
    )
    session.execute(
        delete(SourceOccurrenceObservationModel).where(
            SourceOccurrenceObservationModel.raw_item_id.in_(raw_ids)
        )
    )
    session.execute(
        delete(SourceOccurrenceModel).where(SourceOccurrenceModel.source_definition_id == source.id)
    )
    session.execute(
        delete(SourceCheckpointModel).where(SourceCheckpointModel.source_definition_id == source.id)
    )
    session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_ids)))
    session.execute(delete(SourceRunModel).where(SourceRunModel.source_definition_id == source.id))
    session.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id))
    session.commit()


def test_second_run_makes_no_detail_request_and_no_new_raw_item() -> None:
    listing = json.loads(json.dumps(_LIST))
    log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request.url.path)
        if request.url.path == "/job-posts/public/pages":
            return httpx.Response(200, json=listing)
        job_id = request.url.path.rsplit("/", 1)[1]
        job = next(job for job in listing["jobsPage"] if job["jobId"] == job_id)
        return httpx.Response(200, json={**_DETAIL, **job})

    async def no_sleep(seconds: float) -> None:
        del seconds

    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type="inhire",
            name=f"inhire {uuid4().hex[:8]}",
            enabled=True,
            configuration={"tenant_identifier": "acme"},
            rate_limit_policy={},
        )
        session.add(source)
        session.commit()
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        service = AcquisitionService(
            session,
            registry=CollectorRegistry((InhireCollector(client=client, sleeper=no_sleep),)),
            repository=AcquisitionRepository(session),
            sleeper=no_sleep,
        )

        def run() -> SourceRunModel:
            return asyncio.run(
                service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )

        def raw_count() -> int:
            return session.scalar(
                select(func.count())
                .select_from(RawItemModel)
                .where(RawItemModel.source_definition_id == source.id)
            )

        try:
            first = run()
            assert first.status == "SUCCEEDED" and first.items_persisted == 3
            assert len(log) == 4 and first.http_requests == 4  # 1 list + 3 details
            assert raw_count() == 3
            stored = AcquisitionRepository(session).latest_raw_payloads(source.id)
            assert set(stored) == {job["jobId"] for job in listing["jobsPage"]}
            assert all("description" in payload for payload in stored.values())

            log.clear()
            second = run()
            assert second.status == "SUCCEEDED" and second.complete
            assert log == ["/job-posts/public/pages"]  # zero detail requests
            assert second.http_requests == 1
            assert second.items_seen == 3 and second.items_persisted == 0
            assert second.items_skipped == 3
            assert raw_count() == 3  # nothing new: same hashes, only presence observed

            log.clear()
            listing["jobsPage"][1]["location"] = "Curitiba, PR, BR"
            third = run()
            assert len(log) == 2 and log[1].endswith(listing["jobsPage"][1]["jobId"])
            assert third.items_persisted == 1 and raw_count() == 4
        finally:
            asyncio.run(client.aclose())
            _cleanup(session, source)
