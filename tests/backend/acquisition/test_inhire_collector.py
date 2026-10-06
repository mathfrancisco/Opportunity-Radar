"""inHire collector: list and detail parsing, stop conditions, data minimisation, and the
"detail only for new or changed jobs" contract. Every request goes through a mock transport."""

import asyncio
import json
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

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
    content_hashes,
)
from opportunity_radar.acquisition.http_client import COLLECTOR_USER_AGENT
from opportunity_radar.acquisition.inhire import InhireCollector
from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel
from opportunity_radar.acquisition.scheduling import SourceRunHistory
from opportunity_radar.acquisition.service import (
    AcquisitionService,
    _source_network_policy,
    canonical_payload_hash,
    collected_item_v1,
)
from opportunity_radar.opportunities.domain import (
    ContractType,
    NormalizationInput,
    WorkMode,
    normalize_candidate,
)

_FIXTURES = Path(__file__).parents[2] / "fixtures"
_LIST = json.loads((_FIXTURES / "inhire_jobs.json").read_text(encoding="utf-8"))
_DETAIL = json.loads((_FIXTURES / "inhire_job_detail.json").read_text(encoding="utf-8"))
_IDS = [job["jobId"] for job in _LIST["jobsPage"]]
_CONTRACTS = {_IDS[0]: ["CLT"], _IDS[1]: ["PJ"], _IDS[2]: ["Estágio"]}
_PAGES = "/job-posts/public/pages"
_REFRESH_DAYS = 7
_WEEK = [date(2026, 10, 5) + timedelta(days=offset) for offset in range(_REFRESH_DAYS)]


def _refresh_day(job_id: str) -> date:
    """A day on which the weekly re-read of this job's detail is due."""
    slot = UUID(job_id).int % _REFRESH_DAYS
    return next(day for day in _WEEK if day.toordinal() % _REFRESH_DAYS == slot)


#: A day on which none of the fixture jobs is due.
_QUIET_DAY = next(day for day in _WEEK if all(day != _refresh_day(job) for job in _IDS))
_STORED_FIELDS = {
    "jobId",
    "displayName",
    "status",
    "workplaceType",
    "location",
    "description",
    "contractType",
    "publishedAt",
    "lastPublishedAt",
}
#: Detail fields the review says must never be stored, and a sentinel string for each.
_FORBIDDEN_KEYS = {
    "settings",
    "activeJobBoards",
    "jobBoardsData",
    "privacyPolicyUrl",
    "about",
    "background",
    "logo",
    "bannerTitle",
    "bannerTitleColor",
    "locationComplement",
    "salaryCurrency",
    "createdAt",
    "updatedAt",
}


