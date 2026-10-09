"""F51-08 against a real database: one concurrent pass over two hosts.

The scheduling tests in `test_collection_host_concurrency.py` fake the service. Here the
pass runs the real `AcquisitionService` on real sessions, one per host thread, so what is
checked is what the threads leave in PostgreSQL: runs, raw items, host budget, claims and the
pass row. Overlap is proved with events, never with sleeps.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar import worker
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionMode,
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
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.service import OpportunityService
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
                engine, host_concurrency=4, service_factory=service_factory,
                owner_sub="concurrent-pass-test-owner",
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


class _PlannedCollector:
    """Per board, one scripted listing per call: the ids it yields and whether it then stalls.

    The calls before the pass build the history a closure needs; the last one runs in it.
    """

    capabilities = CollectorCapabilities(company_jobs=True)

    def __init__(
        self,
        source_type: str,
        plans: dict[str, list[tuple[tuple[str, ...], bool]]],
        *,
        stalled: threading.Event,
    ) -> None:
        self.source_type = source_type
        self._plans = plans
        self._stalled = stalled
        self.peer_was_stuck = True
        self._lock = threading.Lock()

    async def healthcheck(self, context: HealthcheckContext | None = None) -> HealthResult:
        del context
        return HealthResult(healthy=True, summary="fake")

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        reference = request.company_reference or ""
        with self._lock:
            external_ids, stall = self._plans[reference].pop(0)
            last_call = not self._plans[reference]
        request.telemetry.record_http_attempt()
        for external_id in external_ids:
            yield CollectedItem(
                source_type=self.source_type,
                external_id=external_id,
                url=f"https://example.test/{reference}/{external_id}",
                title=f"Backend Engineer {external_id}",
                company_name="Acme",
                location_text="Recife",
                description="We build APIs in Python.",
                raw_payload={"id": external_id},
                metadata={},
            )
        if stall:
            self._stalled.set()
            await asyncio.Event().wait()  # the listing never ends; only the deadline does
        elif last_call and self.source_type == "ashby":
            # The complete listing is read while the other host is still stuck.
            if not self._stalled.wait(_TIMEOUT):
                self.peer_was_stuck = False


def _lifecycle(session: Session, source_id: UUID, external_id: str) -> str:
    occurrence = session.scalars(
        select(SourceOccurrenceModel).where(
            SourceOccurrenceModel.source_definition_id == source_id,
            SourceOccurrenceModel.external_id == external_id,
        )
    ).one()
    return occurrence.opportunity.lifecycle_status


def _cleanup_normalized(session: Session, source_ids: list[UUID], hosts: list[str]) -> None:
    """`_cleanup` plus what normalizing and closing leave behind."""
    session.rollback()
    raw_ids = list(
        session.scalars(
            select(RawItemModel.id).where(RawItemModel.source_definition_id.in_(source_ids))
        )
    )
    opportunity_ids = list(
        session.scalars(
            select(SourceOccurrenceModel.opportunity_id).where(
                SourceOccurrenceModel.source_definition_id.in_(source_ids)
            )
        )
    )
    session.execute(
        delete(SourceOccurrenceObservationModel).where(
            SourceOccurrenceObservationModel.raw_item_id.in_(raw_ids)
        )
    )
    session.execute(
        delete(NormalizationResultModel).where(NormalizationResultModel.raw_item_id.in_(raw_ids))
    )
    session.execute(
        delete(SourceOccurrenceModel).where(
            SourceOccurrenceModel.source_definition_id.in_(source_ids)
        )
    )
    session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
    session.commit()
    _cleanup(session, source_ids, hosts)


def test_a_timed_out_listing_stays_partial_while_a_complete_one_on_another_host_reconciles() -> (
    None
):
    """F51-08 AC04: in one pass, host A times out mid-listing and closes nothing while host B
    finishes its listing and closes what that listing no longer shows."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    marker = uuid4().hex[:10]
    slow = _source("teamtailor", "company_identifier", f"slow-{marker}")
    fast = _source("ashby", "board_identifier", f"fast-{marker}")
    source_ids = [slow.id, fast.id]
    slow_host = f"teamtailor:slow-{marker}"
    stalled = threading.Event()
    # Two complete runs leave "gone" one miss from closing; a third complete run would
    # close it. The slow board's third listing never completes.
    slow_collector = _PlannedCollector(
        "teamtailor",
        {
            f"slow-{marker}": [
                (("kept", "gone"), False),
                (("kept",), False),
                (("kept",), True),
            ]
        },
        stalled=stalled,
    )
    fast_collector = _PlannedCollector(
        "ashby",
        {
            f"fast-{marker}": [
                (("open", "withdrawn"), False),
                (("open",), False),
                (("open",), False),
            ]
        },
        stalled=stalled,
    )
    registry = CollectorRegistry((slow_collector, fast_collector))

    async def no_sleep(seconds: float) -> None:
        del seconds

    class _OnlyTheseSources(AcquisitionService):
        def list_collectable_sources(self) -> list[SourceDefinitionModel]:
            return [s for s in super().list_collectable_sources() if s.id in source_ids]

    def service_factory(session: Session) -> AcquisitionService:
        return _OnlyTheseSources(
            session, registry=registry, sleeper=no_sleep, claims_enabled=True
        )

    def prior_complete_run(session: Session, source: SourceDefinitionModel) -> None:
        service = service_factory(session)
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
        assert run.status == "SUCCEEDED" and run.complete is True
        opportunities = OpportunityService(session)
        opportunities.normalize_run(run.id)
        opportunities.reconcile_run_closures(run.id, may_close=service.run_may_close_absences)

    with Session(engine) as session:
        session.execute(
            delete(HostBudgetStateModel).where(HostBudgetStateModel.host == _ASHBY_HOST)
        )
        session.add_all([slow, fast])
        session.commit()
        try:
            for source in (slow, fast):
                prior_complete_run(session, source)
                prior_complete_run(session, source)
            assert _lifecycle(session, slow.id, "gone") != "CLOSED"
            assert _lifecycle(session, fast.id, "withdrawn") != "CLOSED"
            known_runs = set(
                session.scalars(
                    select(SourceRunModel.id).where(
                        SourceRunModel.source_definition_id.in_(source_ids)
                    )
                )
            )

            worker.collect_enabled_sources(
                engine,
                host_concurrency=2,
                source_deadline_seconds=1.0,
                now=datetime.now(UTC) + timedelta(minutes=10),
                service_factory=service_factory,
                owner_sub="concurrent-pass-test-owner",
            )

            session.expire_all()
            pass_runs = {
                run.source_definition_id: run
                for run in session.scalars(
                    select(SourceRunModel).where(
                        SourceRunModel.source_definition_id.in_(source_ids),
                        SourceRunModel.id.not_in(known_runs),
                    )
                )
            }
            timed_out, finished = pass_runs[slow.id], pass_runs[fast.id]
            assert fast_collector.peer_was_stuck  # B read its listing while A was stuck
            assert timed_out.status == "PARTIAL" and timed_out.complete is False
            assert timed_out.error_code == "SOURCE_TIMEOUT"
            assert finished.status == "SUCCEEDED" and finished.complete is True
            assert finished.finished_at < timed_out.finished_at  # B did not wait for A's deadline

            # A kept what it saw and closed nothing; B reconciled its complete listing.
            kept = session.scalars(
                select(SourceOccurrenceModel).where(
                    SourceOccurrenceModel.source_definition_id == slow.id,
                    SourceOccurrenceModel.external_id == "kept",
                )
            ).one()
            assert kept.last_seen_run_id == timed_out.id
            assert _lifecycle(session, slow.id, "kept") != "CLOSED"
            assert _lifecycle(session, slow.id, "gone") != "CLOSED"
            assert _lifecycle(session, fast.id, "open") != "CLOSED"
            assert _lifecycle(session, fast.id, "withdrawn") == "CLOSED"

            last_pass = session.scalars(
                select(WorkerPassHistoryModel)
                .where(WorkerPassHistoryModel.job_name == "collect_enabled_sources")
                .order_by(WorkerPassHistoryModel.started_at.desc())
                .limit(1)
            ).one()
            assert last_pass.details["completed"] == 2 and last_pass.details["failed"] == 0
        finally:
            _cleanup_normalized(session, source_ids, [slow_host, _ASHBY_HOST])
    engine.dispose()
