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
from opportunity_radar.acquisition.teamtailor import TeamtailorCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "teamtailor_jobs.json"
_DOMAIN = "jobs.acme-careers.test"


async def _collect(collector: TeamtailorCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_parses_listed_jobs_and_preserves_payload() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference=_DOMAIN, company_name="Acme")
    try:
        items = asyncio.run(
            _collect(TeamtailorCollector(client=client), collection_request)
        )
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == f"https://{_DOMAIN}/jobs.json"
    assert len(calls) == 1
    assert [item.external_id for item in items] == [
        payload["items"][0]["id"],
        payload["items"][1]["id"],
    ]
    assert items[0].url == payload["items"][0]["url"]
    assert items[0].title == "Senior Backend Engineer"
    assert items[0].company_name == "Acme"
    assert items[0].location_text == "Sao Paulo, SP, BR"
    assert items[0].description == payload["items"][0]["content_html"]
    assert items[0].published_at is not None
    assert items[0].raw_payload == payload["items"][0]
    assert items[0].metadata["parser_version"] == "teamtailor-jobs-feed-v1"
    assert items[0].metadata["hiring_organization"] == {
        "@type": "Organization",
        "name": "Acme",
    }
    assert items[1].location_text == "Remote"
    assert collection_request.telemetry.http_requests == 1
    assert collection_request.telemetry.items_announced == 2


def test_does_not_attempt_a_second_page() -> None:
    """The Teamtailor feed is unpaginated (docs/pesquisas/termos-teamtailor.md): a single
    successful response is the whole board, even when it is exactly the "page size" of
    another ATS's default limit. The collector must not infer more pages exist."""
    payload = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Acme",
        "home_page_url": f"https://{_DOMAIN}/",
        "feed_url": f"https://{_DOMAIN}/jobs.json",
        "items": [
            {
                "id": f"job-{number}",
                "title": f"Role {number}",
                "url": f"https://{_DOMAIN}/jobs/{number}",
                "date_published": "2026-09-01T12:00:00Z",
                "content_html": "<p>Role</p>",
            }
            for number in range(100)
        ],
    }
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference=_DOMAIN)
    try:
        items = asyncio.run(
            _collect(TeamtailorCollector(client=client), collection_request)
        )
    finally:
        asyncio.run(client.aclose())

    assert len(items) == 100
    assert len(calls) == 1
    assert collection_request.telemetry.items_announced == 100


def test_retries_rate_limit_using_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"items": []})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference=_DOMAIN,
        network_policy=CollectionNetworkPolicy(max_retries=1, max_retry_delay_seconds=3),
    )
    try:
        assert (
            asyncio.run(_collect(TeamtailorCollector(client=client, sleeper=sleeper), request))
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
                    TeamtailorCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference=_DOMAIN),
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
                    TeamtailorCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference=_DOMAIN),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


def test_rejects_invalid_identifier_and_schema() -> None:
    with pytest.raises(AcquisitionError) as invalid_identifier:
        asyncio.run(
            _collect(
                TeamtailorCollector(),
                CollectionRequest(company_reference="https://jobs.acme.test/board"),
            )
        )
    assert invalid_identifier.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    )
    try:
        with pytest.raises(AcquisitionError) as invalid_schema:
            asyncio.run(
                _collect(
                    TeamtailorCollector(client=client),
                    CollectionRequest(company_reference=_DOMAIN),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert invalid_schema.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_skips_malformed_listed_job_and_reports_it() -> None:
    request = CollectionRequest(company_reference=_DOMAIN)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda http_request: httpx.Response(
                200,
                json={
                    "items": [
                        {"id": "broken"},
                        {
                            "id": "valid",
                            "title": "Valid Role",
                            "url": f"https://{_DOMAIN}/jobs/valid",
                            "date_published": "2026-09-01T12:00:00Z",
                        },
                    ]
                },
            )
        )
    )
    try:
        items = asyncio.run(_collect(TeamtailorCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["valid"]
    assert request.telemetry.invalid_items == 1


def test_stops_at_max_items_and_does_not_announce_total() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    collection_request = CollectionRequest(company_reference=_DOMAIN, max_items=1)
    try:
        items = asyncio.run(
            _collect(TeamtailorCollector(client=client), collection_request)
        )
    finally:
        asyncio.run(client.aclose())
    assert len(items) == 1
    assert collection_request.telemetry.items_announced is None


def test_sends_conditional_headers_when_checkpoint_has_validators() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"items": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference=_DOMAIN,
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        asyncio.run(_collect(TeamtailorCollector(client=client), request))
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
        company_reference=_DOMAIN,
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        items = asyncio.run(_collect(TeamtailorCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert request.telemetry.not_modified is True
    assert request.telemetry.response_etag == '"abc123"'
    assert request.telemetry.items_announced is None
