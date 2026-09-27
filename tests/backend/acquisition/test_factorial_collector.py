import asyncio
from pathlib import Path

import httpx
import pytest

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionNetworkPolicy,
    CollectionRequest,
)
from opportunity_radar.acquisition.factorial import FactorialCollector

_FIXTURE = Path(__file__).parents[2] / "fixtures" / "factorial_careers_page.html"
_SLUG = "acme"

_SCHEMA_CHANGED_PAGE = "<html><body><p>Nothing here.</p></body></html>"

_MINIMAL_PAGE = """<html><body>
<div data-controller='job-filters'>
<ul>{jobs}</ul>
</div>
</body></html>"""


async def _collect(collector: FactorialCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def test_parses_listed_jobs_and_preserves_payload() -> None:
    page = _FIXTURE.read_text(encoding="utf-8")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=page, headers={"Content-Type": "text/html"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference=_SLUG, company_name="Acme")
    try:
        items = asyncio.run(_collect(FactorialCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert str(calls[0].url) == f"https://{_SLUG}.factorialhr.com/"
    assert len(calls) == 1
    assert [item.external_id for item in items] == [
        "software-engineer-go-open-talent-pool-263236",
        "hr-analyst-69351",
        "partner-service-manager-323792",
    ]
    assert items[0].url == (
        "https://acme.factorialhr.com/job_posting/software-engineer-go-open-talent-pool-263236"
    )
    assert items[0].title == "Software Engineer (Go)"
    assert items[0].company_name == "Acme"
    assert items[0].location_text == "Remote"
    assert items[0].metadata["team_name"] == "Tech Team"
    assert items[0].metadata["team_id"] == "94774"
    assert items[0].metadata["is_remote"] is True
    assert items[0].metadata["contract_type"] == "indefinite"
    assert items[0].metadata["parser_version"] == "factorial-careers-page-v1"
    assert items[1].location_text == "Barcelona, Spain"
    assert items[1].metadata["is_remote"] is False
    # A job with no team assigned (data-team-id="") still renders its team `<div>` label,
    # just with no text inside — confirmed live against careers.factorialhr.com, where 9 of
    # 140 real postings have this exact shape. The empty label must still occupy its
    # positional slot (title, team, location) rather than being dropped, or the location
    # text shifts into the team slot and the job is wrongly rejected as schema-changed.
    assert items[2].title == "Partner Service Manager"
    assert items[2].location_text == "Hybrid"
    assert items[2].metadata["team_name"] is None
    assert items[2].metadata["team_id"] == ""
    assert collection_request.telemetry.http_requests == 1
    assert collection_request.telemetry.items_announced == 3
    assert collection_request.telemetry.invalid_items == 0


def test_does_not_attempt_a_second_page() -> None:
    """The Factorial careers page is unpaginated (docs/pesquisas/termos-factorial.md): every
    job is embedded in the single HTML response, confirmed against a 70+-job board. The
    collector must not infer more pages exist."""
    jobs = "".join(
        f"""<li class='job-offer-item' data-is-remote='true' data-contract-type='indefinite'
        data-job-postings-url='https://{_SLUG}.factorialhr.com/job_posting/role-{number}'
        data-team-id='1' data-location-id='1'>
        <div><span><div class="factorial__headingFontFamily">Role {number}</div></span>
        <div><div class="text-gray-350">Engineering</div></div>
        <div><div class="text-gray-350">Remote</div></div></div></li>"""
        for number in range(100)
    )
    page = _MINIMAL_PAGE.format(jobs=jobs)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=page, headers={"Content-Type": "text/html"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    collection_request = CollectionRequest(company_reference=_SLUG)
    try:
        items = asyncio.run(_collect(FactorialCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())

    assert len(items) == 100
    assert len(calls) == 1
    assert collection_request.telemetry.items_announced == 100


def test_retries_rate_limit_using_retry_after() -> None:
    calls = 0
    delays: list[float] = []
    empty_page = _MINIMAL_PAGE.format(jobs="")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, text=empty_page, headers={"Content-Type": "text/html"})

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference=_SLUG,
        network_policy=CollectionNetworkPolicy(max_retries=1, max_retry_delay_seconds=3),
    )
    try:
        assert (
            asyncio.run(_collect(FactorialCollector(client=client, sleeper=sleeper), request)) == []
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
                    FactorialCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference=_SLUG),
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
def test_classifies_transport_errors(failure: httpx.HTTPError, code: AcquisitionErrorCode) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(failure))
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    FactorialCollector(client=client, max_retries=0),
                    CollectionRequest(company_reference=_SLUG),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is code


def test_rejects_invalid_identifier_and_schema() -> None:
    with pytest.raises(AcquisitionError) as invalid_identifier:
        asyncio.run(
            _collect(
                FactorialCollector(),
                CollectionRequest(company_reference="https://acme.factorialhr.com/"),
            )
        )
    assert invalid_identifier.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    # A 200 response that is not a jobs-listing page (missing the job-filters marker) must
    # never be read as a board with zero postings.
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=_SCHEMA_CHANGED_PAGE, headers={"Content-Type": "text/html"}
            )
        )
    )
    try:
        with pytest.raises(AcquisitionError) as invalid_schema:
            asyncio.run(
                _collect(
                    FactorialCollector(client=client),
                    CollectionRequest(company_reference=_SLUG),
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert invalid_schema.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_accepts_double_quoted_marker_and_void_elements_inside_a_job() -> None:
    page = _MINIMAL_PAGE.replace(
        "data-controller='job-filters'", 'data-controller="job-filters"'
    ).format(
        jobs=(
            "<li class='job-offer-item' data-is-remote='true' "
            "data-job-postings-url='https://acme.factorialhr.com/job_posting/role' "
            "data-team-id='1' data-location-id='1'>"
            "<div class='factorial__headingFontFamily'>Role<br/>title<img src='x'/></div>"
            "<div class='text-gray-350'>Engineering</div>"
            "<div class='text-gray-350'>Remote</div></li>"
        )
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=page, headers={"Content-Type": "text/html"})
        )
    )
    try:
        items = asyncio.run(
            _collect(FactorialCollector(client=client), CollectionRequest(company_reference=_SLUG))
        )
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["role"]
    assert items[0].title == "Role title"


