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
from opportunity_radar.acquisition.workday import WorkdayCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "workday_jobs.json"


async def _collect(collector: WorkdayCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_parses_listed_jobs_and_preserves_payload() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        company_name="Acme",
        api_region="wd5",
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == (
        "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/ExternalCareerSite/jobs"
    )
    assert json.loads(calls[0].content) == {
        "limit": 20,
        "offset": 0,
        "searchText": "",
    }
    postings = payload["jobPostings"]
    assert [item.external_id for item in items] == [
        postings[0]["externalPath"],
        postings[1]["externalPath"],
    ]
    assert items[0].url == (
        "https://acme.wd5.myworkdayjobs.com/ExternalCareerSite"
        "/job/Sao-Paulo/Senior-Backend-Engineer_R12345"
    )
    assert items[0].title == "Senior Backend Engineer"
    assert items[0].company_name == "Acme"
    assert items[0].location_text == "Sao Paulo, Brazil"
    assert items[0].description is None
    assert items[0].raw_payload == postings[0]
    assert items[0].metadata["requisition_id"] == "R12345"
    assert items[0].metadata["posted_on"] == "Posted 3 Days Ago"
    assert items[0].metadata["parser_version"] == "workday-cxs-v1"
    assert collection_request.telemetry.http_requests == 1


def test_paginates_until_short_page() -> None:
    calls: list[httpx.Request] = []
    first_page = {
        "total": 21,
        "jobPostings": [
            {
                "title": f"Engineer {number}",
                "externalPath": f"/job/Remote/Engineer-{number}_R{number}",
                "locationsText": "Remote",
                "bulletFields": [f"R{number}"],
            }
            for number in range(20)
        ],
    }
    second_page = {
        "total": 21,
        "jobPostings": [
            {
                "title": "Last Engineer",
                "externalPath": "/job/Remote/Last-Engineer_R999",
                "locationsText": "Remote",
                "bulletFields": ["R999"],
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=first_page if len(calls) == 1 else second_page)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert len(items) == 21
    assert json.loads(calls[0].content)["offset"] == 0
    assert json.loads(calls[1].content)["offset"] == 20
    assert collection_request.telemetry.items_announced == 21


def test_repeated_page_raises_instead_of_claiming_complete_board() -> None:
    page = {
        "total": 40,
        "jobPostings": [
            {
                "title": f"Engineer {number}",
                "externalPath": f"/job/Remote/Engineer-{number}_R{number}",
                "locationsText": "Remote",
            }
            for number in range(20)
        ],
    }
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=page)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    WorkdayCollector(client=client),
                    CollectionRequest(
                        company_reference="acme/ExternalCareerSite", api_region="wd5"
                    ),
                )
            )
    finally:
        asyncio.run(client.aclose())

    assert error.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED
    assert len(calls) == 2


def test_retries_rate_limit_using_retry_after() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"total": 0, "jobPostings": []})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
        network_policy=CollectionNetworkPolicy(max_retries=1, max_retry_delay_seconds=3),
    )
    try:
        assert (
            asyncio.run(_collect(WorkdayCollector(client=client, sleeper=sleeper), request))
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
                    WorkdayCollector(client=client, max_retries=0),
                    CollectionRequest(
                        company_reference="acme/ExternalCareerSite", api_region="wd5"
                    ),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


def test_rejects_invalid_identifier_and_schema() -> None:
    with pytest.raises(AcquisitionError) as missing_site:
        asyncio.run(
            _collect(
                WorkdayCollector(),
                CollectionRequest(company_reference="acme", api_region="wd5"),
            )
        )
    assert missing_site.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    with pytest.raises(AcquisitionError) as missing_pod:
        asyncio.run(
            _collect(
                WorkdayCollector(),
                CollectionRequest(company_reference="acme/ExternalCareerSite"),
            )
        )
    assert missing_pod.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )
    try:
        with pytest.raises(AcquisitionError) as invalid_schema:
            asyncio.run(
                _collect(
                    WorkdayCollector(client=client),
                    CollectionRequest(
                        company_reference="acme/ExternalCareerSite", api_region="wd5"
                    ),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert invalid_schema.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_skips_malformed_listed_job_and_reports_it() -> None:
    request = CollectionRequest(company_reference="acme/ExternalCareerSite", api_region="wd5")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda http_request: httpx.Response(
                200,
                json={
                    "total": 2,
                    "jobPostings": [
                        {"title": "Missing path"},
                        {
                            "title": "Valid Job",
                            "externalPath": "/job/Remote/Valid-Job_R1",
                            "bulletFields": ["R1"],
                        },
                    ],
                },
            )
        )
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["/job/Remote/Valid-Job_R1"]
    assert request.telemetry.invalid_items == 1
