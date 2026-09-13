import asyncio
from collections.abc import AsyncIterator
from contextlib import nullcontext
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
)
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
)
from opportunity_radar.acquisition.service import (
    AcquisitionService,
    canonical_payload_hash,
)


class _MemorySession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, model: object) -> None:
        self.added.append(model)

    def flush(self) -> None:
        return None

    def begin_nested(self):
        return nullcontext()

    def rollback(self) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def refresh(self, model: object, attribute_names: object = None) -> None:
        del attribute_names
        return None


class _MemoryRepository:
    def __init__(self, source: SourceDefinitionModel) -> None:
        self.source = source
        self.hashes: set[tuple[str, str]] = set()

    def get_source(self, source_id: object) -> SourceDefinitionModel | None:
        return self.source if source_id == self.source.id else None

    def identical_raw_item_exists(
        self, *, source_id: object, identity_key: str, payload_hash: str
    ) -> bool:
        key = (identity_key, payload_hash)
        if key in self.hashes:
            return True
        self.hashes.add(key)
        return False


class _Collector:
    source_type = "example"
    capabilities = CollectorCapabilities()

    async def healthcheck(self, context: object = None) -> HealthResult:
        return HealthResult(healthy=True)

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            raw_payload={"title": "First"},
            cursor="cursor-1",
        )
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            raw_payload={"title": "First"},
            cursor="cursor-1",
        )
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            raw_payload={"title": "Changed"},
            cursor="cursor-2",
        )


class _FailingCollector(_Collector):
    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            raw_payload={"title": "First"},
        )
        raise AcquisitionError(
            AcquisitionErrorCode.SOURCE_TIMEOUT,
            "timed out",
            retryable=True,
        )


class _PartiallyInvalidCollector(_Collector):
    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            raw_payload={"title": "First"},
            cursor="cursor-1",
        )
        yield CollectedItem(
            source_type=self.source_type,
            raw_payload={"title": "Missing identity"},
            cursor="cursor-2",
        )


def _service(collector: _Collector) -> tuple[AcquisitionService, _MemorySession]:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="example",
        name="Example",
        enabled=True,
        configuration={},
    )
    session = _MemorySession()
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((collector,)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
    )
    return service, session


def test_payload_hash_is_canonical_for_mapping_order() -> None:
    first_hash = canonical_payload_hash({"a": 1, "b": 2})
    second_hash = canonical_payload_hash({"b": 2, "a": 1})

    assert first_hash == second_hash


def test_run_deduplicates_identical_identity_but_preserves_changed_payload() -> None:
    service, session = _service(_Collector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.status == "SUCCEEDED"
    assert run.items_seen == 3
    assert run.items_persisted == 2
    assert run.items_skipped == 1
    assert run.checkpoint_after == "cursor-2"
    assert session.committed


def test_collector_failure_after_evidence_marks_run_partial() -> None:
    service, _ = _service(_FailingCollector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.status == "PARTIAL"
    assert run.error_code == AcquisitionErrorCode.SOURCE_TIMEOUT.value
    assert run.items_persisted == 1


def test_partial_run_does_not_promote_checkpoint() -> None:
    service, session = _service(_PartiallyInvalidCollector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    checkpoints = [
        item for item in session.added if isinstance(item, SourceCheckpointModel)
    ]
    assert run.status == "PARTIAL"
    assert run.items_invalid == 1
    assert run.checkpoint_after is None
    assert checkpoints == []


def test_ashby_source_configuration_reaches_collector_and_records_http_metrics() -> None:
    throttling_delays: list[float] = []

    async def sleeper(delay: float) -> None:
        throttling_delays.append(delay)

    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="ashby",
        name="Acme jobs",
        enabled=True,
        rate_limit_policy={
            "minimum_interval_seconds": 5,
            "max_retry_delay_seconds": 30,
        },
        configuration={"board_identifier": "acme", "company_name": "Acme"},
        last_http_attempt_at=datetime.now(UTC),
    )
    session = _MemorySession()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/job-board/acme")
        return httpx.Response(
            200,
            json={
                "apiVersion": "1",
                "jobs": [
                    {"title": "Broken", "isListed": True},
                    {
                        "title": "Backend Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/acme/job-1",
                        "isListed": True,
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((AshbyCollector(client=client),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
        sleeper=sleeper,
    )
    try:
        run = asyncio.run(service.execute(source.id, CollectionRequest()))
    finally:
        asyncio.run(client.aclose())

    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert run.status == "PARTIAL"
    assert run.error_code == AcquisitionErrorCode.INVALID_ITEM.value
    assert run.items_seen == 2
    assert run.items_invalid == 1
    assert run.items_persisted == 1
    assert run.http_requests == 1
    assert run.retry_count == 0
    assert raw_items[0].payload["title"] == "Backend Engineer"
    assert len(throttling_delays) == 1
    assert 0 < throttling_delays[0] <= 5


def test_reused_request_does_not_leak_telemetry_between_runs() -> None:
    class TelemetryCollector(_Collector):
        async def discover(
            self, request: CollectionRequest
        ) -> AsyncIterator[CollectedItem]:
            request.telemetry.record_http_attempt()
            yield CollectedItem(
                source_type=self.source_type,
                external_id="job-1",
                raw_payload={"title": "First"},
            )

    service, _ = _service(TelemetryCollector())
    request = CollectionRequest()

    first = asyncio.run(service.execute(service.repository.source.id, request))
    second = asyncio.run(service.execute(service.repository.source.id, request))

    assert first.http_requests == 1
    assert second.http_requests == 1
    assert request.telemetry.http_requests == 0


def test_rejects_incremental_mode_when_collector_does_not_support_it() -> None:
    service, session = _service(_Collector())

    with pytest.raises(AcquisitionError, match="does not support incremental"):
        asyncio.run(
            service.execute(
                service.repository.source.id,
                CollectionRequest(mode=CollectionMode.INCREMENTAL),
            )
        )

    assert session.added == []
