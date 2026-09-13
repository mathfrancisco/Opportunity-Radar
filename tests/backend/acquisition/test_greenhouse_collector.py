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
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "greenhouse_job_board.json"


async def _collect(collector: GreenhouseCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_maps_public_board_payload_and_preserves_raw_job() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(company_reference="acme", company_name="Acme")
    try:
        items = asyncio.run(_collect(GreenhouseCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == (
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    )
    assert [item.external_id for item in items] == ["84102", "84103"]
    assert items[0].url == payload["jobs"][0]["absolute_url"]
    assert items[0].title == "Senior Backend Engineer"
    assert items[0].company_name == "Acme"
    assert items[0].location_text == "Sao Paulo, Brazil"
    assert items[0].description == payload["jobs"][0]["content"]
    assert items[0].updated_at is not None
    assert items[0].raw_payload == payload["jobs"][0]
    assert items[0].metadata["internal_job_id"] == 9001
    assert (
        items[0].metadata["greenhouse_metadata"]
        == payload["jobs"][0]["metadata"]
    )
    assert items[0].metadata["parser_version"] == "greenhouse-job-board-v1"
    assert request.telemetry.http_requests == 1


def test_stops_at_max_items() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    try:
        items = asyncio.run(
            _collect(
                GreenhouseCollector(client=client),
                CollectionRequest(company_reference="acme", max_items=1),
            )
        )
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["84102"]


def test_retries_rate_limit_with_bounded_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"jobs": [], "meta": {"total": 0}})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme",
        network_policy=CollectionNetworkPolicy(
            max_retries=1,
            max_retry_delay_seconds=3,
        ),
    )
    try:
        items = asyncio.run(
            _collect(GreenhouseCollector(client=client, sleeper=sleeper), request)
        )
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert calls == 2
    assert delays[0] == 3
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
        transport=httpx.MockTransport(lambda _: httpx.Response(status))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    GreenhouseCollector(client=client, max_retries=0),
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
        transport=httpx.MockTransport(lambda _: (_ for _ in ()).throw(failure))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    GreenhouseCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"jobs": {}},
        {"jobs": []},
        {"jobs": [], "meta": {}},
        {"jobs": [], "meta": {"total": True}},
        {"jobs": [], "meta": {"total": -1}},
    ],
)
def test_rejects_invalid_response_schema(payload: object) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    GreenhouseCollector(client=client),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())

    assert error.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_rejects_invalid_configuration_and_skips_invalid_job() -> None:
    with pytest.raises(AcquisitionError) as invalid_token:
        asyncio.run(
            _collect(
                GreenhouseCollector(), CollectionRequest(company_reference="acme/jobs")
            )
        )
    assert invalid_token.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    request = CollectionRequest(company_reference="acme")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "jobs": [
                        {"id": 1, "title": "Broken"},
                        {
                            "id": 2,
                            "title": "Valid",
                            "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
                        },
                    ],
                    "meta": {"total": 2},
                },
            )
        )
    )
    try:
        items = asyncio.run(_collect(GreenhouseCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["2"]
    assert request.telemetry.invalid_items == 1