class _Board:
    """A fake inHire tenant: serves the list and one detail per job, and logs every request."""

    def __init__(self, listing: dict[str, Any] | None = None) -> None:
        self.listing = deepcopy(listing if listing is not None else _LIST)
        self.log: list[httpx.Request] = []
        self.list_status = 200
        self.detail_status: dict[str, int] = {}
        self.detail_description = _DETAIL["description"]

    def detail(self, job_id: str) -> dict[str, Any]:
        job = next(job for job in self.listing["jobsPage"] if job["jobId"] == job_id)
        return {
            **deepcopy(_DETAIL),
            "jobId": job_id,
            "displayName": job["displayName"],
            "workplaceType": job["workplaceType"],
            "location": job["location"],
            "contractType": _CONTRACTS.get(job_id, ["CLT"]),
            "description": self.detail_description,
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.log.append(request)
        if request.url.path == _PAGES:
            if self.list_status == 404:
                return httpx.Response(404, json={"message": "Tenant not found"})
            if self.list_status != 200:
                retry = {"Retry-After": "7"} if self.list_status == 429 else {}
                return httpx.Response(self.list_status, headers=retry)
            return httpx.Response(200, json=self.listing)
        job_id = request.url.path.removeprefix(f"{_PAGES}/")
        status = self.detail_status.get(job_id, 200)
        if status != 200:
            return httpx.Response(status, headers={"Retry-After": "7"} if status == 429 else {})
        return httpx.Response(200, json=self.detail(job_id))

    @property
    def details(self) -> list[str]:
        return [
            call.url.path.removeprefix(f"{_PAGES}/")
            for call in self.log
            if call.url.path != _PAGES
        ]


def _run(
    board: _Board,
    *,
    tenant: str = "acme",
    sleeps: list[float] | None = None,
    today: date | None = None,
    **request_fields: Any,
):
    """Collect one run; returns the items emitted before an error, the error and the request.

    Without `today` the run happens on a day when no fixture job is due for its re-read."""
    sleeps = [] if sleeps is None else sleeps
    today = today or _QUIET_DAY

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async def collect() -> tuple[list, AcquisitionError | None]:
        client = httpx.AsyncClient(transport=httpx.MockTransport(board.handler))
        request = CollectionRequest(company_reference=tenant, **request_fields)
        items: list = []
        error: AcquisitionError | None = None
        try:
            collector = InhireCollector(client=client, sleeper=sleeper, today=lambda: today)
            async for item in collector.discover(request):
                items.append(item)
        except AcquisitionError as raised:
            error = raised
        finally:
            await client.aclose()
        return items, error, request

    return asyncio.run(collect())


# --- list parsing and detail ----------------------------------------------------------


def test_listing_only_parses_the_reduced_real_fixture() -> None:
    board = _Board()
    items, error, request = _run(board)

    assert error is None
    assert [item.external_id for item in items] == _IDS
    first = items[0]
    assert first.source_type == "inhire"
    assert first.url == f"https://acme.inhire.app/vagas/{_IDS[0]}/vaga"
    assert first.title == "\U0001f680 | Backend Developer (Python) | Senior"
    assert first.company_name == "Acme Tecnologia"  # tenantName; no company_name configured
    assert first.location_text == "BR"
    assert items[1].location_text == "Porto Alegre, RS, BR"
    assert first.description is None and first.published_at is None
    assert first.metadata["workplace_type"] == "Remote"
    assert first.metadata["parser_version"] == "inhire-public-pages-v1"
    assert set(first.raw_payload) == {"jobId", "displayName", "status", "workplaceType", "location"}
    assert [call.url.path for call in board.log] == [_PAGES]
    assert request.telemetry.items_announced == 3
    assert request.telemetry.http_requests == 1


def test_configured_company_name_wins_over_tenant_name() -> None:
    items, _, _ = _run(_Board(), company_name="Acme S.A.")

    assert {item.company_name for item in items} == {"Acme S.A."}


def test_detail_supplies_description_contract_and_publication_date() -> None:
    board = _Board()
    items, error, request = _run(board, fetch_detail=True)

    assert error is None
    first = items[0]
    assert first.description == _DETAIL["description"]
    assert first.published_at == datetime(2026, 9, 17, 21, 16, 57, 662000, tzinfo=UTC)
    assert first.metadata["contract_type"] == ["full-time"]
    assert items[1].metadata["contract_type"] == ["contract"]
    assert items[2].metadata["contract_type"] == ["Estágio"]
    # Serial: one list, then one detail per job in list order.
    assert board.details == _IDS
    assert request.telemetry.http_requests == 4
    assert request.telemetry.detail_requests == 3


def test_requests_are_serial_and_paced_at_one_per_second_by_default() -> None:
    sleeps: list[float] = []
    _run(_Board(), fetch_detail=True, sleeps=sleeps)

    assert len(sleeps) == 3 and all(0.9 < seconds <= 1.0 for seconds in sleeps)


def test_the_source_policy_paces_requests_when_given() -> None:
    sleeps: list[float] = []
    _run(
        _Board(),
        fetch_detail=True,
        sleeps=sleeps,
        network_policy=CollectionNetworkPolicy(minimum_interval_seconds=2.0),
    )

    assert len(sleeps) == 3 and all(1.9 < seconds <= 2.0 for seconds in sleeps)


def test_type_default_policy_is_one_request_per_second_unless_the_source_sets_pacing() -> None:
    assert _source_network_policy("inhire", {}).minimum_interval_seconds == 1.0
    assert _source_network_policy("inhire", {"max_retries": 1}).minimum_interval_seconds == 1.0
    assert (
        _source_network_policy("inhire", {"minimum_interval_seconds": 5}).minimum_interval_seconds
        == 5.0
    )
    assert (
        _source_network_policy("inhire", {"requests_per_second": 0.5}).minimum_interval_seconds
        == 2.0
    )
    assert _source_network_policy("workday", {}).minimum_interval_seconds == 0.0


# --- the request itself ---------------------------------------------------------------


def test_request_carries_the_tenant_header_and_the_product_user_agent(monkeypatch) -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, json={"tenantName": "Acme", "jobsPage": []})

    import opportunity_radar.acquisition.http_client as http_client

    real = http_client.httpx.AsyncClient
    monkeypatch.setattr(
        http_client.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(handler), **kwargs),
    )

    async def run() -> None:
        request = CollectionRequest(company_reference="gx2")
        _ = [item async for item in InhireCollector().discover(request)]

    asyncio.run(run())

    assert seen[0]["X-Tenant"] == "gx2"
    assert seen[0]["User-Agent"] == COLLECTOR_USER_AGENT
    # No credentials, cookies or browser headers.
    assert {name.casefold() for name in seen[0]} <= {
        "host",
        "accept",
        "accept-encoding",
        "connection",
        "user-agent",
        "x-tenant",
    }


