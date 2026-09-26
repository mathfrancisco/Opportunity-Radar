import asyncio
import json
from pathlib import Path

import httpx
import pytest

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionNetworkPolicy,
    CollectionRequest,
)
from opportunity_radar.acquisition.lever import LeverCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "lever_postings.json"


async def _collect(collector: LeverCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_maps_payload_and_requests_global_api() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference="acme", company_name="Acme")
    try:
        items = asyncio.run(_collect(LeverCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == (
        "https://api.lever.co/v0/postings/acme?mode=json&skip=0&limit=100"
    )
    assert [item.external_id for item in items] == [
        payload[0]["id"],
        payload[1]["id"],
    ]
    assert items[0].url == payload[0]["hostedUrl"]
    assert items[0].title == "Senior Backend Engineer"
    assert items[0].company_name == "Acme"
    assert items[0].location_text == "Sao Paulo, Brazil"
    assert items[0].description == "Build dependable services for customers."
    assert items[0].raw_payload == payload[0]
    assert items[0].metadata["categories"] == payload[0]["categories"]
    assert items[0].metadata["country"] == "BR"
    assert items[0].metadata["parser_version"] == "lever-postings-v1"
    assert collection_request.telemetry.http_requests == 1


def test_uses_eu_api_and_paginates_until_short_page() -> None:
    calls: list[httpx.Request] = []
    delays: list[float] = []
    first_page = [
        {"id": f"job-{number}", "hostedUrl": f"https://jobs.lever.co/acme/{number}"}
        for number in range(100)
    ]
    second_page = [{"id": "job-last", "hostedUrl": "https://jobs.lever.co/acme/last"}]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=first_page if len(calls) == 1 else second_page)

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(
        company_reference="acme",
        api_region="eu",
        network_policy=CollectionNetworkPolicy(
            minimum_interval_seconds=2,
            max_retry_delay_seconds=30,
        ),
    )
    try:
        items = asyncio.run(
            _collect(
                LeverCollector(client=client, sleeper=sleeper),
                collection_request,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert len(items) == 101
    assert calls[0].url.host == "api.eu.lever.co"
    assert calls[1].url.params["skip"] == "100"
    assert len(delays) == 1
    assert 0 < delays[0] <= 2
    # A short final page is how Lever signals the whole board was read: the announced
    # count is the sum of every page fetched, matching what was actually seen.
    assert collection_request.telemetry.items_announced == 101


def test_repeated_page_raises_instead_of_claiming_complete_board() -> None:
    page = [
        {
            "id": f"job-{number}",
            "hostedUrl": f"https://jobs.lever.co/acme/{number}",
        }
        for number in range(100)
    ]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=page)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    LeverCollector(client=client),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())

    assert error.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED
    assert [call.url.params["skip"] for call in calls] == ["0", "100"]


def test_stops_at_max_items() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    collection_request = CollectionRequest(company_reference="acme", max_items=1)
    try:
        items = asyncio.run(
            _collect(
                LeverCollector(client=client),
                collection_request,
            )
        )
    finally:
        asyncio.run(client.aclose())
    assert len(items) == 1
    # Capped by max_items: the collector never learns whether the board had more, so it
    # must not claim an announced total.
    assert collection_request.telemetry.items_announced is None


def test_retries_rate_limit_with_network_policy() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json=[])

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme",
        network_policy=CollectionNetworkPolicy(max_retries=1, max_retry_delay_seconds=3),
    )
    try:
        assert (
            asyncio.run(_collect(LeverCollector(client=client, sleeper=sleeper), request))
            == []
        )
    finally:
        asyncio.run(client.aclose())
    assert calls == 2
    assert delays == [3]
    assert request.telemetry.retry_count == 1
    assert request.telemetry.rate_limit_events == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, AcquisitionErrorCode.SOURCE_UNAUTHORIZED),
        (403, AcquisitionErrorCode.SOURCE_FORBIDDEN),
        (404, AcquisitionErrorCode.SOURCE_NOT_FOUND),
        (500, AcquisitionErrorCode.SOURCE_SERVER_ERROR),
    ],
)
def test_classifies_http_errors(status: int, code: AcquisitionErrorCode) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    LeverCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


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
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(failure))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    LeverCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


def test_rejects_invalid_configuration_and_schema_and_skips_bad_item() -> None:
    with pytest.raises(AcquisitionError) as invalid_slug:
        asyncio.run(
            _collect(LeverCollector(), CollectionRequest(company_reference="acme/jobs"))
        )
    assert invalid_slug.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    try:
        with pytest.raises(AcquisitionError) as invalid_schema:
            asyncio.run(
                _collect(
                    LeverCollector(client=client),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert invalid_schema.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED

    request = CollectionRequest(company_reference="acme")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda http_request: httpx.Response(
                200,
                json=[
                    {"id": "broken"},
                    {"id": "valid", "hostedUrl": "https://jobs.lever.co/acme/valid"},
                ],
            )
        )
    )
    try:
        items = asyncio.run(_collect(LeverCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["valid"]
    assert request.telemetry.invalid_items == 1
