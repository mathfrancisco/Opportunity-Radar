import asyncio
import json
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.alerts import SourceAlertService
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionMode,
    CollectionNetworkPolicy,
    CollectionRequest,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.scheduling import ConditionalRequestHeaders, SourceRunHistory
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyExtractionSettings
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


def test_rate_limit_persists_retry_after_without_retry_loop() -> None:
    calls = 0
    cooldowns: list[datetime] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "4"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
        network_policy=CollectionNetworkPolicy(max_retries=1, max_retry_delay_seconds=3),
        persist_cooldown=cooldowns.append,
    )
    try:
        with pytest.raises(AcquisitionError) as caught:
            asyncio.run(_collect(WorkdayCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())
    assert caught.value.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED
    assert calls == 1
    assert len(cooldowns) == 1
    assert 3.0 <= (cooldowns[0] - datetime.now(UTC)).total_seconds() <= 4.0
    assert request.telemetry.retry_count == 0
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


def test_untitled_posting_is_skipped_not_invalid() -> None:
    """F20-75: a posting Workday returns without a title is not an opportunity; it is
    skipped, not a malformed item that degrades the run."""
    request = CollectionRequest(company_reference="acme/ExternalCareerSite", api_region="wd5")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda http_request: httpx.Response(
                200,
                json={
                    "total": 3,
                    "jobPostings": [
                        {"externalPath": "/job/Remote/Untitled_R0"},
                        {"title": "  ", "externalPath": "/job/Remote/Blank_R2"},
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
    assert request.telemetry.skipped_items == 2
    assert request.telemetry.invalid_items == 0


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


# --- F48-08: a big Workday board never touches Tavily nor a shared budget bucket --------


class _RunMemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, model: object) -> None:
        self.added.append(model)

    def flush(self) -> None:
        return None

    def begin_nested(self):
        return nullcontext()

    def rollback(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def refresh(self, model: object, attribute_names: object = None) -> None:
        del model, attribute_names

    def scalar(self, statement: object) -> None:
        del statement
        return None

    def get(self, model: type, primary_key: object) -> None:
        del model, primary_key
        return None


class _RunMemoryRepository:
    def __init__(self, source: SourceDefinitionModel) -> None:
        self.source = source
        self.budget_calls: list[dict[str, object]] = []

    def run_history(self, source_id: object, *, sample: int = 32) -> SourceRunHistory:
        del source_id, sample
        return SourceRunHistory()

    def get_source(self, source_id: object) -> SourceDefinitionModel | None:
        return self.source if source_id == self.source.id else None

    def identical_raw_item_exists(self, **_: object) -> bool:
        return False

    def raw_item_by_envelope(self, **_: object) -> bool:
        return False

    def get_host_budget(self, host: str) -> None:
        del host
        return None

    def record_host_budget_usage(
        self,
        host: str,
        *,
        now: object,
        requests: int,
        default_ceiling: int,
        cooldown_until: object = None,
    ) -> None:
        del now, cooldown_until
        self.budget_calls.append(
            {"host": host, "requests": requests, "default_ceiling": default_ceiling}
        )


def _large_workday_run(items: int):
    tavily_calls: list[httpx.Request] = []

    def workday_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        offset, limit = body["offset"], body["limit"]
        postings = [
            {
                "title": f"Engineer {number}",
                "externalPath": f"/job/Remote/Engineer-{number}_R{number}",
                "locationsText": "Remote",
                "bulletFields": [f"R{number}"],
            }
            for number in range(offset, min(offset + limit, items))
        ]
        return httpx.Response(200, json={"total": items, "jobPostings": postings})

    def tavily_handler(request: httpx.Request) -> httpx.Response:
        tavily_calls.append(request)
        return httpx.Response(200, json={"results": [], "usage": {"credits": 1}})

    workday_client = httpx.AsyncClient(transport=httpx.MockTransport(workday_handler))
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="workday",
        name="Adobe",
        enabled=True,
        configuration={"tenant_identifier": "adobe/external", "api_region": "wd5"},
    )
    session = _RunMemorySession()
    repository = _RunMemoryRepository(source)
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((WorkdayCollector(client=workday_client),)),
        repository=repository,  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
        tavily_extraction=TavilyExtractionSettings(
            client_factory=lambda: TavilyClient(
                api_key="test-key",
                client=httpx.AsyncClient(transport=httpx.MockTransport(tavily_handler)),
            ),
            cache_ttl_seconds=3600,
            credit_budget_per_run=100,
        ),
    )
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(workday_client.aclose())
    return run, tavily_calls, repository


def test_500_item_workday_run_makes_zero_tavily_calls_and_finishes_pagination() -> None:
    run, tavily_calls, repository = _large_workday_run(500)

    assert tavily_calls == []
    assert run.items_seen == 500
    assert run.status == "SUCCEEDED"
    assert run.error_code != AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED.value
    assert run.credits_used == 0
    # Only the 25 listing pages count against the tenant's own bucket.
    assert repository.budget_calls == [
        {"host": "adobe.wd5.myworkdayjobs.com", "requests": 25, "default_ceiling": 500}
    ]


# --- F50-03: detail fetch, only for target areas, behind a per-source flag ---------------

# SYNTHETIC: the detail fixture follows the publicly documented CXS shape
# (`jobPostingInfo.jobDescription`, docs/pesquisas/termos-workday.md). No real endpoint was
# called to capture it.
_DETAIL_FIXTURE = Path(__file__).parents[2] / "fixtures" / "workday_job_detail.json"
_TARGETS = ("SOFTWARE_ENGINEERING", "DATA")
_ENG = "Senior Backend Engineer"


def _detail_postings(titles: list[str]) -> list[dict[str, object]]:
    return [
        {
            "title": title,
            "externalPath": f"/job/Remote/Job-{number}_R{number}",
            "locationsText": "Remote",
            "bulletFields": [f"R{number}"],
        }
        for number, title in enumerate(titles)
    ]


def _detail_run(
    titles: list[str],
    *,
    detail_status: dict[str, int] | None = None,
    sleeper=None,
    **request_fields: object,
):
    """Collect `titles` through a mock transport; returns items, request log, request."""
    postings = _detail_postings(titles)
    detail_payload = json.loads(_DETAIL_FIXTURE.read_text(encoding="utf-8"))
    log: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"total": len(postings), "jobPostings": postings})
        path = request.url.path.rsplit("/cxs/acme/ExternalCareerSite", 1)[1]
        status = (detail_status or {}).get(path, 200)
        if status != 200:
            return httpx.Response(status, headers={"Retry-After": "1"} if status == 429 else {})
        return httpx.Response(200, json=detail_payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # Test fixture approval is synthetic and is never loaded by production config.
    request_fields.setdefault("detail_approval_valid", True)
    request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        company_name="Acme",
        api_region="wd5",
        **request_fields,  # type: ignore[arg-type]
    )
    collector = (
        WorkdayCollector(client=client, sleeper=sleeper)
        if sleeper is not None
        else WorkdayCollector(client=client)
    )
    try:
        items = asyncio.run(_collect(collector, request))
    finally:
        asyncio.run(client.aclose())
    return items, log, request


