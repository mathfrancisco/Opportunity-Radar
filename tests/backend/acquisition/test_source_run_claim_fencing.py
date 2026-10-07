"""F51-07 claim, lease and fencing, and F51-06 AC03/AC04, against the database.

Every collector is an in-process fake: no HTTP leaves the test. Two executions are always
two sessions (and, when they race, two threads), because the claim is a row two
transactions dispute; one session would never contend with itself.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
)
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceExecutionClaimModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import (
    AcquisitionRepository,
    FencedWriteRejected,
    SourceClaimUnavailable,
)
from opportunity_radar.acquisition.service import (
    AcquisitionService,
    SourceClaimedElsewhereError,
)
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

_REQUEST = CollectionRequest(mode=CollectionMode.DISCOVERY)
# A renewal tick far beyond any test, so only the tests that exercise renewal see one.
_NO_RENEWAL = 3600.0


class _Scripted:
    """A collector whose `discover` is whatever the test scripts; counts its calls."""

    capabilities = CollectorCapabilities(incremental_cursor=True, etag=True, last_modified=True)

    def __init__(
        self,
        source_type: str,
        script: Callable[[CollectionRequest], AsyncIterator[CollectedItem]],
    ) -> None:
        self.source_type = source_type
        self._script = script
        self.calls = 0
        self._lock = threading.Lock()

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        with self._lock:
            self.calls += 1
        return self._script(request)


class _Board:
    """One enabled source of a unique type, plus whatever the tests leave behind on it."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.source_type = f"claim_probe_{uuid4().hex[:8]}"
        self.source_id = uuid4()
        with Session(engine) as session:
            session.add(
                SourceDefinitionModel(
                    id=self.source_id,
                    source_type=self.source_type,
                    name=f"claim probe {uuid4().hex[:8]}",
                    enabled=True,
                    configuration={},
                    rate_limit_policy={},
                )
            )
            session.commit()

    def item(self, external_id: str) -> CollectedItem:
        return CollectedItem(
            source_type=self.source_type,
            external_id=external_id,
            title=external_id,
            raw_payload={"id": external_id, "title": external_id},
            cursor=external_id,
        )

    def collector(
        self, script: Callable[[CollectionRequest], AsyncIterator[CollectedItem]]
    ) -> _Scripted:
        return _Scripted(self.source_type, script)

    def board_of(self, *external_ids: str) -> _Scripted:
        async def script(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            del request
            for external_id in external_ids:
                yield self.item(external_id)

        return self.collector(script)

    def service(
        self,
        collector: _Scripted,
        session: Session,
        *,
        claims: bool = True,
        renew_interval: float = _NO_RENEWAL,
    ) -> AcquisitionService:
        return AcquisitionService(
            session,
            registry=CollectorRegistry((collector,)),  # type: ignore[arg-type]
            repository=AcquisitionRepository(session),
            claims_enabled=claims,
            claim_renew_interval_seconds=renew_interval,
        )

    def run_one(self, collector: _Scripted, **kwargs: object) -> SourceRunModel:
        with Session(self.engine) as session:
            return asyncio.run(
                self.service(collector, session, **kwargs).execute(  # type: ignore[arg-type]
                    self.source_id, _REQUEST
                )
            )

    def expire_lease(self) -> None:
        with Session(self.engine) as session:
            session.execute(
                update(SourceExecutionClaimModel)
                .where(SourceExecutionClaimModel.source_definition_id == self.source_id)
                .values(lease_expires_at=datetime.now(UTC) - timedelta(minutes=1))
            )
            session.commit()

    def claim_row(self) -> SourceExecutionClaimModel | None:
        with Session(self.engine) as session:
            row = session.get(SourceExecutionClaimModel, (self.source_id, "collect"))
            if row is not None:
                session.expunge(row)
            return row

    def run(self, run_id: UUID) -> SourceRunModel:
        with Session(self.engine) as session:
            row = session.get(SourceRunModel, run_id)
            assert row is not None
            session.expunge(row)
            return row

    def external_ids(self) -> set[str]:
        with Session(self.engine) as session:
            return {
                row.external_id
                for row in session.scalars(
                    select(RawItemModel).where(RawItemModel.source_definition_id == self.source_id)
                )
                if row.external_id is not None
            }

    def checkpoint(self) -> SourceCheckpointModel | None:
        with Session(self.engine) as session:
            row = session.get(SourceCheckpointModel, self.source_id)
            if row is not None:
                session.expunge(row)
            return row

    def complete_run_ids(self) -> list[UUID]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(SourceRunModel.id).where(
                        SourceRunModel.source_definition_id == self.source_id,
                        SourceRunModel.complete.is_(True),
                    )
                )
            )

    def observed_external_ids(self, run_id: UUID) -> set[str]:
        with Session(self.engine) as session:
            return {
                external_id
                for (external_id,) in session.execute(
                    select(RawItemModel.external_id)
                    .join(
                        SourceOccurrenceObservationModel,
                        SourceOccurrenceObservationModel.raw_item_id == RawItemModel.id,
                    )
                    .where(SourceOccurrenceObservationModel.source_run_id == run_id)
                )
                if external_id is not None
            }

    def seed_abandoned_run(self) -> tuple[UUID, int]:
        """What a crashed worker leaves: a RUNNING run bound to a live lease, never released."""
        run_id = uuid4()
        with Session(self.engine) as session:
            claim = AcquisitionRepository(session).claim_source_execution(
                source_id=self.source_id, run_id=run_id
            )
            session.add(
                SourceRunModel(
                    id=run_id,
                    source_definition_id=self.source_id,
                    status="RUNNING",
                    started_at=datetime.now(UTC),
                    fencing_token=claim.fencing_token,
                )
            )
            session.commit()
            assert AcquisitionRepository(session).attach_source_execution_run(claim)
        return run_id, claim.fencing_token

    def cleanup(self) -> None:
        with Session(self.engine) as session:
            run_ids = list(
                session.scalars(
                    select(SourceRunModel.id).where(
                        SourceRunModel.source_definition_id == self.source_id
                    )
                )
            )
            raw_item_ids = list(
                session.scalars(
                    select(RawItemModel.id).where(
                        RawItemModel.source_definition_id == self.source_id
                    )
                )
            )
            occurrence_ids = list(
                session.scalars(
                    select(SourceOccurrenceModel.id).where(
                        SourceOccurrenceModel.raw_item_id.in_(raw_item_ids)
                    )
                )
            )
            opportunity_ids = list(
                session.scalars(
                    select(SourceOccurrenceModel.opportunity_id).where(
                        SourceOccurrenceModel.id.in_(occurrence_ids)
                    )
                )
            )
            session.execute(
                delete(SourceOccurrenceObservationModel).where(
                    SourceOccurrenceObservationModel.raw_item_id.in_(raw_item_ids)
                    | SourceOccurrenceObservationModel.source_occurrence_id.in_(occurrence_ids)
                )
            )
            session.execute(
                delete(NormalizationResultModel).where(
                    NormalizationResultModel.raw_item_id.in_(raw_item_ids)
                )
            )
            session.execute(
                delete(SourceOccurrenceModel).where(SourceOccurrenceModel.id.in_(occurrence_ids))
            )
            session.execute(
                delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids))
            )
            session.execute(
                delete(SourceCheckpointModel).where(
                    SourceCheckpointModel.source_definition_id == self.source_id
                )
            )
            session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_item_ids)))
            session.execute(
                delete(SourceExecutionClaimModel).where(
                    SourceExecutionClaimModel.source_definition_id == self.source_id
                )
            )
            session.execute(delete(SourceRunModel).where(SourceRunModel.id.in_(run_ids)))
            session.execute(
                delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source_id)
            )
            session.commit()


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    yield engine
    engine.dispose()


