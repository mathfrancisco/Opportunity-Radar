import asyncio
from collections.abc import AsyncIterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from opportunity_radar.acquisition.alerts import SourceAlertService
from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    ExecutionTrigger,
    HealthResult,
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
)
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.acquisition.scheduling import SourceRunHistory
from opportunity_radar.acquisition.service import (
    COLLECTED_ITEM_V1_KEY,
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

    def scalar(self, statement: object) -> None:
        """No incident has ever been opened in memory, which is what a query would say."""
        del statement
        return None


class _MemoryRepository:
    def __init__(self, source: SourceDefinitionModel) -> None:
        self.source = source
        self.hashes: set[tuple[str, str]] = set()

    def run_history(self, source_id: object, *, sample: int = 32) -> SourceRunHistory:
        del source_id, sample
        return SourceRunHistory()

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


class _UnderReportingCollector(_Collector):
    """Announces more items than it ever yields, like a board with broken pagination."""

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        request.telemetry.record_items_announced(5)
        items = [
            CollectedItem(
                source_type=self.source_type,
                external_id="job-1",
                raw_payload={"title": "First"},
            ),
            CollectedItem(
                source_type=self.source_type,
                external_id="job-2",
                raw_payload={"title": "Second"},
            ),
        ]
        if request.max_items is not None:
            items = items[: request.max_items]
        for item in items:
            yield item


class _RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send(self, message: dict[str, object]) -> bool:
        self.messages.append(message)
        return True


def _service(
    collector: _Collector, *, notifier: _RecordingNotifier | None = None
) -> tuple[AcquisitionService, _MemorySession]:
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
        alerts=SourceAlertService(session, notifier=notifier),  # type: ignore[arg-type]
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


def test_run_defaults_to_on_demand_execution_trigger() -> None:
    service, _ = _service(_Collector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.execution_trigger == ExecutionTrigger.ON_DEMAND.value


def test_run_persists_scheduled_execution_trigger() -> None:
    service, _ = _service(_Collector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(
                mode=CollectionMode.DISCOVERY,
                execution_trigger=ExecutionTrigger.SCHEDULED,
            ),
        )
    )

    assert run.execution_trigger == ExecutionTrigger.SCHEDULED.value


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


def test_pagination_gap_alert_fires_for_an_unbounded_shortfall() -> None:
    notifier = _RecordingNotifier()
    service, _ = _service(_UnderReportingCollector(), notifier=notifier)

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.items_seen == 2
    assert run.items_announced == 5
    assert [message["event"] for message in notifier.messages] == [
        "source_pagination_gap"
    ]
    assert notifier.messages[0]["items_seen"] == 2
    assert notifier.messages[0]["items_announced"] == 5


def test_pagination_gap_alert_does_not_fire_when_max_items_caps_the_run() -> None:
    notifier = _RecordingNotifier()
    service, _ = _service(_UnderReportingCollector(), notifier=notifier)

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY, max_items=1),
        )
    )

    assert run.items_seen == 1
    assert run.items_announced == 5
    assert notifier.messages == []


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
    snapshot = raw_items[0].item_metadata[COLLECTED_ITEM_V1_KEY]
    assert snapshot["version"] == 1
    assert snapshot["source_type"] == "ashby"
    assert snapshot["external_id"].startswith("ashby:")
    assert snapshot["url"] == "https://jobs.ashbyhq.com/acme/job-1"
    assert snapshot["title"] == "Backend Engineer"
    assert snapshot["company_name"] == "Acme"
    assert snapshot["metadata"]["parser_version"] == "ashby-job-board-v2"
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


def test_rejects_search_filters_when_collector_does_not_support_them() -> None:
    service, session = _service(_Collector())

    with pytest.raises(AcquisitionError, match="does not support keyword search"):
        asyncio.run(
            service.execute(
                service.repository.source.id,
                CollectionRequest(keywords=("python",)),
            )
        )

    assert session.added == []