def _details(log: list[httpx.Request]) -> list[httpx.Request]:
    return [call for call in log if call.method == "GET"]


def test_target_posting_gets_its_description_and_keeps_its_identity() -> None:
    plain, _, _ = _detail_run([_ENG])
    items, log, request = _detail_run([_ENG], fetch_detail=True, target_role_families=_TARGETS)

    assert items[0].description == "<p>Build and run the services behind our platform.</p>"
    assert items[0].external_id == plain[0].external_id
    assert items[0].url == plain[0].url
    assert items[0].title == plain[0].title
    assert str(_details(log)[0].url) == (
        "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/ExternalCareerSite"
        "/job/Remote/Job-0_R0"
    )
    assert request.telemetry.http_requests == 2
    assert request.telemetry.detail_requests == 1


def test_off_target_and_unknown_postings_get_no_detail_request() -> None:
    items, log, _ = _detail_run(
        ["Account Executive", "Wizard of Light", _ENG],
        fetch_detail=True,
        detail_approval_valid=True,
        target_role_families=_TARGETS,
    )

    assert [item.description is not None for item in items] == [False, False, True]
    assert [call.url.path.rsplit("/", 1)[1] for call in _details(log)] == ["Job-2_R2"]


@pytest.mark.parametrize("fields", [{}, {"fetch_detail": False}])
def test_flag_absent_or_false_fetches_no_detail_and_matches_listing_only(
    fields: dict[str, object],
) -> None:
    items, log, request = _detail_run(
        [_ENG, "Data Engineer"], target_role_families=_TARGETS, **fields
    )

    assert _details(log) == []
    assert request.telemetry.http_requests == 1
    assert all(item.description is None for item in items)
    assert [item.external_id for item in items] == [
        "/job/Remote/Job-0_R0",
        "/job/Remote/Job-1_R1",
    ]


def test_flag_on_without_target_role_families_fetches_no_detail() -> None:
    items, log, _ = _detail_run([_ENG], fetch_detail=True)

    assert _details(log) == []
    assert items[0].description is None


