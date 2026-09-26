"""Integration test for the per-run Tavily credit budget (F20-43).

`TavilyCreditBudget` and `SourceRun.record_credits` are the reusable primitives; the
collector that will drive them through a real discovery loop is F20-44. Here a small
harness plays that role directly against `TavilyClient` so the whole path — budget guard,
client call, credit bookkeeping, run outcome — is proven end to end without a real
collector or a real Tavily call.
"""

import asyncio
from contextlib import nullcontext
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionRequest,
    CollectionTelemetry,
    SourceRun,
    SourceRunStatus,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel, SourceRunModel
from opportunity_radar.acquisition.scheduling import SourceRunHistory
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import (
    TavilyClient,
    TavilyCreditBudget,
    TavilySearchCollector,
)


async def _run_bounded_searches(
    client: TavilyClient,
    budget: TavilyCreditBudget,
    run: SourceRun,
    queries: list[str],
) -> None:
    telemetry = CollectionTelemetry()
    for query in queries:
        try:
            budget.ensure_can_call()
        except AcquisitionError as error:
            run.finish(SourceRunStatus.PARTIAL, error=error)
            return
        response = await client.search(query=query, telemetry=telemetry)
        budget.charge(response.credits_used)
        run.record_credits(response.credits_used or 0)
    run.finish(SourceRunStatus.SUCCEEDED)


def _client(credits_per_call: int) -> TavilyClient:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"results": [], "usage": {"credits": credits_per_call}}
        )

    return TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_run_stops_new_calls_once_budget_exhausted_and_ends_partial() -> None:
    client = _client(credits_per_call=1)
    budget = TavilyCreditBudget(limit=2)
    run = SourceRun(source_definition_id=uuid4())
    run.start()

    try:
        asyncio.run(
            _run_bounded_searches(client, budget, run, ["a", "b", "c", "d"])
        )
    finally:
        asyncio.run(client.aclose())

    assert run.status is SourceRunStatus.PARTIAL
    assert run.status is not SourceRunStatus.FAILED
    assert run.credits_used == 2
    assert run.error_code is AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED
    assert run.error_summary is not None
    assert "budget" in run.error_summary.lower()
    # Distinguishable from a 429 or a network failure: neither of those codes appears.
    assert run.error_code is not AcquisitionErrorCode.SOURCE_RATE_LIMITED
    assert run.error_code is not AcquisitionErrorCode.SOURCE_TIMEOUT
    assert run.error_code is not AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR


def test_run_below_budget_finishes_succeeded_with_credits_recorded() -> None:
    client = _client(credits_per_call=1)
    budget = TavilyCreditBudget(limit=5)
    run = SourceRun(source_definition_id=uuid4())
    run.start()

    try:
        asyncio.run(_run_bounded_searches(client, budget, run, ["a", "b"]))
    finally:
        asyncio.run(client.aclose())

    assert run.status is SourceRunStatus.SUCCEEDED
    assert run.credits_used == 2
    assert run.error_code is None


def test_budget_is_per_instance_not_shared_across_runs() -> None:
    budget_a = TavilyCreditBudget(limit=1)
    budget_b = TavilyCreditBudget(limit=1)

    budget_a.charge(1)

    assert budget_a.exhausted
    assert not budget_b.exhausted


def test_negative_limit_or_spend_is_rejected() -> None:
    with pytest.raises(ValueError):
        TavilyCreditBudget(limit=-1)
    with pytest.raises(ValueError):
        TavilyCreditBudget(limit=10).charge(-1)


def test_source_run_records_credits_only_while_running() -> None:
    run = SourceRun(source_definition_id=uuid4())
    with pytest.raises(AcquisitionError):
        run.record_credits(1)

    run.start()
    run.record_credits(3)
    run.record_credits(2)

    assert run.credits_used == 5

    with pytest.raises(ValueError):
        run.record_credits(-1)


def test_credits_used_persists_on_source_run_model() -> None:
    """`SourceRun.credits_used` must survive the domain-to-model copy, otherwise
    `record_credits()` is lost on every flush and the spend is not auditable (F20-43
    follow-up)."""
    run = SourceRun(source_definition_id=uuid4())
    run.start()
    run.record_credits(7)
    run.finish(SourceRunStatus.SUCCEEDED)
    model = SourceRunModel(id=run.id, source_definition_id=run.source_definition_id)

    AcquisitionService._copy_run(run, model)

    assert model.credits_used == 7


class _MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, model: object) -> None:
        self.added.append(model)

    def flush(self) -> None:
        return None

    def begin_nested(self):
        return nullcontext()

    def commit(self) -> None:
        self.committed = True

    def refresh(self, model: object, attribute_names: object = None) -> None:
        del model, attribute_names


class _Repository:
    def __init__(self, source: SourceDefinitionModel) -> None:
        self.source = source
        self.hashes: set[tuple[object, object]] = set()

    def get_source(self, source_id: object) -> SourceDefinitionModel | None:
        return self.source if source_id == self.source.id else None

    def run_history(self, source_id: object) -> SourceRunHistory:
        del source_id
        return SourceRunHistory()

    def identical_raw_item_exists(
        self, *, source_id: object, identity_key: object, payload_hash: object
    ) -> bool:
        del source_id
        key = (identity_key, payload_hash)
        if key in self.hashes:
            return True
        self.hashes.add(key)
        return False


class _Alerts:
    def record_run_outcome(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


def _service_with_tavily_collector(
    *, credits_per_call: int, budget: int, results: list[dict[str, object]] | None = None
) -> tuple[AcquisitionService, _MemorySession, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"results": results or [], "usage": {"credits": credits_per_call}},
        )

    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="tavily_search",
        name="Tavily",
        enabled=True,
        configuration={},
    )
    session = _MemorySession()
    collector = TavilySearchCollector(
        client=TavilyClient(
            api_key="test-key",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
        credit_budget_per_run=budget,
    )
    return (
        AcquisitionService(
            session,  # type: ignore[arg-type]
            registry=CollectorRegistry((collector,)),
            repository=_Repository(source),  # type: ignore[arg-type]
            alerts=_Alerts(),  # type: ignore[arg-type]
        ),
        session,
        requests,
    )


def test_execute_persists_tavily_credits_below_budget() -> None:
    service, session, requests = _service_with_tavily_collector(
        credits_per_call=2, budget=3
    )

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(keywords=("backend",)),
        )
    )

    assert run.status == SourceRunStatus.SUCCEEDED.value
    assert run.credits_used == 2
    assert run.error_code is None
    assert len(requests) == 1
    assert session.committed


def test_execute_stops_at_tavily_budget_with_distinct_partial_error() -> None:
    service, session, requests = _service_with_tavily_collector(
        credits_per_call=2, budget=2
    )

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(keywords=("backend",)),
        )
    )

    assert run.status == SourceRunStatus.PARTIAL.value
    assert run.credits_used == 2
    assert run.error_code == AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED.value
    assert run.error_code != AcquisitionErrorCode.SOURCE_RATE_LIMITED.value
    assert run.error_code != AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR.value
    assert len(requests) == 1
    assert session.committed


def test_execute_persists_paid_tavily_results_before_budget_partial() -> None:
    service, _, requests = _service_with_tavily_collector(
        credits_per_call=2,
        budget=2,
        results=[
            {
                "url": "https://example.com/jobs/1",
                "title": "Backend Engineer",
                "content": "Role details",
                "score": 0.9,
            }
        ],
    )

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(keywords=("backend",)),
        )
    )

    assert run.status == SourceRunStatus.PARTIAL.value
    assert run.credits_used == 2
    assert run.items_persisted == 1
    assert len(requests) == 1