@pytest.mark.parametrize(
    "tenant",
    ["gx2", "contaazul", "atlastechnol", "magalu", "a", "a-b", "0abc", "a" * 63, "a--b"],
)
def test_valid_tenants_are_accepted(tenant: str) -> None:
    assert InhireCollector.validate_tenant_identifier(tenant) == tenant


@pytest.mark.parametrize(
    "tenant",
    [
        None,
        "",
        " ",
        "GX2",
        "gx2.inhire.app",
        "gx2.",
        "gx2/",
        "/gx2",
        "gx2:443",
        "gx2 ",
        " gx2",
        "gx 2",
        "gx2\n",
        "gx2\r\nX-Evil: 1",
        "gx2\r",
        "gx2\x00",
        "gx2\t",
        "-gx2",
        "gx2-",
        "gx_2",
        "gx2?x=1",
        "gx2#frag",
        "gx2@evil",
        "gx2%0d%0a",
        "ação",
        "a" * 64,
    ],
)
def test_tenants_that_could_alter_a_header_or_url_are_refused_before_any_request(
    tenant: str | None,
) -> None:
    with pytest.raises(AcquisitionError) as error:
        InhireCollector.validate_tenant_identifier(tenant)
    assert error.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    board = _Board()
    with pytest.raises(AcquisitionError):
        _run_raising(board, tenant)
    assert board.log == []


def _run_raising(board: _Board, tenant: str | None) -> None:
    async def collect() -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(board.handler))
        try:
            _ = [
                item
                async for item in InhireCollector(client=client).discover(
                    CollectionRequest(company_reference=tenant)
                )
            ]
        finally:
            await client.aclose()

    asyncio.run(collect())


def test_only_the_two_documented_routes_are_requested() -> None:
    board = _Board()
    _run(board, fetch_detail=True)

    for call in board.log:
        assert call.method == "GET"
        assert call.url.host == "api.inhire.app"
        assert call.url.path == _PAGES or (
            call.url.path.startswith(f"{_PAGES}/") and call.url.path.split("/")[-1] in _IDS
        )
        assert "forms" not in str(call.url)
        assert not call.url.query


# --- board states and errors ----------------------------------------------------------


def test_unknown_tenant_is_a_configuration_error_not_an_empty_board() -> None:
    board = _Board()
    board.list_status = 404
    items, error, request = _run(board)

    assert items == []
    assert error is not None
    assert error.code is AcquisitionErrorCode.INVALID_CONFIGURATION
    assert error.field == "configuration.tenant_identifier"
    assert request.telemetry.http_requests == 1  # never retried


def test_empty_board_is_a_complete_empty_run() -> None:
    board = _Board({"tenantName": "Acme", "jobsPage": []})
    items, error, request = _run(board, fetch_detail=True)

    assert items == [] and error is None
    assert request.telemetry.items_announced == 0
    assert request.telemetry.skipped_items == 0
    assert request.telemetry.http_requests == 1


def test_unknown_status_is_skipped_and_counted_never_guessed_published() -> None:
    listing = deepcopy(_LIST)
    listing["jobsPage"][1]["status"] = "closed"
    listing["jobsPage"][2]["status"] = "on_hold_or_something_new"
    listing["jobsPage"].append({**listing["jobsPage"][0], "jobId": str(uuid4()), "status": None})
    board = _Board(listing)
    items, error, request = _run(board, fetch_detail=True)

    assert error is None
    assert [item.external_id for item in items] == [_IDS[0]]
    assert request.telemetry.skipped_items == 3
    assert request.telemetry.items_announced == 4
    assert board.details == [_IDS[0]]  # no detail request for a skipped job


