"""Every collector's default client identifies the product; an injected client is kept."""

import asyncio

import httpx
import pytest

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.domain import CollectionRequest
from opportunity_radar.acquisition.factorial import FactorialCollector
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.hacker_news import HackerNewsCollector
from opportunity_radar.acquisition.http_client import COLLECTOR_USER_AGENT
from opportunity_radar.acquisition.jobposting import JobPostingCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.acquisition.tavily import TavilyClient
from opportunity_radar.acquisition.teamtailor import TeamtailorCollector
from opportunity_radar.acquisition.workable import WorkableCollector
from opportunity_radar.acquisition.workday import WorkdayCollector

_EMPTY_BOARD = {
    AshbyCollector: {"apiVersion": "1", "jobs": []},
    GreenhouseCollector: {"jobs": [], "meta": {"total": 0}},
    LeverCollector: [],
}

_COLLECTORS = [
    AshbyCollector,
    GreenhouseCollector,
    LeverCollector,
    WorkableCollector,
    WorkdayCollector,
    TeamtailorCollector,
    FactorialCollector,
    RemotiveCollector,
    JobPostingCollector,
    HackerNewsCollector,
    lambda: TavilyClient(api_key="key"),
]


@pytest.mark.parametrize("build", _COLLECTORS)
def test_default_client_sends_the_product_user_agent(build) -> None:
    async def default_agent() -> str:
        async with build()._client_factory() as client:
            return client.headers["User-Agent"]

    assert asyncio.run(default_agent()) == COLLECTOR_USER_AGENT
    assert "python-httpx" not in COLLECTOR_USER_AGENT


@pytest.mark.parametrize("collector_class", [AshbyCollector, GreenhouseCollector, LeverCollector])
def test_default_client_user_agent_reaches_the_wire(collector_class, monkeypatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, json=_EMPTY_BOARD[collector_class])

    import opportunity_radar.acquisition.http_client as http_client

    real = http_client.httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def run() -> None:
        request = CollectionRequest(company_reference="acme", company_name="Acme")
        _ = [item async for item in collector_class().discover(request)]

    asyncio.run(run())
    assert seen == [COLLECTOR_USER_AGENT]


@pytest.mark.parametrize("collector_class", [AshbyCollector, GreenhouseCollector, LeverCollector])
def test_injected_client_user_agent_is_not_overridden(collector_class) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, json=_EMPTY_BOARD[collector_class])

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers={"User-Agent": "test-agent"}
    )

    async def run() -> None:
        request = CollectionRequest(company_reference="acme", company_name="Acme")
        _ = [item async for item in collector_class(client=client).discover(request)]
        await client.aclose()

    asyncio.run(run())
    assert seen == ["test-agent"]
