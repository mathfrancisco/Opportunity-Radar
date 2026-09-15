import asyncio
import json
from pathlib import Path

import httpx
import pytest

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionNetworkPolicy,
    CollectionRequest,
)

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "ashby_job_board.json"


async def _collect(collector: AshbyCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_parses_listed_jobs_and_preserves_payload() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(
        company_reference="acme", company_name="Acme"
    )
    try:
        [item] = asyncio.run(
            _collect(AshbyCollector(client=client), collection_request)
        )
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == (
        "https://api.ashbyhq.com/posting-api/job-board/acme?includeCompensation=true"
    )
    assert item.url == payload["jobs"][0]["jobUrl"]
    assert item.external_id.startswith("ashby:")
    assert item.title == "Backend Engineer"
    assert item.company_name == "Acme"
    assert item.location_text == "Sao Paulo, Brazil"
    assert item.description == "Build reliable services."
    assert item.published_at is not None
    assert item.raw_payload == payload["jobs"][0]
    assert item.metadata["applyUrl"] == payload["jobs"][0]["applyUrl"]
    assert item.metadata["compensation"] == payload["jobs"][0]["compensation"]
    assert item.metadata["parser_version"] == "ashby-job-board-v2"
    assert len(calls) == 1
    assert collection_request.telemetry.http_requests == 1
    assert collection_request.telemetry.retry_count == 0


def test_retries_rate_limit_using_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"apiVersion": "1", "jobs": []})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference="acme")
    try:
        items = asyncio.run(
            _collect(
                AshbyCollector(client=client, max_retries=1, sleeper=sleeper),
                collection_request,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert calls == 2
    assert delays == [3.0]
    assert collection_request.telemetry.http_requests == 2
    assert collection_request.telemetry.retry_count == 1
    assert collection_request.telemetry.rate_limit_events == 1


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
                    AshbyCollector(client=client, max_retries=0),
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
        (
            httpx.RemoteProtocolError("connection dropped"),
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
        ),
    ],
)
def test_classifies_transport_errors(
    failure: httpx.HTTPError, code: AcquisitionErrorCode
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise failure

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    AshbyCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())

    assert error.value.code is code


def test_rejects_invalid_slug_and_schema() -> None:
    with pytest.raises(AcquisitionError) as invalid_slug:
        asyncio.run(_collect(AshbyCollector(), CollectionRequest(company_reference="acme/jobs")))
    assert invalid_slug.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"jobs": {}}))
    )
    try:
        with pytest.raises(AcquisitionError) as invalid_schema:
            asyncio.run(
                _collect(AshbyCollector(client=client), CollectionRequest(company_reference="acme"))
            )
    finally:
        asyncio.run(client.aclose())
    assert invalid_schema.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_skips_malformed_listed_job_and_reports_it() -> None:
    payload = {
        "apiVersion": "1",
        "jobs": [
            {"title": "Broken", "isListed": True},
            {
                "title": "Valid",
                "isListed": True,
                "jobUrl": "https://jobs.ashbyhq.com/acme/valid",
            },
        ],
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    collection_request = CollectionRequest(company_reference="acme")
    try:
        items = asyncio.run(_collect(AshbyCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert [item.title for item in items] == ["Valid"]
    assert collection_request.telemetry.invalid_items == 1


def test_caps_non_finite_retry_after_with_request_policy() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "inf"})
        return httpx.Response(200, json={"apiVersion": "1", "jobs": []})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme",
        network_policy=CollectionNetworkPolicy(
            max_retries=1,
            retry_delay_seconds=2,
            max_retry_delay_seconds=5,
        ),
    )
    try:
        asyncio.run(_collect(AshbyCollector(client=client, sleeper=sleeper), request))
    finally:
        asyncio.run(client.aclose())

    assert delays == [2]