def test_malformed_job_id_is_invalid_and_never_reaches_a_url() -> None:
    listing = deepcopy(_LIST)
    listing["jobsPage"][0]["jobId"] = "../forms/public/job-id/x"
    board = _Board(listing)
    items, error, request = _run(board, fetch_detail=True)

    assert error is None
    assert [item.external_id for item in items] == _IDS[1:]
    assert request.telemetry.invalid_items == 1
    assert all(".." not in str(call.url) for call in board.log)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (429, AcquisitionErrorCode.SOURCE_RATE_LIMITED),
        (403, AcquisitionErrorCode.SOURCE_FORBIDDEN),
    ],
)
def test_429_or_403_on_the_list_stops_the_run_without_retry(
    status: int, code: AcquisitionErrorCode
) -> None:
    board = _Board()
    board.list_status = status
    items, error, request = _run(board, fetch_detail=True)

    assert items == []
    assert error is not None and error.code is code
    assert len(board.log) == 1 and request.telemetry.http_requests == 1
    if status == 429:
        assert error.retry_after_seconds == 7.0
        assert request.telemetry.rate_limit_events == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (429, AcquisitionErrorCode.SOURCE_RATE_LIMITED),
        (403, AcquisitionErrorCode.SOURCE_FORBIDDEN),
    ],
)
def test_429_or_403_on_a_detail_stops_all_further_requests_and_surfaces_after_the_items(
    status: int, code: AcquisitionErrorCode
) -> None:
    board = _Board()
    board.detail_status[_IDS[1]] = status
    items, error, request = _run(board, fetch_detail=True)

    # Every job is still emitted; only the first got its detail. The error follows.
    assert [item.external_id for item in items] == _IDS
    assert [item.description is not None for item in items] == [True, False, False]
    assert error is not None and error.code is code
    assert board.details == _IDS[:2]  # nothing after the refused request, no retry
    assert request.telemetry.detail_requests == 2
    assert request.telemetry.detail_failures == 1
    assert request.telemetry.detail_skipped == 1


def test_server_errors_on_the_list_follow_the_retry_policy() -> None:
    board = _Board()
    board.list_status = 503
    sleeps: list[float] = []
    items, error, request = _run(
        board,
        sleeps=sleeps,
        network_policy=CollectionNetworkPolicy(max_retries=2, retry_delay_seconds=0.5),
    )

    assert items == []
    assert error is not None and error.code is AcquisitionErrorCode.SOURCE_SERVER_ERROR
    assert request.telemetry.http_requests == 3 and request.telemetry.retry_count == 2


@pytest.mark.parametrize("failure", ["server_error", "not_found", "bad_json", "wrong_job"])
def test_a_detail_failure_keeps_the_job_and_does_not_fail_the_run(failure: str) -> None:
    board = _Board()
    original_handler = board.handler

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(_IDS[1]):
            board.log.append(request)
            return {
                "server_error": httpx.Response(500),
                "not_found": httpx.Response(404),
                "bad_json": httpx.Response(200, content=b"<html>"),
                "wrong_job": httpx.Response(200, json={**_DETAIL, "jobId": _IDS[2]}),
            }[failure]
        return original_handler(request)

    board.handler = handler  # type: ignore[method-assign]
    items, error, request = _run(board, fetch_detail=True)

    assert error is None
    assert [item.external_id for item in items] == _IDS
    assert [item.description is not None for item in items] == [True, False, True]
    assert request.telemetry.detail_failures == 1
    assert request.telemetry.detail_requests == 3  # the failure was still a request


# --- caps and budget ------------------------------------------------------------------


def test_per_run_cap_limits_detail_requests_and_the_run_still_succeeds() -> None:
    board = _Board()
    items, error, request = _run(board, fetch_detail=True, detail_max_requests=2)

    assert error is None
    assert [item.external_id for item in items] == _IDS
    assert [item.description is not None for item in items] == [True, True, False]
    assert request.telemetry.detail_requests == 2
    assert request.telemetry.detail_skipped == 1


def test_host_budget_left_limits_detail_requests() -> None:
    # The list spent 1 of the 2 requests the host still allows: one detail fits.
    board = _Board()
    items, error, request = _run(board, fetch_detail=True, host_requests_remaining=2)

    assert error is None and len(items) == 3
    assert len(board.details) == 1
    assert request.telemetry.detail_skipped == 2


