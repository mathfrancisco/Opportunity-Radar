"""Tests for the Tavily extraction cache and batched extraction routine (F20-45).

`extract_missing_descriptions` is exercised against `_FakeCache`, an in-memory stand-in
for `ExtractionCachePort` — the same reasoning `Collector` gets tested without a database
for. `TavilyExtractionCache` itself, the SQLAlchemy-backed implementation, is proven
against a real Postgres schema in the integration tests below, which only run with
`RUN_DATABASE_INTEGRATION=1` (see `tests/backend/acquisition/test_alerts.py` for the same
pattern) — they are skipped in this environment, which has no Docker/Postgres available.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionTelemetry,
    SourceRun,
)
from opportunity_radar.acquisition.tavily import (
    ExtractionResult,
    TavilyClient,
    TavilyCreditBudget,
    TavilyExtractionCache,
    apply_extracted_description,
    canonicalize_url,
    extract_missing_descriptions,
)

pytestmark_integration = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


@dataclass
class _FakeCache:
    """In-memory stand-in for `ExtractionCachePort`, with an injectable clock for TTL tests."""

    ttl_seconds: float
    clock: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))
    entries: dict[str, tuple[ExtractionResult, datetime]] = field(default_factory=dict)

    def get(self, url: str) -> ExtractionResult | None:
        entry = self.entries.get(canonicalize_url(url))
        if entry is None:
            return None
        result, expires_at = entry
        if expires_at <= self.clock():
            return None
        return replace(result, from_cache=True)

    def put(self, url: str, result: ExtractionResult) -> None:
        self.entries[canonicalize_url(url)] = (
            result,
            self.clock() + timedelta(seconds=self.ttl_seconds),
        )


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> TavilyClient:
    return TavilyClient(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def _telemetry() -> CollectionTelemetry:
    return CollectionTelemetry()


async def _aclose(client: TavilyClient) -> None:
    await client.aclose()


def test_url_extracted_once_stays_cached_within_ttl() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/jobs/1", "raw_content": "# Job"}
                ],
                "usage": {"credits": 1},
            },
        )

    client = _client(handler)
    cache = _FakeCache(ttl_seconds=3600)

    import asyncio

    try:
        first = asyncio.run(
            extract_missing_descriptions(
                client, cache, ["https://example.com/jobs/1"], telemetry=_telemetry()
            )
        )
        second = asyncio.run(
            extract_missing_descriptions(
                client, cache, ["https://example.com/jobs/1"], telemetry=_telemetry()
            )
        )
    finally:
        asyncio.run(_aclose(client))

    assert calls == 1
    assert first[0].from_cache is False
    assert second[0].from_cache is True
    assert second[0].raw_content == "# Job"


def test_expired_cache_entry_is_treated_as_miss_and_recorded_again() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/jobs/1", "raw_content": f"# Job {calls}"}
                ],
                "usage": {"credits": 1},
            },
        )

    client = _client(handler)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    cache = _FakeCache(ttl_seconds=10, clock=lambda: now)

    import asyncio

    try:
        asyncio.run(
            extract_missing_descriptions(
                client, cache, ["https://example.com/jobs/1"], telemetry=_telemetry()
            )
        )
        now = now + timedelta(seconds=20)  # past the TTL: the entry is now a miss
        second = asyncio.run(
            extract_missing_descriptions(
                client, cache, ["https://example.com/jobs/1"], telemetry=_telemetry()
            )
        )
    finally:
        asyncio.run(_aclose(client))

    assert calls == 2
    assert second[0].from_cache is False
    assert second[0].raw_content == "# Job 2"


def test_batch_over_twenty_urls_is_partitioned() -> None:
    batch_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.content)
        batch_sizes.append(len(payload["urls"]))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": url, "raw_content": "# ok"} for url in payload["urls"]
                ],
                "usage": {"credits": 1},
            },
        )

    client = _client(handler)
    cache = _FakeCache(ttl_seconds=3600)
    urls = [f"https://example.com/jobs/{i}" for i in range(25)]

    import asyncio

    try:
        results = asyncio.run(
            extract_missing_descriptions(client, cache, urls, telemetry=_telemetry())
        )
    finally:
        asyncio.run(_aclose(client))

    assert batch_sizes == [20, 5]
    assert len(results) == 25


def test_isolated_failure_in_batch_preserves_other_nineteen_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.content)
        urls = payload["urls"]
        failing = urls[0]
        ok_urls = urls[1:]
        return httpx.Response(
            200,
            json={
                "results": [{"url": url, "raw_content": "# ok"} for url in ok_urls],
                "failed_results": [
                    {"url": failing, "error": "could not extract content"}
                ],
                "usage": {"credits": 1},
            },
        )

    client = _client(handler)
    cache = _FakeCache(ttl_seconds=3600)
    urls = [f"https://example.com/jobs/{i}" for i in range(20)]

    import asyncio

    try:
        results = asyncio.run(
            extract_missing_descriptions(client, cache, urls, telemetry=_telemetry())
        )
    finally:
        asyncio.run(_aclose(client))

    failed = [result for result in results if result.error is not None]
    succeeded = [result for result in results if result.error is None]
    assert len(failed) == 1
    assert failed[0].url == urls[0]
    assert failed[0].error == "could not extract content"
    assert len(succeeded) == 19


def test_extraction_credits_feed_the_shared_run_accumulator() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/jobs/1", "raw_content": "# Job"}
                ],
                "usage": {"credits": 3},
            },
        )

    client = _client(handler)
    cache = _FakeCache(ttl_seconds=3600)
    budget = TavilyCreditBudget(limit=100)
    run = SourceRun(source_definition_id=uuid4())
    run.start()

    import asyncio

    try:
        asyncio.run(
            extract_missing_descriptions(
                client,
                cache,
                ["https://example.com/jobs/1"],
                telemetry=_telemetry(),
                budget=budget,
                run=run,
            )
        )
    finally:
        asyncio.run(_aclose(client))

    assert run.credits_used == 3
    assert budget.spent == 3


def test_budget_stops_second_uncached_extract_batch_after_paid_first_batch() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        import json

        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": url, "raw_content": "# Job"} for url in payload["urls"]
                ],
                "usage": {"credits": 2},
            },
        )

    client = _client(handler)
    cache = _FakeCache(ttl_seconds=3600)
    budget = TavilyCreditBudget(limit=2)
    run = SourceRun(source_definition_id=uuid4())
    run.start()
    urls = [f"https://example.com/jobs/{index}" for index in range(21)]

    import asyncio

    try:
        with pytest.raises(AcquisitionError) as error:
            asyncio.run(
                extract_missing_descriptions(
                    client, cache, urls, telemetry=_telemetry(), budget=budget, run=run
                )
            )
    finally:
        asyncio.run(_aclose(client))

    assert error.value.code is AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED
    assert calls == 1
    assert run.credits_used == 2
    assert cache.get(urls[0]) is not None


def test_extracted_markdown_replaces_provisional_description() -> None:
    item = CollectedItem(
        source_type="tavily_search",
        url="https://example.com/jobs/1",
        description="short snippet",
        raw_payload={},
    )
    result = ExtractionResult(
        url=item.url or "", raw_content="# Full markdown body", error=None, from_cache=False
    )

    updated = apply_extracted_description(item, result)

    assert updated.description == "# Full markdown body"


def test_extraction_miss_or_failure_keeps_provisional_description() -> None:
    item = CollectedItem(
        source_type="tavily_search",
        url="https://example.com/jobs/1",
        description="short snippet",
        raw_payload={},
    )
    result = ExtractionResult(
        url=item.url or "", raw_content=None, error="failed", from_cache=False
    )

    updated = apply_extracted_description(item, result)

    assert updated.description == "short snippet"


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_cache_get_put_roundtrip_against_real_schema() -> None:
    """Not runnable here (no Docker/Postgres in this environment) — verified in CI's
    isolated database. See module docstring."""
    from sqlalchemy.orm import sessionmaker

    from opportunity_radar.platform.database import create_database_engine

    engine = create_database_engine()
    with sessionmaker(bind=engine)() as session:
        cache = TavilyExtractionCache(session=session, ttl_seconds=3600)
        cache.put(
            "https://Example.com/jobs/1?utm_source=x",
            ExtractionResult(
                url="https://example.com/jobs/1",
                raw_content="# Job",
                error=None,
                from_cache=False,
            ),
        )
        session.commit()

        hit = cache.get("https://example.com/jobs/1")
        assert hit is not None
        assert hit.raw_content == "# Job"
        assert hit.from_cache is True


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_cache_expired_row_reads_as_miss_against_real_schema() -> None:
    """Not runnable here (no Docker/Postgres in this environment) — verified in CI's
    isolated database. See module docstring."""
    from sqlalchemy.orm import sessionmaker

    from opportunity_radar.acquisition.models import TavilyExtractCacheModel
    from opportunity_radar.platform.database import create_database_engine

    engine = create_database_engine()
    with sessionmaker(bind=engine)() as session:
        cache = TavilyExtractionCache(session=session, ttl_seconds=1)
        cache.put(
            "https://example.com/jobs/2",
            ExtractionResult(
                url="https://example.com/jobs/2",
                raw_content="# Job",
                error=None,
                from_cache=False,
            ),
        )
        session.flush()
        row = session.get(TavilyExtractCacheModel, cache._hash("https://example.com/jobs/2"))
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

        assert cache.get("https://example.com/jobs/2") is None
