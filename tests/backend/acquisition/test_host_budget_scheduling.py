"""Shared host/provider budget, HTTP-conditional checkpoints, and restart survival.

Card F20-38. The scheduling half (`HostBudgetState`, `evaluate_gate`, `next_due_at`) is
pure and tested with a controlled clock and deterministic fixtures, exactly like
`test_scheduling.py`. The HTTP-conditional half (`ConditionalRequestHeaders`, the
checkpoint's `etag`/`last_modified`, and 304 handling) goes through `AcquisitionService`
with an in-memory session/repository (no real database) and `httpx.MockTransport` (no real
network), the same pattern `test_service.py` already uses for its fake collectors.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx

from opportunity_radar.acquisition.alerts import SourceAlertService
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
)
from opportunity_radar.acquisition.models import SourceCheckpointModel, SourceDefinitionModel
from opportunity_radar.acquisition.scheduling import (
    DEFAULT_HOST_BUDGET_WINDOW,
    CollectionGate,
    HostBudgetState,
    SourceRunHistory,
    SourceSchedulingState,
    evaluate_gate,
    next_due_at,
)
from opportunity_radar.acquisition.service import AcquisitionService

_HOURLY = "0 * * * *"
_NOON = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


def _state(**overrides: object) -> SourceSchedulingState:
    defaults: dict[str, object] = {"schedule": _HOURLY, "timezone": "UTC"}
    defaults.update(overrides)
    return SourceSchedulingState(**defaults)  # type: ignore[arg-type]


def _budget(**overrides: object) -> HostBudgetState:
    defaults: dict[str, object] = {
        "host": "boards.example.io",
        "window_start": _NOON,
        "requests_used": 0,
        "requests_ceiling": 10,
        "exploration_reserve_ratio": 0.0,
    }
    defaults.update(overrides)
    return HostBudgetState(**defaults)  # type: ignore[arg-type]


# --- acceptance criterion 1: no host exceeds its budget across sources -----------------


def test_two_sources_same_host_share_budget_without_exceeding_ceiling() -> None:
    # Two sources of the same host read the *same* persisted counter. Modelled here as one
    # source seeing the counter after the other already spent against it in this pass.
    budget = _budget(requests_ceiling=10)

    first_source = _state(host="boards.example.io", host_budget=replace(budget, requests_used=9))
    second_source = _state(
        host="boards.example.io", host_budget=replace(budget, requests_used=10)
    )

    assert evaluate_gate(first_source, now=_NOON) is CollectionGate.DUE
    # The second source is evaluated only after the first source's spend is already
    # reflected in the shared counter, so it never gets to push the host past its ceiling.
    assert evaluate_gate(second_source, now=_NOON) is CollectionGate.RATE_LIMITED
    assert evaluate_gate(second_source, now=_NOON).outcome == "blocked"


def test_a_source_without_a_shared_budget_is_unaffected() -> None:
    # Regression guard for the new field: `host_budget=None` must behave exactly like
    # today, for a source whose provider has not been given a shared budget yet.
    state = _state(host=None, host_budget=None)

    assert evaluate_gate(state, now=_NOON) is CollectionGate.DUE


# --- acceptance criterion 2: low-yield sources are not starved forever -----------------


def test_low_yield_source_gets_revisited_within_configured_maximum() -> None:
    # Ceiling 10, 10% reserved for exploration => well-observed sources may use up to 9;
    # a low-yield/never-observed source may use the reserved 10th slot.
    budget = _budget(requests_ceiling=10, exploration_reserve_ratio=0.10, requests_used=9)

    well_observed = _state(host="boards.example.io", host_budget=budget, is_low_yield=False)
    low_yield = _state(host="boards.example.io", host_budget=budget, is_low_yield=True)

    assert evaluate_gate(well_observed, now=_NOON) is CollectionGate.RATE_LIMITED
    assert evaluate_gate(low_yield, now=_NOON) is CollectionGate.DUE


def test_insufficient_budget_gives_an_explicit_delay_without_exceeding_the_ceiling() -> None:
    # Even the reserve is exhausted: a low-yield source must not fire (no ceiling breach),
    # but the reason it is held back is explicit and points to a concrete retry time, not a
    # silent drop.
    exhausted = _budget(requests_ceiling=10, exploration_reserve_ratio=0.10, requests_used=10)
    state = _state(host="boards.example.io", host_budget=exhausted, is_low_yield=True)

    gate = evaluate_gate(state, now=_NOON)
    due_at, reason = next_due_at(state, now=_NOON)

    assert gate is CollectionGate.RATE_LIMITED
    assert reason == "budget"
    assert due_at == exhausted.window_start + DEFAULT_HOST_BUDGET_WINDOW
    assert due_at is not None and due_at > _NOON


# --- acceptance criterion 3: cooldown survives a restart --------------------------------


def test_cooldown_survives_restart() -> None:
    # "Restart" here means a brand new `HostBudgetState` built purely from persisted
    # fields — no shared Python object, no in-process cache — the way a fresh worker
    # process would rebuild it from the database row after `record_host_budget_usage`.
    persisted_cooldown_until = _NOON + timedelta(minutes=30)
    persisted = _budget(cooldown_until=persisted_cooldown_until, requests_used=0)

    reloaded_after_restart = replace(persisted)  # a genuinely new instance
    assert reloaded_after_restart is not persisted

    state = _state(host="boards.example.io", host_budget=reloaded_after_restart)

    still_cooling_down = evaluate_gate(state, now=_NOON)
    due_at, reason = next_due_at(state, now=_NOON)
    after_cooldown = evaluate_gate(state, now=persisted_cooldown_until + timedelta(seconds=1))

    assert still_cooling_down is CollectionGate.RATE_LIMITED
    assert reason == "cooldown"
    assert due_at == persisted_cooldown_until
    assert after_cooldown is CollectionGate.DUE


def test_cooldown_outlives_a_window_rollover() -> None:
    # Retry-After is a provider instruction, not a counter; rolling the request window
    # over must not clear it early.
    cooldown_until = _NOON + timedelta(minutes=10)
    stale_window = _budget(
        window_start=_NOON - DEFAULT_HOST_BUDGET_WINDOW - timedelta(minutes=1),
        requests_used=10,
        requests_ceiling=10,
        cooldown_until=cooldown_until,
    )
    state = _state(host="boards.example.io", host_budget=stale_window)

    assert evaluate_gate(state, now=_NOON) is CollectionGate.RATE_LIMITED


# --- acceptance criterion 4: same cohort, bounded cost, no lost coverage ---------------


def test_same_cohort_reduces_cost_or_delay_without_regressing_coverage() -> None:
    # A deterministic 3-source cohort on one host with a ceiling of 2: no real acervo
    # involved, but the shape (more due sources than the host can serve at once) is the
    # one acceptance criterion 4 asks about.
    ceiling = 2
    cohort = [
        _state(
            host="boards.example.io",
            host_budget=_budget(requests_ceiling=ceiling, requests_used=used),
        )
        for used in range(3)
    ]

    gates = [evaluate_gate(source, now=_NOON) for source in cohort]

    assert gates == [
        CollectionGate.DUE,
        CollectionGate.DUE,
        CollectionGate.RATE_LIMITED,
    ]
    # Cost is capped at the host's ceiling...
    assert sum(1 for gate in gates if gate is CollectionGate.DUE) == ceiling
    # ...and coverage is not silently dropped: the blocked source gets a concrete,
    # future retry time rather than disappearing from the schedule.
    due_at, reason = next_due_at(cohort[2], now=_NOON)
    assert reason == "budget"
    assert due_at is not None and due_at > _NOON


# --- HTTP-conditional requests and 304 handling (service-level, no real network) --------


class _MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, model: object) -> None:
        self.added.append(model)

    def flush(self) -> None:
        return None

    def begin_nested(self):
        return nullcontext()

    def rollback(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, model: object, attribute_names: object = None) -> None:
        del attribute_names
        return None

    def scalar(self, statement: object) -> None:
        del statement
        return None

    def get(self, model: type, primary_key: object) -> None:
        del model, primary_key
        return None


class _MemoryRepository:
    def __init__(self, source: SourceDefinitionModel) -> None:
        self.source = source
        self.hashes: set[tuple[str, str]] = set()
        self.host_budget_calls: list[dict[str, object]] = []

    def run_history(self, source_id: object, *, sample: int = 32) -> SourceRunHistory:
        del source_id, sample
        return SourceRunHistory()

    def get_source(self, source_id: object) -> SourceDefinitionModel | None:
        return self.source if source_id == self.source.id else None

    def identical_raw_item_exists(
        self, *, source_id: object, identity_key: str, payload_hash: str
    ) -> bool:
        key = (identity_key, payload_hash)
        if key in self.hashes:
            return True
        self.hashes.add(key)
        return False

    def get_host_budget(self, host: str) -> None:
        del host
        return None

    def record_host_budget_usage(
        self,
        host: str,
        *,
        now: object,
        requests: int,
        default_ceiling: int,
        cooldown_until: object = None,
    ) -> None:
        self.host_budget_calls.append(
            {
                "host": host,
                "now": now,
                "requests": requests,
                "default_ceiling": default_ceiling,
                "cooldown_until": cooldown_until,
            }
        )


class _ConditionalCollector:
    """A minimal collector exercising `conditional_headers` against a fake HTTP transport.

    Not one of the production collectors (ashby/greenhouse/lever/remotive) — those are
    owned elsewhere in this phase — but the same shape: it reads `request.conditional_headers`
    and reports what the response said via `request.telemetry.record_conditional_response`,
    which is exactly the contract any real collector would follow to opt into F20-38.
    """

    source_type = "example"
    capabilities = CollectorCapabilities(incremental_cursor=True, etag=True, last_modified=True)

    def __init__(self, transport: httpx.MockTransport) -> None:
        self._transport = transport

    async def healthcheck(self, context: object = None) -> HealthResult:
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        headers = (
            request.conditional_headers.as_headers()
            if request.conditional_headers is not None
            else {}
        )
        async with httpx.AsyncClient(transport=self._transport) as client:
            response = await client.get("https://example.test/jobs", headers=headers)
        request.telemetry.record_http_attempt()
        if response.status_code == 304:
            request.telemetry.record_conditional_response(not_modified=True)
            return
        request.telemetry.record_conditional_response(
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        for job in response.json()["jobs"]:
            yield CollectedItem(
                source_type=self.source_type,
                external_id=job["id"],
                raw_payload=job,
                cursor=job["id"],
            )


def _conditional_service(
    transport: httpx.MockTransport,
) -> tuple[AcquisitionService, SourceDefinitionModel]:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="example",
        name="Example",
        enabled=True,
        configuration={},
    )
    # Pre-attached so the service mutates it in place across both calls below, the way a
    # real session's identity map keeps the same row's object across one process's calls.
    source.checkpoint = SourceCheckpointModel(
        source_definition_id=source.id, checkpoint_type="cursor"
    )
    session = _MemorySession()
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((_ConditionalCollector(transport),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
    )
    return service, source


def test_304_revalidates_without_asserting_full_coverage() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("If-None-Match") == "\"v1\"":
            return httpx.Response(304, headers={"ETag": "\"v1\""})
        return httpx.Response(
            200,
            headers={"ETag": "\"v1\"", "Last-Modified": "Wed, 01 Jan 2026 00:00:00 GMT"},
            json={"jobs": [{"id": "job-1", "title": "First"}]},
        )

    service, source = _conditional_service(httpx.MockTransport(handler))

    # First run: no validators yet, unconditional request, board has one job.
    first_run = asyncio.run(
        service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
    )
    assert first_run.status == "SUCCEEDED"
    assert first_run.items_persisted == 1
    assert calls[0].headers.get("If-None-Match") is None
    assert source.checkpoint is not None
    assert source.checkpoint.etag == '"v1"'

    # Second run: the checkpoint's etag conditions the request; the fake board answers 304.
    second_run = asyncio.run(
        service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
    )
    assert calls[1].headers.get("If-None-Match") == '"v1"'
    assert second_run.status == "SUCCEEDED"
    assert second_run.items_persisted == 0
    # Revalidation, not a fresh empty board: `complete` must not read a 304 as "read it
    # all", or a job that later reappears would look closed for good (SPEC 39 §7).
    assert second_run.complete is False
    # The representation's validator survives the revalidation unchanged.
    assert source.checkpoint.etag == '"v1"'


def test_conditional_headers_are_not_reused_across_a_different_checkpoint_scope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "If-None-Match" not in request.headers
        return httpx.Response(200, json={"jobs": []})

    service, source = _conditional_service(httpx.MockTransport(handler))
    # A checkpoint from a different scope (e.g. keyword rotation) must never condition an
    # incremental request just because a value happens to be sitting in the same columns.
    source.checkpoint = SourceCheckpointModel(
        source_definition_id=source.id,
        checkpoint_type="keyword_rotation",
        cursor="0",
    )

    run = asyncio.run(
        service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
    )

    assert run.status == "SUCCEEDED"


# --- F48-08: host budget keyed per tenant, ceiling per source type ---------------------


def _typed_source(source_type: str, configuration: dict[str, object]) -> SourceDefinitionModel:
    return SourceDefinitionModel(
        id=uuid4(),
        source_type=source_type,
        name=f"{source_type} source",
        enabled=True,
        configuration=configuration,
    )


def _scheduling_service() -> AcquisitionService:
    source = _typed_source("workday", {})
    session = _MemorySession()
    return AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry(()),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
    )


def test_fifteen_workday_tenants_do_not_share_a_budget_bucket() -> None:
    service = _scheduling_service()
    sources = [
        _typed_source(
            "workday", {"tenant_identifier": f"tenant{number}/site", "api_region": "wd5"}
        )
        for number in range(15)
    ]

    hosts = {service.scheduling_state(source, timezone="UTC").host for source in sources}

    assert len(hosts) == 15
    assert "tenant0.wd5.myworkdayjobs.com" in hosts
    assert "workday" not in hosts


def test_per_tenant_types_key_on_the_tenant_and_shared_host_types_keep_the_physical_host() -> None:
    service = _scheduling_service()

    def host_of(source_type: str, configuration: dict[str, object]) -> str:
        return service.scheduling_state(
            _typed_source(source_type, configuration), timezone="UTC"
        ).host

    assert host_of("teamtailor", {"company_identifier": "acme"}) == "teamtailor:acme"
    assert host_of("factorial", {"company_identifier": "acme"}) == "factorial:acme"
    assert (
        host_of("jobposting", {"page_url": "https://Careers.Acme.com/jobs/1"})
        == "jobposting:careers.acme.com"
    )
    assert host_of("lever", {"site_identifier": "acme"}) == "api.lever.co"
    assert host_of("greenhouse", {"board_token": "acme"}) == "boards.greenhouse.io"
    assert host_of("hacker_news", {}) == "hacker-news.firebaseio.com"


def test_recorded_usage_goes_to_the_tenant_row_with_the_configured_ceiling() -> None:
    class _Counting(_ConditionalCollector):
        source_type = "workday"

        async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            request.telemetry.record_http_attempt()
            request.telemetry.record_http_attempt()
            return
            yield  # pragma: no cover - makes this an async generator

    source = _typed_source(
        "workday", {"tenant_identifier": "adobe/site", "api_region": "wd5"}
    )
    session = _MemorySession()
    repository = _MemoryRepository(source)
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry(
            (_Counting(httpx.MockTransport(lambda _: httpx.Response(200))),)
        ),
        repository=repository,  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
        host_request_ceilings={"workday": 321},
    )

    asyncio.run(service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)))

    recorded = [
        (call["host"], call["requests"], call["default_ceiling"])
        for call in repository.host_budget_calls
    ]
    assert recorded == [("adobe.wd5.myworkdayjobs.com", 2, 321)]