def test_detail_is_off_unless_requested() -> None:
    board = _Board()
    _run(board)

    assert board.details == []


# --- new or changed only --------------------------------------------------------------


def _stored(items: list) -> dict[str, dict[str, Any]]:
    """What the service hands back next run: each job's newest stored raw payload."""
    return {item.external_id: dict(item.raw_payload) for item in items}


def _hashes(item) -> tuple[str, str]:
    payload_hash = canonical_payload_hash(dict(item.raw_payload))
    semantic = content_hashes(collected_item_v1(item), raw_hash=payload_hash).semantic_hash
    return payload_hash, semantic


def test_second_run_with_nothing_changed_makes_zero_detail_requests_and_identical_items() -> None:
    first_board = _Board()
    first, _, _ = _run(first_board, fetch_detail=True)
    assert len(first_board.details) == 3

    second_board = _Board()
    second, error, request = _run(second_board, fetch_detail=True, known_items=_stored(first))

    assert error is None
    assert second_board.details == []
    assert [call.url.path for call in second_board.log] == [_PAGES]
    assert request.telemetry.detail_requests == 0
    # Same content and same hashes: the service sees the stored evidence, so no new version.
    assert [_hashes(item) for item in second] == [_hashes(item) for item in first]
    assert [item.description for item in second] == [item.description for item in first]


def test_only_a_new_or_changed_job_gets_a_detail_request() -> None:
    first, _, _ = _run(_Board(), fetch_detail=True)
    listing = deepcopy(_LIST)
    listing["jobsPage"][1]["location"] = "Curitiba, PR, BR"  # changed
    new_id = str(uuid4())
    listing["jobsPage"].append({**listing["jobsPage"][0], "jobId": new_id})  # new
    board = _Board(listing)

    items, error, _ = _run(board, fetch_detail=True, known_items=_stored(first))

    assert error is None
    assert board.details == [_IDS[1], new_id]
    assert items[1].location_text == "Curitiba, PR, BR"
    assert all(item.description is not None for item in items)


def test_changed_job_that_cannot_be_refreshed_keeps_its_stored_content_and_hashes() -> None:
    first, _, _ = _run(_Board(), fetch_detail=True)
    listing = deepcopy(_LIST)
    listing["jobsPage"][0]["displayName"] = "Backend Developer (Go) | Senior"
    board = _Board(listing)

    items, error, request = _run(
        board, fetch_detail=True, detail_max_requests=0, known_items=_stored(first)
    )

    assert error is None and board.details == []
    assert request.telemetry.detail_skipped == 1
    # Never blanked, and no churn: the stored job is re-emitted exactly as stored, so a
    # run without room for the detail creates no "without description" version.
    assert items[0].description == first[0].description
    assert _hashes(items[0]) == _hashes(first[0])
    # The change is picked up once there is room, because the stored list fields still differ.
    later_board = _Board(listing)
    later, _, _ = _run(later_board, fetch_detail=True, known_items=_stored(items))
    assert later_board.details == [_IDS[0]]
    assert later[0].title == "Backend Developer (Go) | Senior"


def test_stored_listing_only_job_is_stable_when_there_is_still_no_room_for_detail() -> None:
    first, _, _ = _run(_Board())  # listing-only: no description key stored
    second, _, _ = _run(
        _Board(), fetch_detail=True, detail_max_requests=0, known_items=_stored(first)
    )

    assert [_hashes(item) for item in second] == [_hashes(item) for item in first]
    assert all(item.description is None for item in second)


def test_stored_listing_only_job_gets_its_detail_once_there_is_room() -> None:
    first, _, _ = _run(_Board())
    board = _Board()
    second, _, _ = _run(board, fetch_detail=True, known_items=_stored(first))

    assert board.details == _IDS
    assert all(item.description is not None for item in second)


# --- weekly re-read of a known job's detail -------------------------------------------


def test_description_only_edit_is_picked_up_on_the_jobs_refresh_day() -> None:
    first, _, _ = _run(_Board(), fetch_detail=True)
    board = _Board()
    board.detail_description = "<p>Edited description, same list fields.</p>"

    items, error, request = _run(
        board, fetch_detail=True, known_items=_stored(first), today=_refresh_day(_IDS[1])
    )

    assert error is None
    due = [job for job in _IDS if _refresh_day(job) == _refresh_day(_IDS[1])]
    assert board.details == due
    assert request.telemetry.detail_requests == len(due)
    by_id = {item.external_id: item for item in items}
    assert set(by_id) == set(_IDS)
    assert by_id[_IDS[1]].description == "<p>Edited description, same list fields.</p>"
    assert _hashes(by_id[_IDS[1]]) != _hashes(first[1])