def test_per_run_cap_limits_detail_requests_and_is_recorded() -> None:
    items, log, request = _detail_run(
        [_ENG] * 5,
        fetch_detail=True,
        detail_max_requests=2,
        target_role_families=_TARGETS,
    )

    assert len(_details(log)) == 2
    assert len(items) == 5
    assert [item.description is not None for item in items] == [True, True, False, False, False]
    assert request.telemetry.detail_requests == 2
    assert request.telemetry.detail_skipped == 3


def test_per_run_cap_counts_retry_transports_and_preserves_listing_item() -> None:
    items, log, request = _detail_run(
        [_ENG],
        detail_status={"/job/Remote/Job-0_R0": 500},
        fetch_detail=True,
        detail_max_requests=1,
        target_role_families=_TARGETS,
    )

    assert len(items) == 1
    assert items[0].description is None
    assert len(_details(log)) == 1
    assert request.telemetry.detail_requests == 1
    assert request.telemetry.detail_failures == 1
    assert request.telemetry.detail_skip_reasons == {"cap": 1}


def test_host_budget_left_limits_detail_requests() -> None:
    # One listing page already spent 1 of the 3 requests the host still allows.
    items, log, request = _detail_run(
        [_ENG] * 5,
        fetch_detail=True,
        host_requests_remaining=3,
        target_role_families=_TARGETS,
    )

    assert len(_details(log)) == 2
    assert len(items) == 5
    assert request.telemetry.detail_skipped == 3


def test_detail_failure_keeps_the_posting_and_does_not_fail_the_run() -> None:
    items, log, request = _detail_run(
        [_ENG] * 3,
        detail_status={"/job/Remote/Job-1_R1": 404},
        fetch_detail=True,
        detail_approval_valid=True,
        target_role_families=_TARGETS,
    )

    assert [item.description is not None for item in items] == [True, False, True]
    assert len(_details(log)) == 3
    assert request.telemetry.detail_failures == 1


def test_detail_schema_mismatch_keeps_the_posting() -> None:
    postings = _detail_postings([_ENG])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"total": 1, "jobPostings": postings})
        return httpx.Response(200, json={"unexpected": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        company_reference="acme/ExternalCareerSite",
        api_region="wd5",
        fetch_detail=True,
        detail_approval_valid=True,
        target_role_families=_TARGETS,
    )
    try:
        items = asyncio.run(_collect(WorkdayCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert len(items) == 1
    assert items[0].description is None
    assert request.telemetry.detail_failures == 1


def test_detail_rate_limit_stops_further_detail_requests() -> None:
    async def sleeper(delay: float) -> None:
        del delay

    items, log, request = _detail_run(
        [_ENG] * 4,
        detail_status={"/job/Remote/Job-1_R1": 429},
        sleeper=sleeper,
        fetch_detail=True,
        network_policy=CollectionNetworkPolicy(max_retries=0),
        target_role_families=_TARGETS,
    )

    assert len(items) == 4
    assert [item.description is not None for item in items] == [True, False, False, False]
    assert len(_details(log)) == 2  # the 429 stops the run's detail requests
    assert request.telemetry.rate_limit_events == 1
    assert request.telemetry.detail_skipped == 2


def test_budget_reservation_runs_before_every_http_and_denial_sends_no_request() -> None:
    decisions = iter((None, "quota"))
    items, log, request = _detail_run(
        [_ENG],
        fetch_detail=True,
        detail_approval_valid=True,
        target_role_families=_TARGETS,
        reserve_http_request=lambda is_detail: next(decisions),
    )

    assert len(items) == 1
    assert [call.method for call in log] == ["POST"]
    assert request.telemetry.http_requests == 1
    assert request.telemetry.detail_requests == 0
    assert request.telemetry.detail_skipped == 1
    assert request.telemetry.detail_skip_reasons == {"quota": 1}


def test_detail_without_approval_never_opens_detail_transport() -> None:
    _, log, request = _detail_run(
        [_ENG],
        fetch_detail=True,
        detail_approval_valid=False,
        target_role_families=_TARGETS,
    )

    assert _details(log) == []
    assert request.telemetry.detail_skipped == 1
    assert request.telemetry.detail_skip_reasons == {"approval_missing": 1}


def test_detail_requests_honour_the_minimum_interval() -> None:
    delays: list[float] = []

    async def sleeper(delay: float) -> None:
        delays.append(delay)

    _, log, request = _detail_run(
        [_ENG, "Data Engineer"],
        sleeper=sleeper,
        fetch_detail=True,
        network_policy=CollectionNetworkPolicy(minimum_interval_seconds=30),
        target_role_families=_TARGETS,
    )

    assert len(_details(log)) == 2
    # The listing set `last_http_attempt_at`, so each detail waited out the interval.
    assert len(delays) == 2
    assert all(0 < delay <= 30 for delay in delays)
    assert request.telemetry.http_requests == 3
