"""F48-07: a run records how many bytes it received and how fresh its newest item was."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    item_payload_bytes,
    newest_item_age_seconds,
)
from opportunity_radar.acquisition.models import RawItemModel
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


class _TimeoutAfterFirstPage(_Collector):
    """Page one lists X, the request for page two times out."""

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type, external_id="job-X", raw_payload={"title": "X"}
        )
        raise AcquisitionError(AcquisitionErrorCode.SOURCE_TIMEOUT, "page 2 timed out")


class _QuotaAfterKnownPage(_Collector):
    """Page one is a posting already stored; page two hits the provider quota."""

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type, external_id="job-X", raw_payload={"title": "X"}
        )
        raise AcquisitionError(AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED, "quota")


def _execute_times(collector: _Collector, times: int):
    service, session = _service(collector)
    source_id = service.repository.source.id  # type: ignore[attr-defined]
    runs = [
        asyncio.run(service.execute(source_id, CollectionRequest(mode=CollectionMode.DISCOVERY)))
        for _ in range(times)
    ]
    return runs, session


def test_timeout_after_page_preserves_positive_presence() -> None:
    (run,), session = _execute_times(_TimeoutAfterFirstPage(), 1)

    assert run.status == "PARTIAL"
    assert run.error_code == AcquisitionErrorCode.SOURCE_TIMEOUT.value
    assert run.complete is False
    assert run.items_seen == 1 and run.items_persisted == 1
    # X's evidence was written; nothing in the run claims an absence.
    assert any(isinstance(model, RawItemModel) for model in session.added)
    assert run.items_announced is None


def test_failure_after_already_known_page_is_partial_not_failed() -> None:
    (first, second), _ = _execute_times(_QuotaAfterKnownPage(), 2)

    assert first.status == "PARTIAL"
    assert second.items_persisted == 0 and second.items_seen == 1
    assert second.status == "PARTIAL"
    assert second.complete is False


def test_failure_before_any_valid_item_stays_failed() -> None:
    class _Immediate(_Collector):
        async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
            del request
            raise AcquisitionError(AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED, "quota")
            yield  # pragma: no cover

    (run,), _ = _execute_times(_Immediate(), 1)

    assert run.status == "FAILED"
    assert run.complete is False
