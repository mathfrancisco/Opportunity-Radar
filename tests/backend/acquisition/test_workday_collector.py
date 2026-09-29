import asyncio
import json
from datetime import UTC, datetime, timedelta
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
    # Card F20-61: "Posted N Days Ago" is real source data (a relative age), parsed
    # as a lower-bound `published_at` — never a fabricated exact date.
    now = datetime.now(UTC)
    assert items[0].published_at is not None
    assert abs((now - timedelta(days=3)) - items[0].published_at) < timedelta(minutes=1)
    assert items[1].published_at is not None
    assert abs(now - items[1].published_at) < timedelta(minutes=1)  # "Posted Today"
    assert collection_request.telemetry.http_requests == 1
    # Each item carries the offset a resume should pick up from if this run is
    # interrupted right after it (F20-39 "retomada da mesma execução").
    assert items[0].cursor == "1"
    assert items[1].cursor == "2"


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


def test_stops_at_the_announced_total_when_workday_wraps_past_the_cap() -> None:
    # Regression (Accenture, wd103): Workday states `total` (capped at 2000) only on the
    # offset-0 page, has a real short tail page of 10, and past the cap it wraps back to
    # the first page instead of ending. That is the end of the board, not a schema change.
    def posting(number: int) -> dict[str, object]:
        return {
            "title": f"Engineer {number}",
            "externalPath": f"/job/Remote/Engineer-{number}_R{number}",
            "locationsText": "Remote",
        }

    total = 60
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        calls.append(offset)
        start = offset % total  # wrap past the cap, like the real endpoint
        page = [posting(start + i) for i in range(min(20, total - start))]
        return httpx.Response(
            200, json={"total": total if offset == 0 else 0, "jobPostings": page}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(
        company_reference="acme/ExternalCareerSite", api_region="wd5"
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert len(items) == total
    assert len({item.external_id for item in items}) == total
    assert calls == [0, 20, 40]  # never asks for offset == total
    assert collection_request.telemetry.items_announced == total


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


def test_sends_conditional_headers_only_for_a_fresh_full_run() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"total": 0, "jobPostings": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        asyncio.run(_collect(WorkdayCollector(client=client), request))
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
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert request.telemetry.not_modified is True
    assert request.telemetry.response_etag == '"abc123"'
    assert request.telemetry.items_announced is None


def test_resumes_from_an_explicit_cursor_offset_without_conditional_headers() -> None:
    calls: list[httpx.Request] = []
    page = {
        "total": 1,
        "jobPostings": [
            {
                "title": "Resumed Engineer",
                "externalPath": "/job/Remote/Resumed-Engineer_R42",
                "locationsText": "Remote",
                "bulletFields": ["R42"],
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=page)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # A resumed run supplies both an explicit cursor and the run it continues
    # (`resume_of_run_id`); here we only exercise the collector's own read of `cursor`.
    request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
        cursor="20",
        conditional_headers=ConditionalRequestHeaders(if_none_match='"stale-etag"'),
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert json.loads(calls[0].content)["offset"] == 20
    assert items[0].cursor == "21"
    # A resumed run's request is a different scope (mid-board) than whatever the
    # checkpoint's validators described (a fresh, full read), so it must never send
    # them (SPEC 39 §7 — validators never cross scopes).
    assert "If-None-Match" not in calls[0].headers


def test_rejects_a_malformed_cursor() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"jobPostings": []}))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    WorkdayCollector(client=client),
                    CollectionRequest(
                        company_reference="acme/ExternalCareerSite",
                        api_region="wd5",
                        cursor="not-a-number",
                    ),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION


@pytest.mark.parametrize(
    ("posted_on", "expected_days_ago"),
    [
        ("Posted Today", 0),
        ("Posted Yesterday", 1),
        ("Posted 3 Days Ago", 3),
        ("Posted 1 Day Ago", 1),
        ("Posted 30+ Days Ago", 30),
    ],
)
def test_parse_posted_on_reads_the_relative_age(
    posted_on: str, expected_days_ago: int
) -> None:
    now = datetime.now(UTC)
    parsed = WorkdayCollector._parse_posted_on(posted_on)
    assert parsed is not None
    assert abs((now - timedelta(days=expected_days_ago)) - parsed) < timedelta(minutes=1)


@pytest.mark.parametrize("posted_on", [None, "", "Applications closing soon", 42])
def test_parse_posted_on_returns_none_for_unknown_shapes(posted_on: object) -> None:
    assert WorkdayCollector._parse_posted_on(posted_on) is None
