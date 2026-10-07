"""F51-08 against a real database: one concurrent pass over two hosts.

The scheduling tests in `test_collection_host_concurrency.py` fake the service. Here the
pass runs the real `AcquisitionService` on real sessions, one per host thread, so what is
checked is what the threads leave in PostgreSQL: runs, raw items, host budget, claims and the
pass row. Overlap is proved with events, never with sleeps.
"""

from __future__ import annotations

import os
import threading
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar import worker
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionRequest,
    CollectorCapabilities,
    HealthcheckContext,
    HealthResult,
)
from opportunity_radar.acquisition.models import (
    HostBudgetStateModel,
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceExecutionClaimModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.operations.models import WorkerPassHistoryModel
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

_TIMEOUT = 10.0
_ASHBY_HOST = "api.ashbyhq.com"


class _Transport:
    """What the fake collectors saw: who was inside the "HTTP call" at the same time."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active: dict[str, int] = {}
        self.peak_by_host: dict[str, int] = {}
        self.peak = 0
        self.threads: dict[str, str] = {}
        self.entered = {"tenant": threading.Event(), "ashby": threading.Event()}
        self.met = True

    def enter(self, host: str, reference: str) -> None:
        with self.lock:
            self.active[host] = self.active.get(host, 0) + 1
            self.peak_by_host[host] = max(self.peak_by_host.get(host, 0), self.active[host])
            self.peak = max(self.peak, sum(self.active.values()))
            self.threads[reference] = threading.current_thread().name

    def leave(self, host: str) -> None:
        with self.lock:
            self.active[host] -= 1


class _FakeCollector:
    """One listing "request" per run, held open until the other host is inside too."""

    capabilities = CollectorCapabilities(company_jobs=True)

    def __init__(self, source_type: str, transport: _Transport) -> None:
        self.source_type = source_type
        self._transport = transport
        self._first = True

    async def healthcheck(self, context: HealthcheckContext | None = None) -> HealthResult:
        del context
        return HealthResult(healthy=True, summary="fake")

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        transport = self._transport
        reference = request.company_reference or ""
        host = _ASHBY_HOST if self.source_type == "ashby" else f"teamtailor:{reference}"
        request.telemetry.record_http_attempt()
        transport.enter(host, reference)
        try:
            mine, other = "tenant", "ashby"
            if self.source_type == "ashby":
                mine, other = other, mine
            with transport.lock:
                first, self._first = self._first, False
            transport.entered[mine].set()
            if first and not transport.entered[other].wait(_TIMEOUT):
                transport.met = False
        finally:
            transport.leave(host)
        yield CollectedItem(
            source_type=self.source_type,
            external_id=f"job-{reference}",
            url=f"https://example.test/{reference}/job",
            title="Backend Engineer",
            company_name="Acme",
            location_text="Recife",
            description="We build APIs in Python.",
            raw_payload={"id": reference},
            metadata={},
        )


def _source(source_type: str, key: str, reference: str) -> SourceDefinitionModel:
    return SourceDefinitionModel(
        id=uuid4(),
        source_type=source_type,
        name=f"{source_type} {reference}",
        enabled=True,
        schedule="* * * * *",
        evidence_status="confirmed",
        terms_reviewed=True,
        collector_local_tested=True,
        configuration={key: reference},
        rate_limit_policy={"minimum_interval_seconds": 0},
    )


def _cleanup(session: Session, source_ids: list[UUID], hosts: list[str]) -> None:
    session.rollback()
    raw_ids = list(
        session.scalars(
            select(RawItemModel.id).where(RawItemModel.source_definition_id.in_(source_ids))
        )
    )
    session.execute(
        delete(SourceOccurrenceObservationModel).where(
            SourceOccurrenceObservationModel.raw_item_id.in_(raw_ids)
        )
    )
    session.execute(
        delete(SourceOccurrenceModel).where(
            SourceOccurrenceModel.source_definition_id.in_(source_ids)
        )
    )
    for model in (RawItemModel, SourceCheckpointModel, SourceExecutionClaimModel, SourceRunModel):
        session.execute(delete(model).where(model.source_definition_id.in_(source_ids)))
    session.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id.in_(source_ids)))
    session.execute(delete(HostBudgetStateModel).where(HostBudgetStateModel.host.in_(hosts)))
    session.commit()


def test_a_concurrent_pass_leaves_consistent_rows_for_every_host() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    marker = uuid4().hex[:10]
    tenant = _source("teamtailor", "company_identifier", f"tenant-{marker}")
    boards = [
        _source("ashby", "board_identifier", f"board-a-{marker}"),
        _source("ashby", "board_identifier", f"board-b-{marker}"),
    ]
    sources = [tenant, *boards]
    source_ids = [source.id for source in sources]
    tenant_host = f"teamtailor:tenant-{marker}"
    transport = _Transport()
    registry = CollectorRegistry(
        (_FakeCollector("teamtailor", transport), _FakeCollector("ashby", transport))
    )

    async def no_sleep(seconds: float) -> None:
        del seconds

    class _OnlyTheseSources(AcquisitionService):
        """The shared test database may hold other tests' sources; the pass ignores them."""

        def list_collectable_sources(self) -> list[SourceDefinitionModel]:
            return [s for s in super().list_collectable_sources() if s.id in source_ids]

    def service_factory(session: Session) -> AcquisitionService:
        return _OnlyTheseSources(
            session, registry=registry, sleeper=no_sleep, claims_enabled=True
        )

    with Session(engine) as session:
        session.execute(
            delete(HostBudgetStateModel).where(HostBudgetStateModel.host == _ASHBY_HOST)
        )
        session.add_all(sources)
        session.commit()
        try:
            worker.collect_enabled_sources(
                engine, host_concurrency=4, service_factory=service_factory
            )

            # The two hosts were inside the transport together; the shared host never twice.
            assert transport.met
            assert transport.peak == 2
            assert transport.peak_by_host[_ASHBY_HOST] == 1
            assert transport.threads[f"tenant-{marker}"] != transport.threads[f"board-a-{marker}"]

            session.expire_all()
            runs = session.scalars(
                select(SourceRunModel).where(SourceRunModel.source_definition_id.in_(source_ids))
            ).all()
            assert sorted(run.status for run in runs) == ["SUCCEEDED"] * 3
            assert all(run.finished_at is not None and run.items_persisted == 1 for run in runs)
            assert all(run.http_requests == 1 for run in runs)
            raw_sources = session.scalars(
                select(RawItemModel.source_definition_id).where(
                    RawItemModel.source_definition_id.in_(source_ids)
                )
            ).all()
            assert sorted(raw_sources, key=str) == sorted(source_ids, key=str)

            # Each request was charged to its own host, the two boards to the shared one.
            budgets = {
                row.host: row.requests_used
                for row in session.scalars(
                    select(HostBudgetStateModel).where(
                        HostBudgetStateModel.host.in_([tenant_host, _ASHBY_HOST])
                    )
                )
            }
            assert budgets == {tenant_host: 1, _ASHBY_HOST: 2}

            # Every claim was taken once and handed back.
            claims = session.scalars(
                select(SourceExecutionClaimModel).where(
                    SourceExecutionClaimModel.source_definition_id.in_(source_ids)
                )
            ).all()
            assert len(claims) == 3
            assert all(claim.owner_id is None and claim.fencing_token == 1 for claim in claims)

            last_pass = session.scalars(
                select(WorkerPassHistoryModel)
                .where(WorkerPassHistoryModel.job_name == "collect_enabled_sources")
                .order_by(WorkerPassHistoryModel.started_at.desc())
                .limit(1)
            ).one()
            assert last_pass.success is True and last_pass.due_sources == 3
            assert last_pass.details["completed"] == 3 and last_pass.details["failed"] == 0
        finally:
            _cleanup(session, source_ids, [tenant_host, _ASHBY_HOST])
    engine.dispose()