def test_rejects_truncated_job_listing() -> None:
    page = _MINIMAL_PAGE.format(
        jobs="""<li class='job-offer-item' data-job-postings-url='https://acme.factorialhr.com/job_posting/role'>Role"""
    )
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=page, headers={"Content-Type": "text/html"})
        )
    )
    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                _collect(
                    FactorialCollector(client=client), CollectionRequest(company_reference=_SLUG)
                )
            )
    finally:
        asyncio.run(client.aclose())
    assert error.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_skips_malformed_listed_job_and_reports_it() -> None:
    page = _MINIMAL_PAGE.format(
        jobs="""<li class='job-offer-item' data-contract-type='indefinite'>
        <div><span><div class="factorial__headingFontFamily">Missing url</div></span></div>
        </li>
        <li class='job-offer-item' data-is-remote='true' data-contract-type='indefinite'
        data-job-postings-url='https://acme.factorialhr.com/job_posting/valid-role'
        data-team-id='1' data-location-id='1'>
        <div><span><div class="factorial__headingFontFamily">Valid Role</div></span>
        <div><div class="text-gray-350">Engineering</div></div>
        <div><div class="text-gray-350">Remote</div></div></div></li>"""
    )
    request = CollectionRequest(company_reference=_SLUG)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda http_request: httpx.Response(
                200, text=page, headers={"Content-Type": "text/html"}
            )
        )
    )
    try:
        items = asyncio.run(_collect(FactorialCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert [item.external_id for item in items] == ["valid-role"]
    assert request.telemetry.invalid_items == 1


def test_stops_at_max_items_and_does_not_announce_total() -> None:
    page = _FIXTURE.read_text(encoding="utf-8")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=page, headers={"Content-Type": "text/html"})
        )
    )
    collection_request = CollectionRequest(company_reference=_SLUG, max_items=1)
    try:
        items = asyncio.run(_collect(FactorialCollector(client=client), collection_request))
    finally:
        asyncio.run(client.aclose())
    assert len(items) == 1
    assert collection_request.telemetry.items_announced is None
