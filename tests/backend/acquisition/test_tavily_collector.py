"""Tests for the Tavily web-discovery collector (F20-44)."""

import asyncio
from typing import Any

import httpx
import pytest

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    CollectionRequest,
)
from opportunity_radar.acquisition.tavily import (
    TavilyClient,
    TavilySearchCollector,
    canonicalize_url,
    detect_ats_board,
)


def _client(payload: dict[str, Any]) -> TavilyClient:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _result(url: str, **overrides: Any) -> dict[str, Any]:
    base = {"url": url, "title": "A job", "content": "Body", "score": 0.5}
    base.update(overrides)
    return base


def test_registered_and_resolves_by_tavily_search() -> None:
    registry = CollectorRegistry(
        (TavilySearchCollector(client_factory=lambda: _client({"results": []})),)
    )

    resolved = registry.resolve("tavily_search")

    assert resolved.source_type == "tavily_search"


def test_query_includes_profile_keywords_and_include_domains_when_configured() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"results": []})

    client = TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    collector = TavilySearchCollector(
        client=client, include_domains=["boards.greenhouse.io", "jobs.lever.co"]
    )

    asyncio.run(_collect(collector, CollectionRequest(keywords=("backend", "remote"))))

    assert captured["query"] == "backend remote"
    assert captured["include_domains"] == ["boards.greenhouse.io", "jobs.lever.co"]


def test_time_range_never_open() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"results": []})

    client = TavilyClient(
        api_key="test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    collector = TavilySearchCollector(client=client)

    asyncio.run(_collect(collector, CollectionRequest(keywords=("backend",))))

    assert captured["time_range"]
    assert captured["time_range"] is not None


def test_collected_item_metadata_has_query_rank_score_retrieved_at_parser_version() -> None:
    client = _client({"results": [_result("https://example.com/jobs/1")]})
    collector = TavilySearchCollector(client=client)

    items = asyncio.run(_collect(collector, CollectionRequest(keywords=("backend",))))

    assert len(items) == 1
    metadata = items[0].metadata
    assert metadata["query"] == "backend"
    assert metadata["rank"] == 0
    assert metadata["score"] == 0.5
    assert metadata["retrieved_at"]
    assert metadata["parser_version"] == "tavily-search-v1"


def test_equivalent_urls_deduplicate_within_one_run() -> None:
    client = _client(
        {
            "results": [
                _result("https://Example.com/jobs/1?utm_source=x"),
                _result("https://example.com/jobs/1#apply"),
                _result("https://example.com/jobs/2"),
            ]
        }
    )
    collector = TavilySearchCollector(client=client)

    items = asyncio.run(_collect(collector, CollectionRequest(keywords=("backend",))))

    assert len(items) == 2


def test_known_ats_board_marks_source_proposal_candidate() -> None:
    client = _client({"results": [_result("https://boards.greenhouse.io/acme/jobs/1")]})
    collector = TavilySearchCollector(client=client, known_ats_boards=frozenset())

    items = asyncio.run(_collect(collector, CollectionRequest(keywords=("backend",))))

    assert items[0].metadata["source_proposal_candidate"] is True


def test_enabled_ats_board_loaded_per_request_does_not_mark_candidate() -> None:
    client = _client({"results": [_result("https://boards.greenhouse.io/acme/jobs/1")]})
    collector = TavilySearchCollector(client=client)
    request = CollectionRequest(
        keywords=("backend",),
        known_ats_boards=frozenset({("greenhouse", "acme")}),
    )

    items = asyncio.run(_collect(collector, request))

    assert "source_proposal_candidate" not in items[0].metadata


def test_non_ats_url_does_not_mark_candidate() -> None:
    client = _client({"results": [_result("https://example.com/jobs/1")]})
    collector = TavilySearchCollector(client=client)

    items = asyncio.run(_collect(collector, CollectionRequest(keywords=("backend",))))

    assert "source_proposal_candidate" not in items[0].metadata


def test_discover_requires_at_least_one_keyword() -> None:
    client = _client({"results": []})
    collector = TavilySearchCollector(client=client)

    with pytest.raises(AcquisitionError):
        asyncio.run(_collect(collector, CollectionRequest()))


def test_canonicalize_url_strips_tracking_query_and_fragment_lowercases_host() -> None:
    result = canonicalize_url("https://Example.COM/Jobs/1/?utm_source=x&b=2&a=1#section")

    assert result == "https://example.com/Jobs/1?a=1&b=2"


def test_detect_ats_board_matches_known_patterns_and_returns_none_otherwise() -> None:
    assert detect_ats_board("https://boards.greenhouse.io/acme/jobs/12345") == (
        "greenhouse",
        "acme",
    )
    assert detect_ats_board("https://jobs.lever.co/acme/abc") == ("lever", "acme")
    assert detect_ats_board("https://jobs.ashbyhq.com/acme/abc") == ("ashby", "acme")
    assert detect_ats_board("https://example.com/jobs/1") is None


async def _collect(collector: TavilySearchCollector, request: CollectionRequest) -> list[Any]:
    return [item async for item in collector.discover(request)]
