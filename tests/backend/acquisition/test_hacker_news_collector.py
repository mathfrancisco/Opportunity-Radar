"""F20-55: "Ask HN: Who is hiring?" via Algolia (locate) + Firebase (items), no network."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionNetworkPolicy,
    CollectionRequest,
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.hacker_news import (
    DISCOVERY_VIA,
    HackerNewsCollector,
    parse_comment,
)
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.probing import PROBE_TYPES
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

_ALGOLIA = {
    "hits": [
        {
            "objectID": "900",
            "title": "Ask HN: Who is hiring? (August 2026)",
            "created_at": "2026-08-03T15:00:54Z",
        },
        {
            "objectID": "1000",
            "title": "Ask HN: Who is hiring? (September 2026)",
            "created_at": "2026-09-01T15:01:17Z",
        },
        {
            "objectID": "1001",
            "title": "Ask HN: Who wants to be hired? (September 2026)",
            "created_at": "2026-09-01T15:01:18Z",
        },
    ]
}
_GOOD = (
    "Acme (YC W21) | Junior Backend Engineer | Berlin, Germany | REMOTE (EU) | "
    '<a href="https:&#x2F;&#x2F;boards.greenhouse.io&#x2F;acme&#x2F;jobs&#x2F;1" rel="nofollow">'
    "apply</a><p>We build payments &amp; ledgers.</p>"
)
_COMMENTS: dict[int, dict[str, object]] = {
    1: {"id": 1, "type": "comment", "time": 1790000000, "text": _GOOD},
    2: {
        "id": 2,
        "type": "comment",
        "time": 1790000100,
        "text": "Globex | Data Science Intern | NYC | ONSITE<p>Interns wanted.",
    },
    3: {"id": 3, "type": "comment", "time": 1790000200, "text": "Hiring! DM me for details."},
    4: {"id": 4, "type": "comment", "deleted": True},
    5: {"id": 5, "type": "comment", "time": 1790000300, "dead": True, "text": "spam | x | y"},
    6: {
        "id": 6,
        "type": "comment",
        "time": 1790000400,
        "text": "Initech | Senior Rust Engineer | Remote (US only)",
    },
}

Handler = Callable[[httpx.Request], httpx.Response]


def _handler(calls: list[httpx.Request], *, comments: dict[int, Any] | None = None) -> Handler:
    comments = _COMMENTS if comments is None else comments

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        host, path = request.url.host, request.url.path
        if host == "hn.algolia.com":
            return httpx.Response(200, json=_ALGOLIA)
        assert host == "hacker-news.firebaseio.com", request.url
        item_id = int(path.rsplit("/", 1)[1].removesuffix(".json"))
        if item_id == 1000:
            return httpx.Response(
                200, json={"id": 1000, "type": "story", "kids": list(comments)}
            )
        if item_id == 900:
            return httpx.Response(200, json={"id": 900, "type": "story", "kids": []})
        return httpx.Response(200, json=comments.get(item_id))

    return handler


async def _collect(collector: HackerNewsCollector, request: CollectionRequest):
    return [item async for item in collector.discover(request)]


def _run(request: CollectionRequest, handler: Handler) -> list[CollectedItem]:
    async def go() -> list[CollectedItem]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _collect(HackerNewsCollector(client=client), request)

    return asyncio.run(go())


def test_locates_current_thread_via_algolia_and_reads_comments_via_firebase() -> None:
    calls: list[httpx.Request] = []
    request = CollectionRequest()
    items = _run(request, _handler(calls))

    algolia = [c for c in calls if c.url.host == "hn.algolia.com"]
    assert len(algolia) == 1
    assert algolia[0].url.path == "/api/v1/search_by_date"
    assert algolia[0].url.params["tags"] == "story,author_whoishiring"
    # newest "Who is hiring?" thread (not "Who wants to be hired?"): story + 6 comments
    paths = [c.url.path for c in calls if c.url.host != "hn.algolia.com"]
    assert paths[0] == "/v0/item/1000.json"
    assert len(paths) == 7
    assert not any(c.url.host == "news.ycombinator.com" for c in calls)
    assert request.telemetry.items_announced == 4  # live comments; 2 deleted/dead
    assert [i.external_id for i in items] == ["1", "2", "6"]


def test_month_can_be_pinned_through_company_reference() -> None:
    calls: list[httpx.Request] = []
    items = _run(CollectionRequest(company_reference="2026-08"), _handler(calls))
    assert items == []
    assert [c.url.path for c in calls if c.url.host != "hn.algolia.com"] == [
        "/v0/item/900.json"
    ]


def test_unknown_month_is_source_not_found() -> None:
    with pytest.raises(AcquisitionError) as caught:
        _run(CollectionRequest(company_reference="2020-01"), _handler([]))
    assert caught.value.code is AcquisitionErrorCode.SOURCE_NOT_FOUND


def test_item_maps_company_role_location_remote_and_keeps_attribution() -> None:
    item = _run(CollectionRequest(), _handler([]))[0]
    assert item.source_type == "hacker_news"
    assert item.url == "https://news.ycombinator.com/item?id=1"
    assert item.company_name == "Acme"
    assert item.title == "Junior Backend Engineer"
    assert item.location_text == "REMOTE (EU)"
    assert item.metadata["remote"] is True
    assert item.metadata["yc_batch"] == "W21"
    assert item.metadata["thread_id"] == 1000
    assert item.metadata["attribution"] == "Hacker News"
    assert item.metadata["ats_board_url"] == "https://boards.greenhouse.io/acme/jobs/1"
    assert "We build payments & ledgers." in (item.description or "")
    assert item.published_at is not None and item.published_at.tzinfo is not None
    assert item.raw_payload["id"] == 1


def test_onsite_and_negated_remote_are_not_marked_remote() -> None:
    parsed = parse_comment("Globex | Engineer | NYC | ONSITE")
    assert parsed is not None and parsed.remote is False
    parsed = parse_comment("Globex | Engineer | Berlin | No remote")
    assert parsed is not None and parsed.remote is False
    parsed = parse_comment("Globex | Engineer | Somewhere")
    assert parsed is not None and parsed.remote is None and parsed.location_text is None


def test_comment_without_identifiable_company_or_role_is_a_pending_not_an_item() -> None:
    request = CollectionRequest()
    items = _run(request, _handler([]))
    # comment 3 (free text) is reported, never emitted; deleted/dead are skipped silently.
    assert "3" not in [i.external_id for i in items]
    assert request.telemetry.invalid_items == 1
    assert "3" in (request.telemetry.last_invalid_item_error or "")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Just a sentence without any header at all",
        "https://example.com/careers | Engineer | Remote",
        "| Engineer | Remote",
        "Senior Python Backend Engineer | REMOTE (EMEA/APAC)",  # a role, not a company
        "NYC | ONSITE (hybrid) Norm Ai builds things",
        "Location: London, UK",
        "This is a very long sentence that pretends to be a company name here | Engineer",
    ],
)
def test_parser_refuses_instead_of_guessing(text: str) -> None:
    assert parse_comment(text) is None


def test_header_without_role_keeps_company_but_never_guesses_a_title() -> None:
    parsed = parse_comment("Middesk | Full-time | NYC, NY | Hybrid | middesk.com")
    assert parsed is not None
    assert parsed.company == "Middesk"
    assert parsed.title is None and parsed.roles == ()
    assert parsed.location_text == "Hybrid"


def test_comment_without_a_role_is_skipped_not_emitted_or_invalid() -> None:
    """F48-03: an untitled comment is not an opportunity, so it is `skipped`, not `FAILED`."""
    comments: dict[int, Any] = {
        1: {
            "id": 1,
            "type": "comment",
            "time": 1790000000,
            "text": "Middesk | Full-time | NYC, NY | Hybrid | middesk.com",
        },
        2: {
            "id": 2,
            "type": "comment",
            "time": 1790000100,
            "text": (
                "Middesk | Full-time | NYC, NY | Hybrid | "
                '<a href="https:&#x2F;&#x2F;boards.greenhouse.io&#x2F;middesk&#x2F;jobs&#x2F;1">'
                "apply</a>"
            ),
        },
    }
    request = CollectionRequest()
    items = _run(request, _handler([], comments=comments))
    # The untitled comment that links a supported ATS board still reaches the proposal
    # queue (F20-55), so only the one without any board is skipped.
    assert [i.external_id for i in items] == ["2"]
    assert request.telemetry.skipped_items == 1
    assert request.telemetry.invalid_items == 0


def test_company_urls_and_parentheticals_are_stripped() -> None:
    parsed = parse_comment("Smarkets (https://www.smarkets.com) | Junior Engineer | London, UK")
    assert parsed is not None and parsed.company == "Smarkets"
    assert parsed.location_text == "London, UK"
    parsed = parse_comment("Snout https://snout.com/ | Product Engineer | Remote US")
    assert parsed is not None and parsed.company == "Snout"


def test_keywords_filter_by_comment_text_and_max_items_stops_early() -> None:
    items = _run(CollectionRequest(keywords=("rust",)), _handler([]))
    assert [i.external_id for i in items] == ["6"]
    calls: list[httpx.Request] = []
    items = _run(CollectionRequest(max_items=1), _handler(calls))
    assert [i.external_id for i in items] == ["1"]
    assert len([c for c in calls if c.url.path.startswith("/v0/item/")]) == 2


def test_rate_limit_retries_with_retry_after_then_succeeds() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []
    inner = _handler([])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "hn.algolia.com" and attempts["n"] == 0:
            attempts["n"] += 1
            return httpx.Response(429, headers={"Retry-After": "3"})
        return inner(request)

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async def go() -> tuple[CollectionRequest, list[CollectedItem]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            request = CollectionRequest(max_items=1)
            collector = HackerNewsCollector(client=client, sleeper=sleeper)
            return request, await _collect(collector, request)

    request, items = asyncio.run(go())
    assert [i.external_id for i in items] == ["1"]
    assert sleeps == [3.0]
    assert request.telemetry.rate_limit_events == 1
    assert request.telemetry.retry_count == 1


def test_persistent_rate_limit_and_forbidden_are_typed_errors() -> None:
    policy = CollectionNetworkPolicy(max_retries=0)
    with pytest.raises(AcquisitionError) as caught:
        _run(CollectionRequest(network_policy=policy), lambda _: httpx.Response(429))
    assert caught.value.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED

    with pytest.raises(AcquisitionError) as caught:
        _run(CollectionRequest(network_policy=policy), lambda _: httpx.Response(403))
    assert caught.value.code is AcquisitionErrorCode.SOURCE_FORBIDDEN


def test_minimum_interval_paces_requests() -> None:
    sleeps: list[float] = []

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)

    async def go() -> list[CollectedItem]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(_handler([]))) as client:
            request = CollectionRequest(
                max_items=1,
                network_policy=CollectionNetworkPolicy(minimum_interval_seconds=5.0),
            )
            return await _collect(HackerNewsCollector(client=client, sleeper=sleeper), request)

    asyncio.run(go())
    assert len(sleeps) >= 2 and all(0 < s <= 5.0 for s in sleeps)


def test_malformed_story_is_a_schema_change() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "hn.algolia.com":
            return httpx.Response(200, json=_ALGOLIA)
        return httpx.Response(200, json={"id": 1000, "kids": "nope"})

    with pytest.raises(AcquisitionError) as caught:
        _run(CollectionRequest(), handler)
    assert caught.value.code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED


def test_registered_by_source_type_and_probeable() -> None:
    registry = build_collector_registry(greenhouse_base_url="http://unused")
    collector = registry.resolve("hacker_news")
    assert isinstance(collector, HackerNewsCollector)
    assert collector.capabilities.keyword_search
    assert "hacker_news" in PROBE_TYPES


# --- database integration: ATS board in a comment -> proposal via "hn_who_is_hiring" ---

_PREFIX = "f20-55:"
_integration = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _purge() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        ids = list(
            session.scalars(
                select(SourceDefinitionModel.id).where(
                    or_(
                        SourceDefinitionModel.name.startswith(_PREFIX),
                        SourceDefinitionModel.configuration["company_name"]
                        .as_string()
                        .startswith(_PREFIX),
                    )
                )
            )
        )
        if ids:
            session.execute(delete(RawItemModel).where(RawItemModel.source_definition_id.in_(ids)))
            session.execute(
                delete(SourceRunModel).where(SourceRunModel.source_definition_id.in_(ids))
            )
            session.execute(
                delete(SourceDefinitionModel).where(SourceDefinitionModel.id.in_(ids))
            )
        session.execute(delete(Company).where(Company.canonical_name.startswith(_PREFIX)))
        session.commit()


@pytest.fixture
def _clean() -> Iterator[None]:
    _purge()
    yield
    _purge()


@_integration
@pytest.mark.integration
def test_ats_board_comment_creates_proposal_tagged_hn_who_is_hiring(_clean: None) -> None:
    name = f"{_PREFIX}Acme{uuid4().hex[:6]}"
    comments = {
        1: {
            "id": 1,
            "type": "comment",
            "time": 1790000000,
            "text": (
                f"{name} | Junior Engineer | Remote | "
                '<a href="https://boards.greenhouse.io/acme-hn/jobs/1">apply</a>'
            ),
        },
        2: {"id": 2, "type": "comment", "time": 1790000001, "text": "not a job header"},
    }
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        marker = uuid4().hex
        session.add(Company(canonical_name=name, normalized_name=f"f20-55-{marker}"))
        source = SourceDefinitionModel(
            source_type="hacker_news",
            name=f"{_PREFIX}hn-{marker}",
            enabled=True,
            configuration={},
            evidence_status="confirmed",
            terms_reviewed=True,
            collector_local_tested=True,
        )
        session.add(source)
        session.commit()

        async def go():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(_handler([], comments=comments))
            ) as client:
                service = AcquisitionService(
                    session,
                    registry=CollectorRegistry(
                        (HackerNewsCollector(client=client), GreenhouseCollector())
                    ),
                )
                return await service.execute(source.id, CollectionRequest())

        run = asyncio.run(go())

        assert run.items_persisted == 1
        assert run.items_invalid == 1  # the free-text comment is a pending, not a success
        assert str(run.status) == "PARTIAL"
        proposal = session.scalar(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.source_type == "greenhouse",
                SourceDefinitionModel.configuration["company_name"].as_string() == name,
            )
        )
        assert proposal is not None, (run.error_code, run.error_summary)
        assert proposal.configuration["discovery_via"] == DISCOVERY_VIA == "hn_who_is_hiring"
        assert proposal.configuration["board_token"] == "acme-hn"
        assert proposal.enabled is False
