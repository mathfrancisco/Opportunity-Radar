"""F51-04 AC01, AC03, AC04, AC05a, AC05b: Workday detail cooldown, budget and counters.

Runs the real `WorkdayCollector` and `AcquisitionService.execute` against a real database
(HTTP is `httpx.MockTransport`; no network), because each criterion is about what the
*next* session or a reloaded run sees, not about one call's return value.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
)
from opportunity_radar.acquisition.models import (
    HostBudgetStateModel,
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.scheduling import DEFAULT_HOST_BUDGET_WINDOW
from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY, AcquisitionService
from opportunity_radar.acquisition.workday import WorkdayCollector
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

HOST = "acme.wd5.myworkdayjobs.com"
CEILING = 50
_ENG = "Senior Backend Engineer"
_TARGETS = ("SOFTWARE_ENGINEERING",)
_DETAIL_BODY = {"jobPostingInfo": {"jobDescription": "<p>Synthetic.</p>"}}


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE acquisition.host_budget_state"))
    yield engine
    engine.dispose()


def _postings(count: int, *, start: int = 0) -> list[dict[str, object]]:
    return [
        {
            "title": _ENG,
            "externalPath": f"/job/Remote/Job-{number}_R{number}",
            "locationsText": "Remote",
            "bulletFields": [f"R{number}"],
        }
        for number in range(start, start + count)
    ]


def _listing_response(request: httpx.Request, postings: list[dict[str, object]]) -> httpx.Response:
    body = json.loads(request.content)
    offset, limit = body["offset"], body["limit"]
    return httpx.Response(
        200,
        json={
            "total": len(postings) if offset == 0 else 0,
            "jobPostings": postings[offset : offset + limit],
        },
    )


def _session_run(
    engine: Engine,
    *,
    now: datetime,
    detail_response: Callable[[], httpx.Response],
    postings: list[dict[str, object]] | None = None,
):
    """One worker session against `HOST` at `now`, reserving through the real repository."""
    board = postings if postings is not None else _postings(1)
    log: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        if request.method == "POST":
            return _listing_response(request, board)
        return detail_response()

    def reserve(is_detail: bool) -> str | None:
        with Session(engine) as session:
            return AcquisitionRepository(session).reserve_host_request(
                HOST, now=now, default_ceiling=CEILING, run_id=uuid4(), detail=is_detail
            )

    def persist_cooldown(until: datetime) -> None:
        with Session(engine) as session:
            AcquisitionRepository(session).persist_host_cooldown(HOST, until)

    async def no_sleep(delay: float) -> None:
        del delay

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme/site",
        company_name="Acme",
        api_region="wd5",
        fetch_detail=True,
        detail_approval_valid=True,
        target_role_families=_TARGETS,
        reserve_http_request=reserve,
        persist_cooldown=persist_cooldown,
    )

    async def collect() -> list[CollectedItem]:
        collector = WorkdayCollector(client=client, sleeper=no_sleep)
        return [item async for item in collector.discover(request)]

    items: list[CollectedItem] = []
    error: AcquisitionError | None = None
    try:
        try:
            items = asyncio.run(collect())
        except AcquisitionError as caught:
            error = caught
    finally:
        asyncio.run(client.aclose())
    return items, log, error


def _budget_row(engine: Engine) -> HostBudgetStateModel:
    with Session(engine) as session:
        row = session.get(HostBudgetStateModel, HOST)
        assert row is not None
        session.expunge(row)
        return row


def _too_many(retry_after: int) -> Callable[[], httpx.Response]:
    return lambda: httpx.Response(429, headers={"Retry-After": str(retry_after)})


def test_workday_429_retry_after_persists_across_sessions(engine: Engine) -> None:
    t0 = datetime.now(UTC)

    # 12:00 — the detail call is rate limited with Retry-After: 120.
    items, log, error = _session_run(engine, now=t0, detail_response=_too_many(120))
    assert error is None
    assert [call.method for call in log] == ["POST", "GET"]
    until = _budget_row(engine).cooldown_until
    assert until is not None
    assert t0 + timedelta(seconds=120) <= until <= datetime.now(UTC) + timedelta(seconds=120)
    used_after_429 = _budget_row(engine).requests_used

    # 12:01 — a brand new session (new connections, nothing in memory) sends nothing.
    _, log, error = _session_run(
        engine, now=t0 + timedelta(seconds=60), detail_response=_too_many(120)
    )
    assert error is not None and error.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED
    assert log == []
    assert _budget_row(engine).requests_used == used_after_429

    # One microsecond before the due instant is still blocked, the instant itself is not.
    with Session(engine) as session:
        assert (
            AcquisitionRepository(session).reserve_host_request(
                HOST,
                now=until - timedelta(microseconds=1),
                default_ceiling=CEILING,
                run_id=uuid4(),
            )
            == "cooldown"
        )
    assert _budget_row(engine).requests_used == used_after_429

    # 12:02 — resumes, and every transport is preceded by a fresh persisted reservation.
    items, log, error = _session_run(
        engine, now=until, detail_response=lambda: httpx.Response(200, json=_DETAIL_BODY)
    )
    assert error is None
    assert [call.method for call in log] == ["POST", "GET"]
    assert items[0].description == "<p>Synthetic.</p>"
    assert _budget_row(engine).requests_used == used_after_429 + 2


def test_workday_cooldown_survives_budget_window_rollover(engine: Engine) -> None:
    t0 = datetime.now(UTC)
    window = DEFAULT_HOST_BUDGET_WINDOW

    # A Retry-After longer than the quota window (70 minutes against a 1 hour window).
    _session_run(engine, now=t0, detail_response=_too_many(int(window.total_seconds()) + 600))
    before = _budget_row(engine)
    assert before.cooldown_until is not None
    assert before.cooldown_until > before.window_start + window
    assert before.requests_used == 2

    # The quota window has elapsed, the cooldown has not: still zero requests.
    _, log, error = _session_run(
        engine,
        now=before.window_start + window + timedelta(minutes=1),
        detail_response=lambda: httpx.Response(200, json=_DETAIL_BODY),
    )
    assert error is not None and error.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED
    assert log == []
    blocked = _budget_row(engine)
    assert blocked.cooldown_until == before.cooldown_until
    assert blocked.requests_used == before.requests_used

    # At the cooldown's end the request starts, in a fresh quota window.
    _, log, error = _session_run(
        engine,
        now=before.cooldown_until,
        detail_response=lambda: httpx.Response(200, json=_DETAIL_BODY),
    )
    assert error is None
    assert [call.method for call in log] == ["POST", "GET"]
    after = _budget_row(engine)
    assert after.window_start == before.cooldown_until
    assert after.requests_used == 2


# --- service level: counters and inventory contract -------------------------------------


class _Board:
    """What the fake Workday tenant answers; mutated between runs by each test."""

    def __init__(self, postings: list[dict[str, object]]) -> None:
        self.postings = postings
        self.detail: Callable[[str], httpx.Response] = lambda path: httpx.Response(
            200, json=_DETAIL_BODY
        )
        self.log: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.log.append(request)
        if request.method == "POST":
            return _listing_response(request, self.postings)
        return self.detail(request.url.path.rsplit("/cxs/acme/site", 1)[1])


class _Fixture:
    def __init__(self, engine: Engine, session: Session, board: _Board) -> None:
        self.engine = engine
        self.session = session
        self.board = board
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="workday",
            name=f"workday detail probe {uuid4().hex[:8]}",
            enabled=True,
            configuration=self.configuration(detail=False),
            rate_limit_policy={"max_retries": 0, "minimum_interval_seconds": 0},
        )
        session.add(self.source)
        session.commit()

    def configuration(self, *, detail: bool) -> dict[str, object]:
        configuration: dict[str, object] = {"tenant_identifier": "acme/site", "api_region": "wd5"}
        if detail:
            configuration["fetch_detail"] = True
            # Synthetic approval for this HTTP fake only; never copied into source data.
            configuration["detail_approval"] = {
                "source_id": str(self.source.id),
                "owner": "test fixture",
                "hostname": HOST,
                "reviewed_at": datetime.now(UTC).date().isoformat(),
                "terms_reference": "synthetic fixture policy",
                "decision": "approved",
            }
        return configuration

    def use_detail(self, enabled: bool) -> None:
        self.source.configuration = self.configuration(detail=enabled)
        self.session.commit()

    def execute(self, *, ceiling: int | None = None) -> SourceRunModel:
        async def no_sleep(delay: float) -> None:
            del delay

        client = httpx.AsyncClient(transport=httpx.MockTransport(self.board.handler))
        service = AcquisitionService(
            self.session,
            registry=CollectorRegistry((WorkdayCollector(client=client, sleeper=no_sleep),)),
            sleeper=no_sleep,
            target_role_families=lambda: _TARGETS,
            host_request_ceilings=None if ceiling is None else {"workday": ceiling},
        )
        try:
            return asyncio.run(
                service.execute(self.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
            )
        finally:
            asyncio.run(client.aclose())

    def raw_items(self) -> list[RawItemModel]:
        return list(
            self.session.scalars(
                select(RawItemModel).where(RawItemModel.source_definition_id == self.source.id)
            )
        )

    def normalize_all(self) -> None:
        opportunities = OpportunityService(self.session)
        for raw_item in self.raw_items():
            opportunities.normalize(raw_item.id)

    def opportunity_for(self, external_id: str) -> OpportunityModel:
        raw_item = next(item for item in self.raw_items() if item.external_id == external_id)
        occurrence = self.session.scalar(
            select(SourceOccurrenceModel).where(SourceOccurrenceModel.raw_item_id == raw_item.id)
        )
        assert occurrence is not None
        self.session.refresh(occurrence.opportunity)
        return occurrence.opportunity

    def cleanup(self) -> None:
        self.session.rollback()
        run_ids = list(
            self.session.scalars(
                select(SourceRunModel.id).where(
                    SourceRunModel.source_definition_id == self.source.id
                )
            )
        )
        raw_item_ids = [item.id for item in self.raw_items()]
        occurrence_ids = list(
            self.session.scalars(
                select(SourceOccurrenceModel.id).where(
                    SourceOccurrenceModel.raw_item_id.in_(raw_item_ids)
                )
            )
        )
        opportunity_ids = list(
            self.session.scalars(
                select(SourceOccurrenceModel.opportunity_id).where(
                    SourceOccurrenceModel.id.in_(occurrence_ids)
                )
            )
        )
        self.session.execute(
            delete(SourceOccurrenceObservationModel).where(
                SourceOccurrenceObservationModel.raw_item_id.in_(raw_item_ids)
                | SourceOccurrenceObservationModel.source_occurrence_id.in_(occurrence_ids)
            )
        )
        self.session.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id.in_(raw_item_ids)
            )
        )
        self.session.execute(
            delete(SourceOccurrenceModel).where(SourceOccurrenceModel.id.in_(occurrence_ids))
        )
        self.session.execute(
            delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids))
        )
        self.session.execute(
            delete(SourceCheckpointModel).where(
                SourceCheckpointModel.source_definition_id == self.source.id
            )
        )
        self.session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_item_ids)))
        self.session.execute(delete(SourceRunModel).where(SourceRunModel.id.in_(run_ids)))
        self.session.execute(
            delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id)
        )
        self.session.commit()


def _persist_cooldown(engine: Engine, until: datetime) -> None:
    with Session(engine) as session:
        AcquisitionRepository(session).persist_host_cooldown(HOST, until)


def test_detail_telemetry_round_trips_with_source_run(engine: Engine) -> None:
    board = _Board(_postings(3))

    def detail(path: str) -> httpx.Response:
        if path.endswith("Job-0_R0"):
            raise httpx.ReadTimeout("synthetic timeout")
        # Another source on the same host is rate limited while this run is in flight, so
        # the next eligible posting is blocked by the persisted cooldown.
        _persist_cooldown(engine, datetime.now(UTC) + timedelta(minutes=10))
        return httpx.Response(304)

    board.detail = detail
    with Session(engine) as session:
        fixture = _Fixture(engine, session, board)
        try:
            fixture.use_detail(True)
            run = fixture.execute()
            run_id, source_id = run.id, fixture.source.id
            assert run.status == "SUCCEEDED"

            # "Restart": a new session reads the run back from the database only.
            with Session(engine) as reloaded_session:
                reloaded = reloaded_session.get(SourceRunModel, run_id)
                assert reloaded is not None
                assert reloaded.source_definition_id == source_id
                assert reloaded.detail_requests == 2  # the timeout and the 304 started transport
                assert reloaded.detail_failures == 1  # the timeout only; a 304 is not a failure
                assert reloaded.detail_skipped == 1  # blocked before transport
                assert reloaded.detail_skip_reasons == {"cooldown": 1}
                assert reloaded.http_requests == 3  # one listing page and the two detail transports
            assert [call.method for call in board.log] == ["POST", "GET", "GET"]
        finally:
            fixture.cleanup()


def test_detail_429_keeps_completed_listing_inventory(engine: Engine) -> None:
    board = _Board(_postings(2))
    with Session(engine) as session:
        fixture = _Fixture(engine, session, board)
        try:
            opportunities = OpportunityService(session)
            first = fixture.execute()
            assert first.complete is True
            fixture.normalize_all()

            board.postings = _postings(1)  # Job-1 left the board
            second = fixture.execute()
            assert second.complete is True
            opportunities.reconcile_run_closures(second.id)
            assert fixture.opportunity_for("/job/Remote/Job-1_R1").lifecycle_status != "CLOSED"

            # Same listing, but detail is on and answers 429.
            board.detail = lambda path: httpx.Response(429, headers={"Retry-After": "1"})
            fixture.use_detail(True)
            third = fixture.execute()

            assert third.status == "SUCCEEDED"
            assert third.complete is True  # inventory: the listing finished normally
            assert third.detail_requests == 1  # content: the one detail attempt failed
            assert third.detail_failures == 1
            [kept] = [
                item for item in fixture.raw_items() if item.external_id == "/job/Remote/Job-0_R0"
            ]
            assert kept.item_metadata[COLLECTED_ITEM_V1_KEY]["description"] is None

            # Absence closing follows the listing's completeness alone.
            opportunities.reconcile_run_closures(third.id)
            assert fixture.opportunity_for("/job/Remote/Job-1_R1").lifecycle_status == "CLOSED"
            assert fixture.opportunity_for("/job/Remote/Job-0_R0").lifecycle_status != "CLOSED"
        finally:
            fixture.cleanup()


def test_listing_budget_exhaustion_does_not_close_absences(engine: Engine) -> None:
    board = _Board(_postings(25))
    with Session(engine) as session:
        fixture = _Fixture(engine, session, board)
        try:
            opportunities = OpportunityService(session)
            first = fixture.execute()  # two pages: 20 + 5
            assert first.complete is True
            fixture.normalize_all()

            board.postings = _postings(20)  # the last five left the board
            second = fixture.execute()
            assert second.complete is True
            opportunities.reconcile_run_closures(second.id)

            # They are listed again, but the quota allows only the first page.
            board.postings = _postings(25)
            with Session(engine) as budget_session:
                budget_session.execute(
                    update(HostBudgetStateModel)
                    .where(HostBudgetStateModel.host == HOST)
                    .values(
                        requests_used=0,
                        requests_ceiling=1,
                        window_start=datetime.now(UTC),
                        cooldown_until=None,
                    )
                )
                budget_session.commit()
            third = fixture.execute()

            assert third.status == "PARTIAL"
            assert third.complete is False
            assert third.items_seen == 20
            assert third.error_code == AcquisitionErrorCode.SOURCE_RATE_LIMITED.value
            opportunities.reconcile_run_closures(third.id)
            for number in range(20, 25):
                opportunity = fixture.opportunity_for(f"/job/Remote/Job-{number}_R{number}")
                assert opportunity.lifecycle_status != "CLOSED"
                assert opportunity.closure_evidence is None
        finally:
            fixture.cleanup()
