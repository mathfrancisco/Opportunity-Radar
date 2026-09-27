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
from opportunity_radar.acquisition.scheduling import ConditionalRequestHeaders
from opportunity_radar.acquisition.workable import WorkableCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "workable_jobs.json"


async def _collect(collector: WorkableCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_parses_listed_jobs_and_preserves_payload() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference="acme", company_name="Acme")
    try:
        items = asyncio.run(
            _collect(WorkableCollector(client=client), collection_request)
        )
    finally:
        asyncio.run(client.aclose())

    jobs = payload["jobs"]
    assert str(calls[0].url) == (
        "https://apply.workable.com/api/v1/widget/accounts/acme?details=true"
    )
    assert [item.external_id for item in items] == [jobs[0]["id"], jobs[1]["id"]]
    assert items[0].url == jobs[0]["url"]
    assert items[0].title == "Senior Backend Engineer"
    assert items[0].company_name == "Acme"
    assert items[0].location_text == "Sao Paulo, Brazil"
    assert items[0].description == jobs[0]["full_description"]
    assert items[0].raw_payload == jobs[0]
    assert items[0].metadata["workplace_type"] == "hybrid"
    assert items[0].metadata["experience"] == "Mid"
    assert items[0].metadata["parser_version"] == "workable-widget-v1"
    assert collection_request.telemetry.http_requests == 1
    assert collection_request.telemetry.items_announced == 2


def test_single_response_has_no_pagination_and_stops_at_max_items() -> None:
    """The widget has no page parameter (docs/pesquisas/termos-workable.md): one request
    answers with the whole board, so a `max_items` cap truncates that single response
    rather than driving a second call."""
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference="acme", max_items=1)
    try:
        items = asyncio.run(
            _collect(WorkableCollector(client=client), collection_request)
        )
    finally:
        asyncio.run(client.aclose())

    assert len(items) == 1
    assert len(calls) == 1
    # Capped by max_items before the whole response was consumed: the collector never
    # learns whether that was the entire board, so it must not claim an announced total.
    assert collection_request.telemetry.items_announced is None


def test_retries_rate_limit_using_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"jobs": []})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme",
        network_policy=CollectionNetworkPolicy(max_retries=1, max_retry_delay_seconds=3),
    )
    try:
        assert (
            asyncio.run(_collect(WorkableCollector(client=client, sleeper=sleeper), request))
            == []
        )
    finally:
        asyncio.run(client.aclose())
    assert calls == 2
    assert delays == [3]
    assert request.telemetry.retry_count == 1
    assert request.telemetry.rate_limit_events == 1
    assert request.telemetry.items_announced == 0


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
                    WorkableCollector(client=client, max_retries=0),
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
                    WorkableCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


def test_rejects_invalid_identifier_and_schema() -> None:
    with pytest.raises(AcquisitionError) as invalid_slug:
        asyncio.run(
            _collect(
                WorkableCollector(), CollectionRequest(company_reference="acme/jobs")
            )
        )
    assert invalid_slug.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    try:
        with pytest.raises(AcquisitionError) as invalid_schema:
            asyncio.run(
                _collect(
                    WorkableCollector(client=client),
                    CollectionRequest(company_reference="acme"),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert invalid_schema.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_skips_malformed_listed_job_and_reports_it() -> None:
    request = CollectionRequest(company_reference="acme")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda http_request: httpx.Response(
                200,
                json={
                    "jobs": [
                        {"id": "broken"},
                        {
                            "id": "valid",
                            "title": "Valid Job",
                            "url": "https://apply.workable.com/acme/j/VALID/",
                        },
                    ]
                },
            )
        )
    )
    try:
        items = asyncio.run(_collect(WorkableCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["valid"]
    assert request.telemetry.invalid_items == 1


def test_sends_conditional_headers_when_checkpoint_has_validators() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"jobs": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme",
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        asyncio.run(_collect(WorkableCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert calls[0].headers["If-None-Match"] == '"abc123"'


def test_bare_304_yields_no_items_and_records_not_modified_without_a_total() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(304, headers={"ETag": '"abc123"'})
        )
    )
    request = CollectionRequest(
        company_reference="acme",
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        items = asyncio.run(_collect(WorkableCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert request.telemetry.not_modified is True
    assert request.telemetry.response_etag == '"abc123"'
    assert request.telemetry.items_announced is None
