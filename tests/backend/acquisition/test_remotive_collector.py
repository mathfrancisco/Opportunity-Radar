import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionNetworkPolicy,
    CollectionRequest,
)
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.acquisition.scheduling import ConditionalRequestHeaders
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    ProfileSnapshot,
    ProfileVersion,
    ProfileVersionStatus,
    Skill,
)
from opportunity_radar.profile.service import ProfileService
from opportunity_radar.worker import _scheduled_request

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
    # The fixture's date is "2026-09-13T12:30:00": no timezone, so none is invented (F48-03).
    assert item.published_at is None
    assert item.raw_payload == payload["jobs"][0]
    assert item.metadata["category"] == "Software Development"
    assert item.metadata["attribution"] == "Remotive"
    assert item.metadata["parser_version"] == "remotive-remote-jobs-v2"
    assert item.metadata["tags"] == ["python", "backend"]
    assert request.telemetry.http_requests == 1


def test_receives_keywords_derived_from_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"job-count": 0, "jobs": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    profile = ProfileVersion(
        id=uuid4(),
        number=1,
        status=ProfileVersionStatus.ACTIVE,
        profile_lock_version=1,
        snapshot=ProfileSnapshot(
            skills=(Skill("Python", level="advanced"), Skill("React", level="basic")),
            experiences=(),
            projects=(),
            preferences=EmploymentPreference(target_titles=("Backend Engineer",)),
        ),
    )
    monkeypatch.setattr(ProfileService, "get_active", lambda self: profile)
    source = SimpleNamespace(
        id=uuid4(),
        source_type="remotive",
        configuration={"keywords": ["remote"]},
        checkpoint=None,
    )
    registry = CollectorRegistry((RemotiveCollector(client=client),))
    service = SimpleNamespace(session=object(), registry=registry)
    request = _scheduled_request(service, source, "test-correlation")

    try:
        asyncio.run(_collect(registry.resolve("remotive"), request))
    finally:
        asyncio.run(client.aclose())

    assert request.keywords == ("backend engineer", "python", "remote")
    assert calls[0].url.params["search"] == "backend engineer python remote"


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


def test_sends_conditional_headers_when_checkpoint_has_validators() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"job-count": 0, "jobs": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    request = CollectionRequest(
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        asyncio.run(_collect(RemotiveCollector(client=client), request))
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
        conditional_headers=ConditionalRequestHeaders(if_none_match='"abc123"'),
    )
    try:
        items = asyncio.run(_collect(RemotiveCollector(client=client), request))
    finally:
        asyncio.run(client.aclose())

    assert items == []
    assert request.telemetry.not_modified is True
    assert request.telemetry.response_etag == '"abc123"'
    assert request.telemetry.items_announced is None


def test_publication_date_keeps_an_explicit_timezone_and_drops_a_naive_one() -> None:
    aware = RemotiveCollector._published_at("2026-09-12T10:00:00Z")
    assert aware is not None and aware.utcoffset() is not None
    assert RemotiveCollector._published_at("2026-09-29T08:00:00") is None
    assert RemotiveCollector._published_at(None) is None
