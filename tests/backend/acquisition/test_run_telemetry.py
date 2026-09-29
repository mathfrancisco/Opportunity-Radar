"""F48-07: a run records how many bytes it received and how fresh its newest item was."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    item_payload_bytes,
    newest_item_age_seconds,
)
from tests.backend.acquisition.test_service import _Collector, _service


class _DatedCollector(_Collector):
    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        now = datetime.now(UTC)
        for index, age in enumerate((timedelta(days=3), timedelta(hours=2))):
            yield CollectedItem(
                source_type=self.source_type,
                external_id=f"job-{index}",
                raw_payload={"title": f"Role {index}"},
                published_at=now - age,
            )


def _execute(collector: _Collector):
    service, _ = _service(collector)
    return asyncio.run(
        service.execute(
            service.repository.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
        )
    )


def test_bytes_received_sums_the_serialized_payloads() -> None:
    run = _execute(_Collector())

    expected = sum(
        len(json.dumps({"title": title}).encode())
        for title in ("First", "First", "Changed")
    )
    assert run.bytes_received == expected


def test_newest_item_age_is_none_when_no_item_carries_a_date() -> None:
    assert _execute(_Collector()).newest_item_age_seconds is None


def test_newest_item_age_uses_the_freshest_dated_item() -> None:
    run = _execute(_DatedCollector())

    assert run.newest_item_age_seconds is not None
    assert 2 * 3600 <= run.newest_item_age_seconds < 2 * 3600 + 60


def test_pure_helpers() -> None:
    item = CollectedItem(source_type="x", raw_payload={"a": "é"})
    assert item_payload_bytes(item) == len(json.dumps({"a": "é"}, ensure_ascii=False).encode())
    at = datetime(2026, 9, 29, 12, tzinfo=UTC)
    assert newest_item_age_seconds(at - timedelta(minutes=5), at) == 300
    assert newest_item_age_seconds(at + timedelta(minutes=5), at) == 0
    assert newest_item_age_seconds(None, at) is None
