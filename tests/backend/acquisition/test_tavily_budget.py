"""Integration test for the per-run Tavily credit budget (F20-43).

`TavilyCreditBudget` and `SourceRun.record_credits` are the reusable primitives; the
collector that will drive them through a real discovery loop is F20-44. Here a small
harness plays that role directly against `TavilyClient` so the whole path — budget guard,
client call, credit bookkeeping, run outcome — is proven end to end without a real
collector or a real Tavily call.
"""

import asyncio
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionTelemetry,
    SourceRun,
    SourceRunStatus,
)
from opportunity_radar.acquisition.models import SourceRunModel
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyCreditBudget


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
    assert run.error_code is AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED
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
