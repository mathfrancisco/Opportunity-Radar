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
from opportunity_radar.acquisition.remotive import RemotiveCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "remotive_remote_jobs.json"


async def _collect(collector: RemotiveCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_queries_maps_and_preserves_public_payload() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(keywords=("python", "remote"), max_items=1)
    try:
        items = asyncio.run(_collect(RemotiveCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == (
        "https://remotive.com/api/remote-jobs?search=python+remote&limit=1"
    )
    assert [item.external_id for item in items] == ["200001"]
    item = items[0]
    assert item.url == payload["jobs"][0]["url"]
    assert item.title == "Senior Python Engineer"
    assert item.company_name == "Acme Remote"
    assert item.location_text == "Brazil"
    assert item.description == payload["jobs"][0]["description"]
    assert item.published_at is not None
    assert item.raw_payload == payload["jobs"][0]
    assert item.metadata["category"] == "Software Development"
    assert item.metadata["attribution"] == "Remotive"
    assert item.metadata["parser_version"] == "remotive-remote-jobs-v1"
    assert request.telemetry.http_requests == 1


def test_retries_rate_limit_and_records_telemetry() -> None:
    calls = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"job-count": 0, "jobs": []})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        network_policy=CollectionNetworkPolicy(
            max_retries=1, max_retry_delay_seconds=3
        )
    )
    try:
        items = asyncio.run(
            _collect(RemotiveCollector(client=client, sleeper=sleeper), request)
        )
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert calls == 2
    assert delays == [3]
    assert request.telemetry.http_requests == 2
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
                    RemotiveCollector(client=client, max_retries=0),
                    CollectionRequest(),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (httpx.ReadTimeout("timed out"), AcquisitionErrorCode.SOURCE_TIMEOUT),
        (
            httpx.ConnectError("offline"),
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
        ),
    ],
)
def test_classifies_transport_errors(
    failure: httpx.HTTPError, code: AcquisitionErrorCode
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise failure

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    RemotiveCollector(client=client, max_retries=0),
                    CollectionRequest(),
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
        {"jobs": [], "job-count": True},
        {"jobs": [], "job-count": -1},
        {"jobs": [], "job-count": 1},
    ],
)
def test_rejects_invalid_response_schema(payload: object) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(RemotiveCollector(client=client), CollectionRequest())
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_skips_invalid_job_without_losing_valid_jobs() -> None:
    request = CollectionRequest()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "job-count": 2,
                    "jobs": [
                        {"id": 1, "title": "Broken"},
                        {
                            "id": 2,
                            "url": "https://remotive.com/remote-jobs/dev/valid-2",
                            "title": "Valid",
                        },
                    ],
                },
            )
        )
    )
    try:
        items = asyncio.run(_collect(RemotiveCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert [item.external_id for item in items] == ["2"]
    assert request.telemetry.invalid_items == 1