def test_refresh_that_finds_the_same_content_creates_no_new_version() -> None:
    first, _, _ = _run(_Board(), fetch_detail=True)
    board = _Board()

    items, _, _ = _run(
        board, fetch_detail=True, known_items=_stored(first), today=_refresh_day(_IDS[0])
    )

    assert _IDS[0] in board.details
    assert {_hashes(item) for item in items} == {_hashes(item) for item in first}


def test_refresh_only_uses_the_room_new_and_changed_jobs_leave() -> None:
    first, _, _ = _run(_Board(), fetch_detail=True)
    listing = deepcopy(_LIST)
    new_id = str(uuid4())
    listing["jobsPage"].append({**listing["jobsPage"][0], "jobId": new_id})  # new, listed last
    board = _Board(listing)
    board.detail_description = "<p>Edited.</p>"

    items, error, request = _run(
        board,
        fetch_detail=True,
        detail_max_requests=1,
        known_items=_stored(first),
        today=_refresh_day(_IDS[0]),
    )

    assert error is None
    assert board.details == [new_id]  # the new job wins the only slot
    assert request.telemetry.detail_skipped >= 1
    by_id = {item.external_id: item for item in items}
    # The job that was due stays exactly as stored and is tried again next week.
    assert _hashes(by_id[_IDS[0]]) == _hashes(first[0])


def test_no_refresh_when_detail_is_off() -> None:
    first, _, _ = _run(_Board(), fetch_detail=True)
    board = _Board()

    _run(board, known_items=_stored(first), today=_refresh_day(_IDS[0]))

    assert board.details == []


# --- data minimisation ----------------------------------------------------------------


def test_contact_data_in_the_description_is_masked_before_storage() -> None:
    board = _Board()
    board.detail_description = (
        '<p>Envie para <a href="mailto:maria.silva@acme.example">maria.silva@acme.example</a>'
        " ou ligue (11) 98765-4321, +55 51 3333-4444 ou 21 99876-5432.</p>"
        "<p>Faixa 2024-2025, salário 8000-12000, CNPJ 12.345.678/0001-90.</p>"
    )

    items, _, _ = _run(board, fetch_detail=True)

    text = items[0].description
    assert text == items[0].raw_payload["description"]
    assert "@" not in text and "98765" not in text and "3333" not in text and "99876" not in text
    assert text.count("[email]") == 2 and text.count("[telefone]") == 3
    # Years, ranges and document numbers are not phone numbers.
    assert "2024-2025" in text and "8000-12000" in text and "12.345.678/0001-90" in text