@pytest.fixture
def board(engine: Engine) -> Iterator[_Board]:
    board = _Board(engine)
    yield board
    board.cleanup()


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        str(record.__dict__["event"])
        for record in caplog.records
        if "event" in record.__dict__ and record.__dict__.get("job") == "collect"
    ]


# --- F51-07 ---------------------------------------------------------------------------


def test_worker_and_cli_race_only_one_claims_and_the_other_makes_zero_http(
    board: _Board,
) -> None:
    """AC01: two entries, one barrier, one source; the loser is `claimed_elsewhere`."""
    loser_done = threading.Event()

    async def script(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        # Whoever claims first holds the lease until the other entry has been turned away.
        await asyncio.to_thread(loser_done.wait, 10)
        yield board.item("only-one")

    collectors = [board.collector(script), board.collector(script)]
    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    guard = threading.Lock()

    def entry(collector: _Scripted) -> None:
        with Session(board.engine) as session:
            service = board.service(collector, session)
            barrier.wait(timeout=10)
            try:
                outcome: object = asyncio.run(service.execute(board.source_id, _REQUEST))
            except SourceClaimedElsewhereError as error:
                loser_done.set()
                outcome = error
            with guard:
                outcomes.append(outcome)

    threads = [threading.Thread(target=entry, args=(collector,)) for collector in collectors]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(thread.is_alive() for thread in threads)

    refused = [item for item in outcomes if isinstance(item, SourceClaimedElsewhereError)]
    ran = [item for item in outcomes if isinstance(item, SourceRunModel)]
    assert len(refused) == 1 and len(ran) == 1
    assert refused[0].outcome == "claimed_elsewhere"
    assert sum(collector.calls for collector in collectors) == 1  # zero HTTP for the loser
    assert ran[0].status == "SUCCEEDED"


def test_fenced_item_write_is_rejected_after_the_lease_is_recovered(
    board: _Board, caplog: pytest.LogCaptureFixture
) -> None:
    """AC02: A (token 1) blocks before its second item; B recovers (token 2) and writes."""
    caplog.set_level(logging.INFO)

    async def scenario() -> tuple[SourceRunModel, SourceRunModel]:
        blocked, release = asyncio.Event(), asyncio.Event()

        async def a_script(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            del request
            yield board.item("a-before-loss")
            blocked.set()
            await release.wait()
            yield board.item("a-after-loss")

        a_run_id: list[UUID] = []
        with Session(board.engine) as a_session, Session(board.engine) as b_session:
            a = board.service(board.collector(a_script), a_session)
            b = board.service(board.board_of("b-only"), b_session)
            a_task = asyncio.create_task(a.execute(board.source_id, _REQUEST))
            await blocked.wait()
            claim = board.claim_row()
            assert claim is not None and claim.fencing_token == 1
            a_run_id.append(claim.run_id)  # type: ignore[arg-type]
            board.expire_lease()
            b_run = await b.execute(board.source_id, _REQUEST)
            release.set()
            with pytest.raises(FencedWriteRejected):
                await a_task
        return board.run(a_run_id[0]), b_run

    a_run, b_run = asyncio.run(scenario())

    assert board.external_ids() == {"a-before-loss", "b-only"}  # nothing from A after the loss
    assert board.observed_external_ids(a_run.id) == {"a-before-loss"}
    assert a_run.fencing_token == 1 and b_run.fencing_token == 2
    assert a_run.status == "PARTIAL" and a_run.error_code == "FENCE_REJECTED"
    assert a_run.complete is False
    assert b_run.status == "SUCCEEDED"
    events = _events(caplog)
    assert events.count("claim_acquired") == 2
    assert "claim_recovered" in events and "fence_rejected" in events


def test_fenced_terminal_write_leaves_run_checkpoint_and_inventory_untouched(
    board: _Board,
) -> None:
    """AC02: run, checkpoint and metrics are fenced too, so a stale run cannot overwrite the
    last complete inventory or promote its cursor."""
    baseline = board.run_one(board.board_of("kept"))
    assert baseline.complete is True
    baseline_cursor = board.checkpoint()
    assert baseline_cursor is not None and baseline_cursor.cursor == "kept"

    async def scenario() -> UUID:
        blocked, release = asyncio.Event(), asyncio.Event()

        async def a_script(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            del request
            yield board.item("stale-cursor")
            blocked.set()
            await release.wait()

        with Session(board.engine) as a_session:
            a = board.service(board.collector(a_script), a_session)
            a_task = asyncio.create_task(a.execute(board.source_id, _REQUEST))
            await blocked.wait()
            claim = board.claim_row()
            assert claim is not None and claim.run_id is not None
            board.expire_lease()
            with Session(board.engine) as recoverer:
                AcquisitionRepository(recoverer).claim_source_execution(
                    source_id=board.source_id, run_id=uuid4()
                )
            release.set()
            with pytest.raises(FencedWriteRejected):
                await a_task
            return claim.run_id

    stale_run = board.run(asyncio.run(scenario()))

    assert stale_run.status == "PARTIAL" and stale_run.error_code == "FENCE_REJECTED"
    assert stale_run.complete is False
    assert stale_run.items_persisted == 0  # A's own counters were never written
    assert stale_run.checkpoint_after is None
    checkpoint = board.checkpoint()
    assert checkpoint is not None
    assert checkpoint.cursor == "kept" and checkpoint.promoted_by_run_id == baseline.id
    assert board.complete_run_ids() == [baseline.id]  # the last complete inventory stands


def test_two_recoveries_of_one_expired_lease_have_a_single_winner(board: _Board) -> None:
    """AC03: one conditional update wins; one recovered correlation, one execution."""
    abandoned_run_id, first_token = board.seed_abandoned_run()
    board.expire_lease()
    barrier = threading.Barrier(2)
    results: list[object] = []
    guard = threading.Lock()

    def recover() -> None:
        with Session(board.engine) as session:
            barrier.wait(timeout=10)
            try:
                result: object = AcquisitionRepository(session).claim_source_execution(
                    source_id=board.source_id, run_id=uuid4()
                )
            except SourceClaimUnavailable as error:
                result = error
            with guard:
                results.append(result)

    threads = [threading.Thread(target=recover) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    winners = [item for item in results if not isinstance(item, SourceClaimUnavailable)]
    assert len(winners) == 1 and len(results) == 2
    winner = winners[0]
    assert winner.recovered is True  # type: ignore[attr-defined]
    assert winner.recovered_run_id == abandoned_run_id  # type: ignore[attr-defined]
    assert winner.fencing_token == first_token + 1  # type: ignore[attr-defined]
    row = board.claim_row()
    assert row is not None and row.fencing_token == first_token + 1


def test_distinct_sources_claim_independently(engine: Engine, board: _Board) -> None:
    """AC04: the worker's source and the CLI's source never block each other."""
    other = _Board(engine)
    try:
        async def scenario() -> list[SourceRunModel]:
            both_inside = asyncio.Event()
            inside = 0

            def script_for(target: _Board, name: str):
                async def script(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
                    nonlocal inside
                    del request
                    inside += 1
                    if inside == 2:
                        both_inside.set()
                    # Both executions must be inside discover at once, each with its claim.
                    await asyncio.wait_for(both_inside.wait(), timeout=10)
                    yield target.item(name)

                return script

            with Session(engine) as one, Session(engine) as two:
                a = board.service(board.collector(script_for(board, "worker-item")), one)
                b = other.service(other.collector(script_for(other, "cli-item")), two)
                return list(
                    await asyncio.gather(
                        a.execute(board.source_id, _REQUEST),
                        b.execute(other.source_id, _REQUEST),
                    )
                )

        runs = asyncio.run(scenario())

        assert [run.status for run in runs] == ["SUCCEEDED", "SUCCEEDED"]
        assert board.external_ids() == {"worker-item"}
        assert other.external_ids() == {"cli-item"}
    finally:
        other.cleanup()


def test_crash_leaves_an_observable_lease_and_never_becomes_success(board: _Board) -> None:
    """A dead worker's lease stays visible, blocks others until it expires, and the
    abandoned run ends PARTIAL when the next worker recovers it."""
    abandoned_run_id, _ = board.seed_abandoned_run()

    row = board.claim_row()
    assert row is not None and row.owner_id is not None
    assert row.lease_expires_at is not None and row.lease_expires_at > datetime.now(UTC)
    assert board.run(abandoned_run_id).status == "RUNNING"

    contender = board.board_of("late")
    with Session(board.engine) as session, pytest.raises(SourceClaimedElsewhereError):
        asyncio.run(board.service(contender, session).execute(board.source_id, _REQUEST))
    assert contender.calls == 0

    board.expire_lease()
    recovered = board.run_one(board.board_of("late"))

    abandoned = board.run(abandoned_run_id)
    assert abandoned.status == "PARTIAL" and abandoned.status != "SUCCEEDED"
    assert abandoned.error_code == "FENCE_REJECTED" and abandoned.complete is False
    assert abandoned.finished_at is not None
    assert recovered.status == "SUCCEEDED" and recovered.fencing_token == 2


def test_network_failure_ends_failed_not_succeeded(board: _Board) -> None:
    async def failing(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        raise AcquisitionError(AcquisitionErrorCode.SOURCE_SERVER_ERROR, "upstream down")
        yield board.item("never")

    run = board.run_one(board.collector(failing))

    assert run.status == "FAILED" and run.complete is False
    assert run.error_code == "SOURCE_SERVER_ERROR"
    assert board.complete_run_ids() == []


def test_stale_owner_cannot_renew_the_recovered_claim(board: _Board) -> None:
    """Task 2: renewal is conditional on the current token, so A cannot extend B's lease."""
    with Session(board.engine) as session:
        repository = AcquisitionRepository(session)
        stale = repository.claim_source_execution(source_id=board.source_id, run_id=uuid4())
        board.expire_lease()
        current = repository.claim_source_execution(source_id=board.source_id, run_id=uuid4())

        assert repository.renew_source_execution_claim(stale) is False
        assert repository.renew_source_execution_claim(current) is True
        assert repository.release_source_execution_claim(stale) is False
        row = board.claim_row()
        assert row is not None and row.owner_id == current.owner_id


def test_lease_is_renewed_while_the_run_is_alive(
    board: _Board, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    async def slow(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        # The lease is about to lapse; only a renewal can save it during this wait.
        with Session(board.engine) as session:
            session.execute(
                update(SourceExecutionClaimModel)
                .where(SourceExecutionClaimModel.source_definition_id == board.source_id)
                .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=1))
            )
            session.commit()
        await asyncio.sleep(0.3)
        row = board.claim_row()
        assert row is not None and row.lease_expires_at is not None
        assert row.lease_expires_at > datetime.now(UTC) + timedelta(minutes=2)
        yield board.item("renewed")

    run = board.run_one(board.collector(slow), renew_interval=0.05)

    assert run.status == "SUCCEEDED"
    assert "lease_renewed" in _events(caplog)


def test_claims_disabled_runs_without_a_claim_row_and_ignores_a_foreign_claim(
    board: _Board,
) -> None:
    """The switch-off path: no claim row, no per-item commit, a foreign lease not consulted."""
    run = board.run_one(board.board_of("plain"), claims=False)
    assert run.status == "SUCCEEDED" and run.fencing_token is None
    assert board.claim_row() is None

    board.seed_abandoned_run()  # a live foreign lease, with its run left RUNNING
    with Session(board.engine) as session:
        session.execute(
            update(SourceRunModel)
            .where(SourceRunModel.source_definition_id == board.source_id)
            .values(status="FAILED", finished_at=datetime.now(UTC))
        )
        session.commit()
    again = board.run_one(board.board_of("plain", "second"), claims=False)
    assert again.status == "SUCCEEDED"
    assert board.external_ids() == {"plain", "second"}


# --- F51-06 AC03 / AC04 ---------------------------------------------------------------


def test_live_transport_keeps_source_single_flight(board: _Board) -> None:
    """F51-06 AC03: a transport that ignores cancellation keeps the claim; exactly one
    request is ever alive, and a second execution makes none until the first ends."""
    live = 0
    peak = 0

    async def scenario() -> tuple[SourceRunModel, _Scripted, _Scripted]:
        nonlocal live, peak
        started, released = asyncio.Event(), asyncio.Event()

        async def stubborn(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            nonlocal live, peak
            del request
            live += 1
            peak = max(peak, live)
            started.set()
            try:
                while not released.is_set():
                    try:
                        await released.wait()
                    except asyncio.CancelledError:
                        continue  # the transport only ends on its own signal
            finally:
                live -= 1
            return
            yield board.item("never")

        first_collector = board.collector(stubborn)
        second_collector = board.board_of("late")
        with Session(board.engine) as one, Session(board.engine) as two:
            first = asyncio.create_task(
                board.service(first_collector, one).execute(
                    board.source_id, _REQUEST, deadline_seconds=0.05
                )
            )
            await started.wait()
            await asyncio.sleep(0.2)  # the deadline has fired; cleanup is still pending
            assert not first.done()
            row = board.claim_row()
            assert row is not None and row.owner_id is not None  # ownership not released

            with pytest.raises(SourceClaimedElsewhereError):
                await board.service(second_collector, two).execute(board.source_id, _REQUEST)
            assert second_collector.calls == 0 and peak == 1

            released.set()
            run = await first
        return run, first_collector, second_collector

    run, first_collector, _ = asyncio.run(scenario())

    assert first_collector.calls == 1 and peak == 1
    assert run.status == "PARTIAL" and run.complete is False
    row = board.claim_row()
    assert row is not None and row.owner_id is None  # released only after the transport ended
    assert board.run_one(board.board_of("after")).status == "SUCCEEDED"


def test_worker_timeout_preserves_positive_presence_only(board: _Board) -> None:
    """F51-06 AC04: under the claim, a timed-out run keeps what it saw and closes nothing."""

    async def stalled_after_prefix(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield board.item("present")
        await asyncio.Event().wait()

    with Session(board.engine) as session:
        opportunities = OpportunityService(session)
        board.run_one(board.board_of("present", "absent"))
        for raw_item in session.scalars(
            select(RawItemModel).where(RawItemModel.source_definition_id == board.source_id)
        ):
            opportunities.normalize(raw_item.id)
        second = board.run_one(board.board_of("present"))
        assert second.complete is True
        opportunities.reconcile_run_closures(second.id)

        with Session(board.engine) as timed_out_session:
            partial = asyncio.run(
                board.service(board.collector(stalled_after_prefix), timed_out_session).execute(
                    board.source_id, _REQUEST, deadline_seconds=0.05
                )
            )
        assert partial.status == "PARTIAL" and partial.complete is False

        session.expire_all()
        by_external = {
            raw_item.external_id: raw_item
            for raw_item in session.scalars(
                select(RawItemModel).where(RawItemModel.source_definition_id == board.source_id)
            )
        }
        present = session.scalar(
            select(SourceOccurrenceModel).where(
                SourceOccurrenceModel.raw_item_id == by_external["present"].id
            )
        )
        absent = session.scalar(
            select(SourceOccurrenceModel).where(
                SourceOccurrenceModel.raw_item_id == by_external["absent"].id
            )
        )
        assert present is not None and absent is not None
        assert present.last_seen_run_id == partial.id  # the positive observation stays

        opportunities.reconcile_run_closures(partial.id)
        session.refresh(absent)
        assert absent.opportunity.lifecycle_status != "CLOSED"
        assert absent.opportunity.closure_evidence is None


def _normalize_source(session: Session, board: _Board) -> None:
    for raw_item in session.scalars(
        select(RawItemModel).where(RawItemModel.source_definition_id == board.source_id)
    ):
        OpportunityService(session).normalize(raw_item.id)


def _absent_status(session: Session, board: _Board) -> str:
    session.expire_all()
    raw_item = session.scalar(
        select(RawItemModel).where(
            RawItemModel.source_definition_id == board.source_id,
            RawItemModel.external_id == "absent",
        )
    )
    assert raw_item is not None
    occurrence = session.scalar(
        select(SourceOccurrenceModel).where(SourceOccurrenceModel.raw_item_id == raw_item.id)
    )
    assert occurrence is not None
    return occurrence.opportunity.lifecycle_status


def test_stale_complete_run_does_not_close_absences_once_a_newer_run_started(
    board: _Board, caplog: pytest.LogCaptureFixture
) -> None:
    """F51-07 AC02 (closure): the claim is gone after `execute`, the fencing generation is not."""
    caplog.set_level(logging.INFO)
    board.run_one(board.board_of("present", "absent"))
    board.run_one(board.board_of("present"))
    third = board.run_one(board.board_of("present"))  # would close it: absent from two in a row
    fourth = board.run_one(board.board_of("present"))  # a newer run of the same source
    assert third.complete is True and fourth.complete is True
    with Session(board.engine) as session:
        _normalize_source(session, board)
        guard = board.service(board.board_of(), session)

        closed = OpportunityService(session).reconcile_run_closures(
            third.id, may_close=guard.run_may_close_absences
        )

        assert closed is False
        assert _absent_status(session, board) != "CLOSED"
        rejected = [
            record
            for record in caplog.records
            if record.__dict__.get("event") == "fence_rejected"
            and record.__dict__.get("reason") == "closure_superseded"
        ]
        assert [record.__dict__["run_id"] for record in rejected] == [str(third.id)]

        # The newest complete run still closes it, with the same guard.
        assert OpportunityService(session).reconcile_run_closures(
            fourth.id, may_close=guard.run_may_close_absences
        ) is True
        assert _absent_status(session, board) == "CLOSED"


def test_closure_without_claims_behaves_as_before(board: _Board) -> None:
    """`collection_claim_enabled=false`: runs carry no token and the guard never refuses."""
    board.run_one(board.board_of("present", "absent"), claims=False)
    board.run_one(board.board_of("present"), claims=False)
    third = board.run_one(board.board_of("present"), claims=False)
    board.run_one(board.board_of("present"), claims=False)
    assert third.fencing_token is None
    with Session(board.engine) as session:
        _normalize_source(session, board)
        guard = board.service(board.board_of(), session, claims=False)

        assert OpportunityService(session).reconcile_run_closures(
            third.id, may_close=guard.run_may_close_absences
        ) is True
        assert _absent_status(session, board) == "CLOSED"