def test_lever_source_configuration_reaches_paginated_collector() -> None:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="lever",
        name="Spotify jobs",
        enabled=True,
        rate_limit_policy={},
        configuration={
            "site_identifier": "spotify",
            "company_name": "Spotify",
            "api_region": "global",
        },
    )
    session = _MemorySession()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/postings/spotify")
        return httpx.Response(
            200,
            json=[
                {
                    "id": "spotify-job-1",
                    "text": "Backend Engineer",
                    "hostedUrl": "https://jobs.lever.co/spotify/job-1",
                }
            ],
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((LeverCollector(client=client),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
    )
    try:
        run = asyncio.run(service.execute(source.id, CollectionRequest()))
    finally:
        asyncio.run(client.aclose())

    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert run.status == "SUCCEEDED"
    assert run.items_seen == 1
    assert run.items_persisted == 1
    assert run.http_requests == 1
    assert raw_items[0].external_id == "spotify-job-1"


def test_greenhouse_source_configuration_reaches_collector() -> None:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="greenhouse",
        name="AssemblyAI jobs",
        enabled=True,
        rate_limit_policy={},
        configuration={
            "board_token": "assemblyai",
            "company_name": "AssemblyAI",
        },
    )
    session = _MemorySession()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/boards/assemblyai/jobs")
        assert request.url.params["content"] == "true"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 123,
                        "title": "ML Engineer",
                        "absolute_url": (
                            "https://job-boards.greenhouse.io/assemblyai/jobs/123"
                        ),
                    }
                ],
                "meta": {"total": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((GreenhouseCollector(client=client),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
    )
    try:
        run = asyncio.run(service.execute(source.id, CollectionRequest()))
    finally:
        asyncio.run(client.aclose())

    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert run.status == "SUCCEEDED"
    assert run.items_seen == 1
    assert run.items_persisted == 1
    assert run.http_requests == 1
    assert raw_items[0].external_id == "123"


def test_remotive_query_uses_separate_interval_between_runs() -> None:
    throttling_delays: list[float] = []

    async def sleeper(delay: float) -> None:
        throttling_delays.append(delay)

    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="remotive",
        name="Remotive remote jobs",
        enabled=True,
        rate_limit_policy={"minimum_run_interval_seconds": 21_600},
        configuration={},
        last_http_attempt_at=datetime.now(UTC) - timedelta(hours=7),
    )
    session = _MemorySession()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == "python backend"
        assert request.url.params["limit"] == "1"
        return httpx.Response(
            200,
            json={
                "job-count": 1,
                "jobs": [
                    {
                        "id": 42,
                        "url": "https://remotive.com/remote-jobs/dev/job-42",
                        "title": "Python Engineer",
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((RemotiveCollector(client=client),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
        sleeper=sleeper,
    )
    try:
        run = asyncio.run(
            service.execute(
                source.id,
                CollectionRequest(keywords=("python", "backend"), max_items=1),
            )
        )
    finally:
        asyncio.run(client.aclose())

    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert run.status == "SUCCEEDED"
    assert run.items_persisted == 1
    assert raw_items[0].external_id == "42"
    assert throttling_delays == []


def test_run_interval_fails_fast_without_holding_the_request() -> None:
    sleeper_delays: list[float] = []
    network_called = False

    async def sleeper(delay: float) -> None:
        sleeper_delays.append(delay)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal network_called
        network_called = True
        return httpx.Response(200, json={"job-count": 0, "jobs": []})

    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="remotive",
        name="Remotive remote jobs",
        enabled=True,
        rate_limit_policy={"minimum_run_interval_seconds": 21_600},
        configuration={},
        last_http_attempt_at=datetime.now(UTC),
    )
    session = _MemorySession()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((RemotiveCollector(client=client),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
        sleeper=sleeper,
    )

    try:
        run = asyncio.run(service.execute(source.id, CollectionRequest()))
    finally:
        asyncio.run(client.aclose())

    assert run.status == "FAILED"
    assert run.error_code == AcquisitionErrorCode.SOURCE_RATE_LIMITED.value
    assert run.http_requests == 0
    assert run.rate_limit_events == 1
    assert sleeper_delays == []
    assert network_called is False