def _all_strings(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_strings(nested)
    elif isinstance(value, str):
        yield value


def test_raw_payload_keeps_only_the_usable_fields() -> None:
    items, _, _ = _run(_Board(), fetch_detail=True)

    for item in items:
        assert set(item.raw_payload) == _STORED_FIELDS
        assert not _FORBIDDEN_KEYS & set(_all_strings(dict(item.raw_payload)))
        serialized = json.dumps(item.raw_payload) + json.dumps(item.metadata)
        for sentinel in (
            "Synthetic automatic e-mail body",
            "Synthetic company text",
            "files.example.test",
            "example.test/privacy",
            "Synthetic location complement",
        ):
            assert sentinel not in serialized


# --- normalizer: work mode and contract reach the opportunity --------------------------


def _normalized(item, *, content_rules: bool):
    return normalize_candidate(
        NormalizationInput(
            raw_item_id=uuid4(),
            source_definition_id=uuid4(),
            source_type=item.source_type,
            external_id=item.external_id,
            url=item.url,
            title=item.title,
            company_name=item.company_name,
            location_text=item.location_text,
            description=item.description,
            published_at=item.published_at,
            metadata=item.metadata,
        ),
        content_rules=content_rules,
    )


@pytest.mark.parametrize("content_rules", [False, True])
def test_work_mode_and_contract_reach_the_normalized_opportunity(content_rules: bool) -> None:
    items, _, _ = _run(_Board(), fetch_detail=True)

    clt_remote = _normalized(items[0], content_rules=content_rules)
    pj_hybrid = _normalized(items[1], content_rules=content_rules)
    internship_onsite = _normalized(items[2], content_rules=content_rules)

    assert (clt_remote.work_mode, clt_remote.contract_type) == (
        WorkMode.REMOTE,
        ContractType.FULL_TIME,
    )
    assert (pj_hybrid.work_mode, pj_hybrid.contract_type) == (
        WorkMode.HYBRID,
        ContractType.CONTRACT,
    )
    assert (internship_onsite.work_mode, internship_onsite.contract_type) == (
        WorkMode.ONSITE,
        ContractType.INTERNSHIP,
    )


def test_unknown_or_mixed_contract_values_stay_unknown_and_listing_only_has_none() -> None:
    board = _Board()
    _CONTRACTS[_IDS[0]] = ["Cooperado"]
    _CONTRACTS[_IDS[1]] = ["CLT", "PJ"]
    try:
        items, _, _ = _run(board, fetch_detail=True)
    finally:
        _CONTRACTS[_IDS[0]], _CONTRACTS[_IDS[1]] = ["CLT"], ["PJ"]
    listing_only, _, _ = _run(_Board())

    assert items[0].metadata["contract_type"] == ["Cooperado"]  # passed as text, not guessed
    assert _normalized(items[0], content_rules=False).contract_type is ContractType.UNKNOWN
    assert _normalized(items[1], content_rules=False).contract_type is ContractType.UNKNOWN
    assert _normalized(listing_only[0], content_rules=False).contract_type is ContractType.UNKNOWN
    # Work mode still comes from the list.
    assert _normalized(listing_only[0], content_rules=False).work_mode is WorkMode.REMOTE


# --- service level --------------------------------------------------------------------


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

    def latest_raw_payloads(self, source_id: object) -> dict[str, dict[str, Any]]:
        del source_id
        return {}

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


def _service(board: _Board, *, configuration: dict[str, Any] | None = None, families=None):
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="inhire",
        name="Acme inHire",
        enabled=True,
        configuration=configuration or {"tenant_identifier": "acme"},
    )
    session = _RunMemorySession()
    repository = _RunMemoryRepository(source)
    waits: list[float] = []

    async def sleeper(seconds: float) -> None:
        waits.append(seconds)

    client = httpx.AsyncClient(transport=httpx.MockTransport(board.handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((InhireCollector(client=client, sleeper=sleeper),)),
        repository=repository,  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
        sleeper=sleeper,
        target_role_families=(lambda: families) if families is not None else None,
    )
    return service, source, repository, session, client


def test_service_runs_an_inhire_source_end_to_end_and_records_target_counts() -> None:
    board = _Board()
    service, source, repository, session, client = _service(
        board, families=("SOFTWARE_ENGINEERING",)
    )
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(client.aclose())

    assert run.status == "SUCCEEDED"
    assert run.items_seen == 3 and run.items_persisted == 3
    # Two engineering titles in the profile's target area, one sales title off target.
    assert run.items_target_area == 2
    assert run.items_off_target == 1
    assert run.http_requests == 4  # 1 list + 3 details (the source's detail default is on)
    assert run.complete is True
    # One bucket on the shared vendor host, charged for every request.
    assert repository.budget_calls == [
        {"host": "api.inhire.app", "requests": 4, "default_ceiling": 1200}
    ]
    stored = [item for item in session.added if isinstance(item, RawItemModel)]
    assert len(stored) == 3
    for raw_item in stored:
        assert set(raw_item.payload_record.payload) == _STORED_FIELDS


def test_service_stops_the_run_with_the_rate_limit_code_when_a_detail_is_refused() -> None:
    board = _Board()
    board.detail_status[_IDS[0]] = 429
    service, source, repository, _, client = _service(board)
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(client.aclose())

    assert run.error_code == AcquisitionErrorCode.SOURCE_RATE_LIMITED.value
    assert run.items_persisted == 3  # the jobs are kept, listing-only
    assert board.details == [_IDS[0]]
    assert run.rate_limit_events == 1


def test_detail_settings_come_from_the_source_configuration() -> None:
    board = _Board()
    service, source, _, _, client = _service(
        board, configuration={"tenant_identifier": "acme", "detail_max_requests": 1}
    )
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(client.aclose())

    assert run.status == "SUCCEEDED" and run.http_requests == 2
    assert board.details == [_IDS[0]]


def test_create_source_validates_the_tenant_and_detail_settings() -> None:
    service, _, _, _, client = _service(_Board())
    asyncio.run(client.aclose())

    for configuration in (
        {"tenant_identifier": "GX2"},
        {"tenant_identifier": "gx2\r\nX-Evil: 1"},
        {"tenant_identifier": "gx2.inhire.app"},
        {},
        {"tenant_identifier": "gx2", "detail_max_requests": -1},
        {"tenant_identifier": "gx2", "fetch_detail": "yes"},
    ):
        with pytest.raises(AcquisitionError) as error:
            service.create_source(
                source_type="inhire", name="Bad", configuration=configuration
            )
        assert error.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION

    source = service.create_source(
        source_type="inhire", name="Acme", configuration={"tenant_identifier": "gx2"}
    )
    assert source.source_type == "inhire" and source.enabled is False


# --- detection, proposals, forbidden list, probe --------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://gx2.inhire.app/vagas",
        "https://gx2.inhire.app/vagas/11111111-1111-4111-8111-111111111111/backend-developer",
        "https://gx2.inhire.app",
        "https://GX2.inhire.app/vagas/",
    ],
)
def test_inhire_board_urls_are_detected_with_the_tenant_as_key(url: str) -> None:
    from opportunity_radar.acquisition.tavily import detect_ats_board

    assert detect_ats_board(url) == ("inhire", "gx2")


@pytest.mark.parametrize(
    "url",
    [
        "https://api.inhire.app/job-posts/public/pages",
        "https://embed.inhire.app/v1/jobs.js",
        "https://www.inhire.app/",
        "https://inhire.app/",
        "https://gx2.inhire.app.evil.test/vagas",
        "https://evil.test/gx2.inhire.app/vagas",
        "https://www.inhire.com.br/privacidade/",
    ],
)
def test_inhire_vendor_hosts_and_lookalikes_are_not_boards(url: str) -> None:
    from opportunity_radar.acquisition.tavily import detect_ats_board

    assert detect_ats_board(url) is None


def test_inhire_is_proposable_and_not_a_forbidden_platform() -> None:
    from opportunity_radar.acquisition.forbidden import (
        forbidden_platform_for_url,
        forbidden_platform_in,
    )
    from opportunity_radar.acquisition.proposals import IDENTIFIER_KEYS
    from opportunity_radar.acquisition.service import PROPOSABLE_SOURCE_TYPES

    assert IDENTIFIER_KEYS["inhire"] == "tenant_identifier"
    assert "inhire" in PROPOSABLE_SOURCE_TYPES
    assert forbidden_platform_for_url("https://gx2.inhire.app/vagas") is None
    assert forbidden_platform_for_url("https://api.inhire.app/job-posts/public/pages") is None
    assert forbidden_platform_in({"tenant_identifier": "gx2", "page": "gx2.inhire.app"}) is None


def _probe(board: _Board, *, tenant: str = "acme"):
    from opportunity_radar.acquisition.probing import run_probe

    async def probe():
        client = httpx.AsyncClient(transport=httpx.MockTransport(board.handler))
        try:
            return await run_probe(
                "inhire",
                {"tenant_identifier": tenant},
                CollectorRegistry((InhireCollector(client=client),)),
                max_items=1,
            )
        finally:
            await client.aclose()

    return asyncio.run(probe())


def test_probe_makes_one_list_request_and_reports_the_board_size() -> None:
    board = _Board()
    outcome = _probe(board)

    assert outcome.ok and outcome.items_seen == 1 and outcome.http_requests == 1
    assert "3 items" in outcome.detail
    assert [call.url.path for call in board.log] == [_PAGES]  # no detail requests


def test_probe_tells_an_empty_board_from_an_unknown_tenant() -> None:
    empty = _probe(_Board({"tenantName": "Acme", "jobsPage": []}))
    assert empty.ok and empty.items_seen == 0 and "0 items" in empty.detail

    missing_board = _Board()
    missing_board.list_status = 404
    missing = _probe(missing_board)
    assert not missing.ok
    assert missing.error_code == AcquisitionErrorCode.INVALID_CONFIGURATION.value
    assert "tenant not found" in missing.detail


def test_probe_refuses_a_malformed_tenant_without_a_request() -> None:
    board = _Board()
    outcome = _probe(board, tenant="gx2\r\nX-Evil: 1")

    assert not outcome.ok and board.log == []
