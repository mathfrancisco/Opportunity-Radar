from __future__ import annotations

import asyncio

import httpx
import pytest

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionRequest,
)
from opportunity_radar.acquisition.jobposting import JobPostingCollector, extract_job_postings
from opportunity_radar.acquisition.probing import probe_request, run_probe
from tests.e2e.fake_jobposting_site import (
    PAGE_URL,
    divergent_schema,
    graph_of_postings,
    list_of_postings,
    missing_required_fields,
    mixed_valid_and_missing,
    no_markup_at_all,
    single_object_en,
    single_object_pt,
    soft_404,
    telecommute_without_location_requirements,
)


def _client(html: str, *, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=html.encode("utf-8"))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _collect(collector: JobPostingCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def _request(**overrides) -> CollectionRequest:
    defaults = {"company_reference": PAGE_URL}
    defaults.update(overrides)
    return CollectionRequest(**defaults)


def test_object_list_and_graph_produce_items_with_provenance() -> None:
    for html, expected_titles in (
        (single_object_en(), {"Senior Backend Engineer"}),
        (list_of_postings(), {"Data Engineer", "Frontend Engineer"}),
        (graph_of_postings(), {"Site Reliability Engineer"}),
    ):
        client = _client(html)
        try:
            items = asyncio.run(_collect(JobPostingCollector(client=client), _request()))
        finally:
            asyncio.run(client.aclose())
        assert {item.title for item in items} == expected_titles
        for item in items:
            assert item.company_name
            assert item.url
            assert item.metadata["job_posting_v1"]["parser_version"]


def test_pt_and_en_are_both_extracted() -> None:
    for html in (single_object_en(), single_object_pt()):
        client = _client(html)
        try:
            items = asyncio.run(_collect(JobPostingCollector(client=client), _request()))
        finally:
            asyncio.run(client.aclose())
        assert len(items) == 1
        assert items[0].title


def test_missing_fields_are_unknown_not_fabricated() -> None:
    client = _client(single_object_pt())
    try:
        items = asyncio.run(_collect(JobPostingCollector(client=client), _request()))
    finally:
        asyncio.run(client.aclose())
    item = items[0]
    assert item.published_at is not None
    metadata = item.metadata["job_posting_v1"]
    assert metadata["base_salary_min"] is None
    assert metadata["base_salary_currency"] is None
    assert metadata["job_location_type"] is None


def test_salary_fields_are_separated_when_present() -> None:
    client = _client(single_object_en())
    try:
        items = asyncio.run(_collect(JobPostingCollector(client=client), _request()))
    finally:
        asyncio.run(client.aclose())
    metadata = items[0].metadata["job_posting_v1"]
    assert metadata["base_salary_min"] == "120000"
    assert metadata["base_salary_max"] == "160000"
    assert metadata["base_salary_currency"] == "USD"
    assert metadata["base_salary_unit"] == "YEAR"


def test_mixed_valid_and_missing_keeps_only_the_valid_node() -> None:
    fields = extract_job_postings(mixed_valid_and_missing(), page_url=PAGE_URL)
    assert len(fields) == 1
    assert fields[0].title == "Support Engineer"


@pytest.mark.parametrize(
    "html",
    [missing_required_fields(), divergent_schema(), soft_404(), no_markup_at_all(), ""],
)
def test_blocked_page_is_not_empty_success(html: str) -> None:
    client = _client(html)
    try:
        with pytest.raises(AcquisitionError) as exc_info:
            asyncio.run(_collect(JobPostingCollector(client=client), _request()))
    finally:
        asyncio.run(client.aclose())
    assert exc_info.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_soft_404_is_flagged_not_persisted() -> None:
    client = _client(soft_404())
    try:
        with pytest.raises(AcquisitionError) as exc_info:
            asyncio.run(_collect(JobPostingCollector(client=client), _request()))
    finally:
        asyncio.run(client.aclose())
    assert exc_info.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_telecommute_does_not_imply_global_eligibility() -> None:
    fields = extract_job_postings(
        telecommute_without_location_requirements(), page_url=PAGE_URL
    )
    assert len(fields) == 1
    assert fields[0].job_location_type == "TELECOMMUTE"
    assert fields[0].applicant_location_requirements == ()


def test_probe_exercises_real_collector() -> None:
    client = _client(single_object_en())
    try:
        registry = CollectorRegistry((JobPostingCollector(client=client),))
        outcome = asyncio.run(
            run_probe(
                "jobposting",
                {"page_url": PAGE_URL},
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())
    assert outcome.ok is True
    assert outcome.items_seen == 1
    assert outcome.http_requests == 1


def test_probe_request_requires_page_url() -> None:
    with pytest.raises(ValueError):
        probe_request("jobposting", {}, max_items=1)


def test_missing_page_url_is_invalid_configuration() -> None:
    client = _client(single_object_en())
    try:
        with pytest.raises(AcquisitionError) as exc_info:
            asyncio.run(
                _collect(JobPostingCollector(client=client), CollectionRequest())
            )
    finally:
        asyncio.run(client.aclose())
    assert exc_info.value.code is AcquisitionErrorCode.INVALID_CONFIGURATION
    assert exc_info.value.field == "configuration.page_url"


def test_max_items_bounds_emitted_items() -> None:
    client = _client(list_of_postings())
    try:
        items = asyncio.run(
            _collect(JobPostingCollector(client=client), _request(max_items=1))
        )
    finally:
        asyncio.run(client.aclose())
    assert len(items) == 1
