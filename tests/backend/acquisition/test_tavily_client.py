import asyncio

import httpx
import pytest

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionNetworkPolicy,
    CollectionTelemetry,
)
from opportunity_radar.acquisition.tavily import TavilyClient


def _client(handler, **kwargs) -> TavilyClient:
    return TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


async def _aclose(client: TavilyClient) -> None:
    await client.aclose()


def test_search_sends_authenticated_request_without_auto_parameters() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://boards.greenhouse.io/acme/1",
                        "title": "Backend",
                        "content": "desc",
                        "score": 0.9,
                    },
                ],
                "usage": {"credits": 1},
            },
        )

    client = _client(handler)
    try:
        response = asyncio.run(
            client.search(
                query="backend engineer",
                telemetry=CollectionTelemetry(),
            )
        )
    finally:
        asyncio.run(_aclose(client))

    request = calls[0]
    assert str(request.url) == "https://api.tavily.com/search"
    assert request.headers["Authorization"] == "Bearer test-key"
    import json as _json

    payload = _json.loads(calls[0].content)
    assert payload["query"] == "backend engineer"
    assert payload["search_depth"] == "basic"
    assert payload["topic"] == "general"
    assert payload["include_usage"] is True
    assert "auto_parameters" not in payload
    assert response.results[0].url == "https://boards.greenhouse.io/acme/1"
    assert response.results[0].title == "Backend"
    assert response.credits_used == 1


def test_extract_sends_urls_and_reads_credits() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/job", "raw_content": "# Job\nbody"},
                ],
                "failed_results": [],
                "usage": {"credits": 1},
            },
        )

    client = _client(handler)
    try:
        response = asyncio.run(
            client.extract(
                urls=["https://example.com/job"],
                telemetry=CollectionTelemetry(),
            )
        )
    finally:
        asyncio.run(_aclose(client))

    import json as _json

    payload = _json.loads(calls[0].content)
    assert payload["urls"] == ["https://example.com/job"]
    assert payload["extract_depth"] == "basic"
    assert payload["format"] == "markdown"
    assert payload["include_usage"] is True
    assert "auto_parameters" not in payload
    assert response.results[0].raw_content == "# Job\nbody"
    assert response.credits_used == 1


def test_retries_rate_limit_with_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"results": [], "usage": {"credits": 0}})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        sleeper=sleeper,
    )
    telemetry = CollectionTelemetry()
    try:
        asyncio.run(
            client.search(
                query="x",
                telemetry=telemetry,
                network_policy=CollectionNetworkPolicy(
                    max_retries=1, max_retry_delay_seconds=3
                ),
            )
        )
    finally:
        asyncio.run(_aclose(client))

    assert calls == 2
    assert delays == [3]
    assert telemetry.http_requests == 2
    assert telemetry.retry_count == 1
    assert telemetry.rate_limit_events == 1


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, AcquisitionErrorCode.SOURCE_UNAUTHORIZED, False),
        (403, AcquisitionErrorCode.SOURCE_FORBIDDEN, False),
        (429, AcquisitionErrorCode.SOURCE_RATE_LIMITED, True),
        (500, AcquisitionErrorCode.SOURCE_SERVER_ERROR, True),
        (503, AcquisitionErrorCode.SOURCE_SERVER_ERROR, True),
        (433, AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED, False),
    ],
)
def test_classifies_http_errors(
    status: int, code: AcquisitionErrorCode, retryable: bool
) -> None:
    client = TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status))
        ),
        max_retries=0,
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                client.search(query="x", telemetry=CollectionTelemetry())
            )
    finally:
        asyncio.run(_aclose(client))
    assert error.value.code is code
    assert error.value.retryable is retryable


def test_432_maps_to_invalid_configuration_with_field() -> None:
    client = TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(432))
        ),
        max_retries=0,
    )
    try:
        with pytest.raises(AcquisitionError) as search_error:
            asyncio.run(client.search(query="x", telemetry=CollectionTelemetry()))
        with pytest.raises(AcquisitionError) as extract_error:
            asyncio.run(
                client.extract(
                    urls=["https://example.com"], telemetry=CollectionTelemetry()
                )
            )
    finally:
        asyncio.run(_aclose(client))
    assert search_error.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION
    assert search_error.value.field == "search_depth"
    assert extract_error.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION
    assert extract_error.value.field == "extract_depth"


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (httpx.ReadTimeout("timed out"), AcquisitionErrorCode.SOURCE_TIMEOUT),
        (httpx.ConnectError("offline"), AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR),
    ],
)
def test_classifies_transport_errors(
    failure: httpx.HTTPError, code: AcquisitionErrorCode
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise failure

    client = TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_retries=0,
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(client.search(query="x", telemetry=CollectionTelemetry()))
    finally:
        asyncio.run(_aclose(client))
    assert error.value.code is code


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"results": {}},
        {"results": [{"title": "no url"}]},
    ],
)
def test_rejects_invalid_search_schema(payload: object) -> None:
    client = TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=payload)
            )
        ),
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(client.search(query="x", telemetry=CollectionTelemetry()))
    finally:
        asyncio.run(_aclose(client))
    assert error.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_healthcheck_reports_blocked_by_configuration_without_key() -> None:
    client = TavilyClient(api_key=None)
    result = asyncio.run(client.healthcheck())
    assert result.healthy is True
    assert result.summary is not None
    assert "TAVILY_API_KEY" in result.summary


def test_healthcheck_reports_configured_with_key() -> None:
    client = TavilyClient(api_key="test-key")
    result = asyncio.run(client.healthcheck())
    assert result.healthy is True


def test_search_without_key_raises_invalid_configuration() -> None:
    client = TavilyClient(api_key=None)
    with pytest.raises(AcquisitionError) as error:
        asyncio.run(client.search(query="x", telemetry=CollectionTelemetry()))
    assert error.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION
