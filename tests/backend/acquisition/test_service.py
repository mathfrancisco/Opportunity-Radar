import asyncio
import json
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
from opportunity_radar.acquisition.factorial import FactorialCollector
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.inventory_contract import (
    INVENTORY_CONTRACTS,
    PAGINATION_NONE,
    PAGINATION_OFFSET,
)
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
)
from opportunity_radar.acquisition.probing import run_probe
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.acquisition.scheduling import SourceRunHistory
from opportunity_radar.acquisition.service import (
    COLLECTED_ITEM_V1_KEY,
    AcquisitionService,
    _workday_detail_approval,
    canonical_payload_hash,
)
from opportunity_radar.acquisition.tavily import TavilyClient, TavilyExtractionSettings
from opportunity_radar.acquisition.teamtailor import TeamtailorCollector
from opportunity_radar.acquisition.workable import WorkableCollector
from opportunity_radar.acquisition.workday import WorkdayCollector


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

    def get(self, model: type, primary_key: object) -> None:
        """No cache row has ever been written here, so every lookup is a cache miss —
        exactly what `TavilyExtractionCache.get`/`put` need to run without a real
        database (see `test_execute_fills_missing_description_via_tavily_extraction`)."""
        del model, primary_key
        return None


class _MemoryRepository:
    def __init__(self, source: SourceDefinitionModel) -> None:
        self.source = source
        self.hashes: set[tuple[object, str, str, str, str]] = set()

    def run_history(self, source_id: object, *, sample: int = 32) -> SourceRunHistory:
        del source_id, sample
        return SourceRunHistory()

    def get_source(self, source_id: object) -> SourceDefinitionModel | None:
        return self.source if source_id == self.source.id else None

    def identical_raw_item_exists(
        self, *, source_id: object, identity_key: str, payload_hash: str
    ) -> bool:
        # Compatibility seam for older test adapters. Production uses the envelope-aware
        # lookup below, which also keeps parser interpretation in the dedupe key.
        key = (source_id, identity_key, payload_hash, "", "")
        if key in self.hashes:
            return True
        self.hashes.add(key)
        return False

    def raw_item_by_envelope(
        self,
        *,
        source_id: object,
        identity_key: str,
        payload_hash: str,
        semantic_hash: str,
        semantic_hash_version: str,
    ) -> bool:
        key = (source_id, identity_key, payload_hash, semantic_hash, semantic_hash_version)
        if key in self.hashes:
            return True
        self.hashes.add(key)
        return False

    def get_host_budget(self, host: str) -> None:
        """No shared budget persisted in memory: `scheduling_state` sees `None`, and
        `execute`'s per-run bookkeeping (F20-38) has nothing to read back here."""
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
        del host, now, requests, default_ceiling, cooldown_until


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


class _RepeatedCursorLoopCollector(_Collector):
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
        raise AcquisitionError(
            AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
            "provider repeated cursor cursor-1",
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


class _NoDescriptionCollector(_Collector):
    """Yields one item with a URL but no description, like any collector normalizing an
    item that arrived with no body — not only `tavily_search`'s own results (F20-45)."""

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            url="https://example.com/jobs/1",
            raw_payload={"title": "First"},
        )


class _SkippedAndValidItemsCollector(_Collector):
    """Yields valid items and records skipped items in telemetry, like Hacker News
    when comments lack identifiable company/role."""

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        # Record a skipped item
        request.telemetry.record_skipped_item()
        # Yield a valid item
        yield CollectedItem(
            source_type=self.source_type,
            external_id="job-1",
            raw_payload={"title": "First"},
        )


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


def test_source_deadline_waits_for_generator_cleanup_and_finishes_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class _WaitingCollector(_Collector):
        async def discover(
            self, request: CollectionRequest
        ) -> AsyncIterator[CollectedItem]:
            del request
            try:
                yield CollectedItem(
                    source_type=self.source_type,
                    external_id="job-timeout",
                    raw_payload={"title": "Waiting"},
                )
            finally:
                closed.append(True)

    service, session = _service(_WaitingCollector())

    async def wait_forever(*_args: object, **_kwargs: object) -> CollectedItem:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    monkeypatch.setattr(service, "_fill_missing_description", wait_forever)
    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
            deadline_seconds=0.01,
        )
    )

    persisted_run = next(item for item in session.added if hasattr(item, "status"))
    assert closed == [True]
    assert run.status == "PARTIAL"
    assert run.complete is False
    assert persisted_run.status == "PARTIAL"
    assert session.committed is True


def test_source_deadline_is_partial_when_collector_suppresses_cancellation() -> None:
    class _SuppressingCollector(_Collector):
        async def discover(
            self, request: CollectionRequest
        ) -> AsyncIterator[CollectedItem]:
            del request
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                yield CollectedItem(
                    source_type=self.source_type,
                    external_id="job-late",
                    raw_payload={"title": "Late"},
                )

    service, session = _service(_SuppressingCollector())
    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
            deadline_seconds=0.01,
        )
    )

    assert run.status == "PARTIAL"
    assert run.complete is False
    assert run.items_seen == 0
    assert session.committed is True


def test_source_deadline_after_enrichment_prevents_late_item_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OneItemCollector(_Collector):
        async def discover(
            self, request: CollectionRequest
        ) -> AsyncIterator[CollectedItem]:
            del request
            yield CollectedItem(
                source_type=self.source_type,
                external_id="job-enrichment-timeout",
                title="Late enrichment",
                description="already present",
                raw_payload={"title": "Late enrichment"},
            )

    service, session = _service(_OneItemCollector())

    async def suppress_cancel(item: CollectedItem, **_kwargs: object) -> CollectedItem:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return item
        raise AssertionError("unreachable")

    monkeypatch.setattr(service, "_fill_missing_description", suppress_cancel)
    run = asyncio.run(
        service.execute(
            service.repository.source.id,  # type: ignore[attr-defined]
            CollectionRequest(mode=CollectionMode.DISCOVERY),
            deadline_seconds=0.01,
        )
    )

    assert run.status == "PARTIAL"
    assert run.complete is False
    assert run.items_persisted == 0
    assert not any(isinstance(item, RawItemModel) for item in session.added)


def test_deadline_includes_throttle_sleep_and_never_starts_discovery() -> None:
    collector = _Collector()
    service, _ = _service(collector)
    source = service.repository.source  # type: ignore[attr-defined]
    source.last_http_attempt_at = datetime.now(UTC)
    source.rate_limit_policy = {"minimum_interval_seconds": 15}
    started = False

    async def sleeper(_delay: float) -> None:
        await asyncio.Event().wait()

    async def discover(request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        nonlocal started
        started = True
        del request
        if False:
            yield CollectedItem(source_type="example", external_id="unused")

    collector.discover = discover  # type: ignore[method-assign]
    service._sleeper = sleeper
    run = asyncio.run(
        service.execute(
            source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
            deadline_seconds=0.01,
        )
    )

    assert started is False
    assert run.status == "PARTIAL"
    assert run.error_code == AcquisitionErrorCode.SOURCE_TIMEOUT.value


def test_external_cancel_waits_for_live_collector_cleanup_and_logs_pending(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entered_second_request = asyncio.Event()
    release_cleanup = asyncio.Event()
    cleanup_finished = asyncio.Event()
    second_request_started = False

    class _LiveCollector(_Collector):
        async def discover(
            self, request: CollectionRequest
        ) -> AsyncIterator[CollectedItem]:
            nonlocal second_request_started
            del request
            try:
                yield CollectedItem(
                    source_type=self.source_type,
                    external_id="first-request",
                    title="Persisted",
                    description="Present",
                    raw_payload={"title": "Persisted"},
                )
                second_request_started = True
                entered_second_request.set()
                await asyncio.Event().wait()
            finally:
                await release_cleanup.wait()
                cleanup_finished.set()

    async def run_cancelled() -> tuple[object, _MemorySession]:
        service, session = _service(_LiveCollector())
        task = asyncio.create_task(
            service.execute(
                service.repository.source.id,  # type: ignore[attr-defined]
                CollectionRequest(mode=CollectionMode.DISCOVERY),
            )
        )
        await entered_second_request.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert task.done() is False
        assert cleanup_finished.is_set() is False
        assert second_request_started is True
        release_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        return task, session

    with caplog.at_level("WARNING", logger="opportunity_radar.acquisition.service"):
        _, session = asyncio.run(run_cancelled())

    assert cleanup_finished.is_set()
    assert session.committed is True
    pending = next(
        record for record in caplog.records if record.message == "source collection cleanup pending"
    )
    assert pending.state == "cleanup_pending"


def test_parser_or_parsed_boundary_variant_creates_fresh_raw_evidence() -> None:
    service, session = _service(_Collector())
    raw_payload = {"id": "job-1", "body": "unchanged bytes"}
    parser_v1 = CollectedItem(
        source_type="example",
        external_id="job-1",
        title="Backend Engineer",
        description="Build APIs.",
        raw_payload=raw_payload,
        metadata={"parser_version": "example-v1"},
    )
    parser_v2 = CollectedItem(
        source_type="example",
        external_id="job-1",
        title="Backend Engineer",
        description="Build APIs.",
        raw_payload=raw_payload,
        metadata={"parser_version": "example-v2"},
    )
    corrected_fields = CollectedItem(
        source_type="example",
        external_id="job-1",
        title="Backend Engineer",
        description="Build APIs with Python.",
        raw_payload=raw_payload,
        metadata={"parser_version": "example-v2"},
    )

    assert service._persist_item(  # noqa: SLF001 - verifies the persistence boundary.
        service.repository.source.id, uuid4(), "example", parser_v1, observed_at=datetime.now(UTC)
    )
    assert not service._persist_item(  # noqa: SLF001
        service.repository.source.id, uuid4(), "example", parser_v1, observed_at=datetime.now(UTC)
    )
    assert service._persist_item(  # noqa: SLF001
        service.repository.source.id, uuid4(), "example", parser_v2, observed_at=datetime.now(UTC)
    )
    assert service._persist_item(  # noqa: SLF001
        service.repository.source.id,
        uuid4(),
        "example",
        corrected_fields,
        observed_at=datetime.now(UTC),
    )

    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert len(raw_items) == 3
    assert {item.payload_hash for item in raw_items} == {canonical_payload_hash(raw_payload)}
    assert [item.item_metadata["parser_version"] for item in raw_items] == [
        "example-v1",
        "example-v2",
        "example-v2",
    ]
    assert len({item.semantic_hash for item in raw_items}) == 3


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


def test_execute_fills_missing_description_via_tavily_extraction() -> None:
    """The real wiring gap this closes (F20-45): before this, nothing in the collection
    flow called `extract_missing_descriptions` — the routine existed and was tested in
    isolation, but no run ever reached it. `_NoDescriptionCollector` stands in for any
    collector (not `tavily_search` itself) whose item arrived with no body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://example.com/jobs/1", "raw_content": "# Full body"}
                ],
                "usage": {"credits": 1},
            },
        )

    tavily_extraction = TavilyExtractionSettings(
        client_factory=lambda: TavilyClient(
            api_key="test-key",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        ),
        cache_ttl_seconds=3600,
        credit_budget_per_run=100,
    )
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
        registry=CollectorRegistry((_NoDescriptionCollector(),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
        tavily_extraction=tavily_extraction,
    )

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.status == "SUCCEEDED"
    assert run.credits_used == 1
    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert len(raw_items) == 1
    persisted = raw_items[0].item_metadata[COLLECTED_ITEM_V1_KEY]
    assert persisted["description"] == "# Full body"


def _extraction_service(
    calls: list[httpx.Request], **settings: object
) -> tuple[AcquisitionService, list[dict[str, object]]]:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://example.com/jobs/1", "raw_content": "# Body"}],
                "usage": {"credits": 1},
            },
        )

    budget_calls: list[dict[str, object]] = []

    class _Repository(_MemoryRepository):
        def record_host_budget_usage(self, host: str, **kwargs: object) -> None:
            budget_calls.append({"host": host, **kwargs})

    source = SourceDefinitionModel(
        id=uuid4(), source_type="example", name="Example", enabled=True, configuration={}
    )
    session = _MemorySession()
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((_NoDescriptionCollector(),)),
        repository=_Repository(source),  # type: ignore[arg-type]
        alerts=SourceAlertService(session, notifier=None),  # type: ignore[arg-type]
        tavily_extraction=TavilyExtractionSettings(
            client_factory=lambda: TavilyClient(
                api_key="test-key",
                client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            ),
            cache_ttl_seconds=3600,
            credit_budget_per_run=100,
            **settings,  # type: ignore[arg-type]
        ),
    )
    return service, budget_calls


def _execute(service: AcquisitionService):
    return asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )


def test_tavily_calls_are_not_counted_in_the_ats_host_budget() -> None:
    calls: list[httpx.Request] = []
    service, budget_calls = _extraction_service(calls)

    run = _execute(service)

    assert len(calls) == 1
    assert run.credits_used == 1
    # The collector made no request of its own: the Tavily call must not show up here.
    assert budget_calls == []


def test_extraction_skip_source_types_spends_no_tavily_call() -> None:
    calls: list[httpx.Request] = []
    service, _ = _extraction_service(calls, skip_source_types=frozenset({"example"}))

    run = _execute(service)

    assert calls == []
    assert run.status == "SUCCEEDED"
    assert run.credits_used == 0


def test_extraction_stops_for_a_host_that_keeps_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    from opportunity_radar.acquisition.tavily import TavilyExtractionCache

    seen: list[tuple[str, int]] = []

    def failing(self: object, url: str, *, threshold: int) -> bool:
        seen.append((url, threshold))
        return True

    monkeypatch.setattr(TavilyExtractionCache, "host_is_failing", failing)
    calls: list[httpx.Request] = []
    service, _ = _extraction_service(calls, host_failure_threshold=3)

    run = _execute(service)

    assert calls == []
    assert seen == [("https://example.com/jobs/1", 3)]
    assert run.status == "SUCCEEDED"


def test_execute_leaves_description_alone_when_extraction_is_not_configured() -> None:
    """No `tavily_extraction` passed to `AcquisitionService` (the default): the run must
    still succeed, with the item's own (absent) description untouched — extraction is an
    opt-in enrichment, not a requirement for collection to work."""
    service, session = _service(_NoDescriptionCollector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.status == "SUCCEEDED"
    raw_items = [item for item in session.added if isinstance(item, RawItemModel)]
    assert len(raw_items) == 1
    assert raw_items[0].item_metadata[COLLECTED_ITEM_V1_KEY]["description"] is None


def test_repeated_cursor_loop_error_never_marks_run_complete() -> None:
    service, _ = _service(_RepeatedCursorLoopCollector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,
            CollectionRequest(mode=CollectionMode.DISCOVERY),
        )
    )

    assert run.status == "PARTIAL"
    assert run.complete is False
    assert run.checkpoint_after is None


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
    assert run.complete is False
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


def test_workday_source_configuration_reaches_collector_via_execute() -> None:
    """F20-28/F20-38: `_collector_settings` must build a Workday `CollectionRequest` from
    `SourceDefinitionModel.configuration` the same way `probe_request` already does — a
    real homologated Workday source ran through `service.execute` with `company_reference`
    left as `None` (only the probe path built it), so every scheduled run raised
    INVALID_CONFIGURATION before this fix. `tenant_identifier`/`api_region` are the keys
    `IDENTIFIER_KEYS`/`probe_request` already use for this ATS."""
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="workday",
        name="Acme jobs",
        enabled=True,
        configuration={
            "tenant_identifier": "acme/ExternalCareerSite",
            "api_region": "wd5",
            "company_name": "Acme",
        },
        last_http_attempt_at=datetime.now(UTC),
    )
    session = _MemorySession()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "acme.wd5.myworkdayjobs.com"
        return httpx.Response(
            200,
            json={
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Backend Engineer",
                        "externalPath": "/job/Remote/Backend-Engineer_R1",
                        "locationsText": "Remote",
                        "bulletFields": ["R1"],
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((WorkdayCollector(client=client),)),
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
    assert raw_items[0].payload["title"] == "Backend Engineer"


def test_workday_untitled_postings_count_as_skipped_and_do_not_degrade_the_run() -> None:
    """F20-75: untitled Workday postings are skipped, so the run stays SUCCEEDED."""
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="workday",
        name="Acme jobs",
        enabled=True,
        configuration={
            "tenant_identifier": "acme/ExternalCareerSite",
            "api_region": "wd5",
            "company_name": "Acme",
        },
        last_http_attempt_at=datetime.now(UTC),
    )
    session = _MemorySession()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "total": 2,
                "jobPostings": [
                    {"externalPath": "/job/Remote/Untitled_R0"},
                    {
                        "title": "Backend Engineer",
                        "externalPath": "/job/Remote/Backend-Engineer_R1",
                        "bulletFields": ["R1"],
                    },
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((WorkdayCollector(client=client),)),
        repository=_MemoryRepository(source),  # type: ignore[arg-type]
    )
    try:
        run = asyncio.run(service.execute(source.id, CollectionRequest()))
    finally:
        asyncio.run(client.aclose())

    assert run.status == "SUCCEEDED"
    assert run.error_code is None
    assert run.items_seen == 2
    assert run.items_persisted == 1
    assert run.items_skipped == 1
    assert run.items_invalid == 0


def test_probe_reports_retry_after_on_rate_limit() -> None:
    """F20-25: a probe against a rate-limited endpoint surfaces `Retry-After` so the
    homologation queue's batch mode knows how long to wait before the next probe."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, headers={"Retry-After": "12"})
        )
    )
    registry = CollectorRegistry((AshbyCollector(client=client, max_retries=0),))
    try:
        outcome = asyncio.run(
            run_probe(
                "ashby",
                {"board_identifier": "acme", "company_name": "Acme"},
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ok is False
    assert outcome.error_code == AcquisitionErrorCode.SOURCE_RATE_LIMITED.value
    assert outcome.retry_after_seconds == 12.0


def test_probe_leaves_retry_after_unset_when_not_rate_limited() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(500))
    )
    registry = CollectorRegistry((AshbyCollector(client=client, max_retries=0),))
    try:
        outcome = asyncio.run(
            run_probe(
                "ashby",
                {"board_identifier": "acme", "company_name": "Acme"},
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ok is False
    assert outcome.error_code == AcquisitionErrorCode.SOURCE_SERVER_ERROR.value
    assert outcome.retry_after_seconds is None


def test_probe_recognizes_teamtailor_source_type() -> None:
    """F20-29: the sonda (probe) must resolve `teamtailor` from a source's own
    `company_identifier` configuration, the same way it already does for the other ATS
    types, so homologation can test a Teamtailor board before it is enabled."""
    payload = {
        "items": [
            {
                "id": "job-1",
                "title": "Backend Engineer",
                "url": "https://jobs.acme-careers.test/jobs/job-1",
                "date_published": "2026-09-01T12:00:00Z",
            }
        ]
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    registry = CollectorRegistry((TeamtailorCollector(client=client),))
    try:
        outcome = asyncio.run(
            run_probe(
                "teamtailor",
                {
                    "company_identifier": "jobs.acme-careers.test",
                    "company_name": "Acme",
                },
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ok is True
    assert outcome.items_seen == 1
    assert outcome.http_requests == 1


def test_probe_recognizes_factorial_source_type() -> None:
    """F20-31: the sonda (probe) must resolve `factorial` from a source's own
    `company_identifier` configuration, the same way it already does for the other ATS
    types, so homologation can test a Factorial board before it is enabled."""
    page = """<html><body><div data-controller='job-filters'><ul>
    <li class='job-offer-item' data-is-remote='true' data-contract-type='indefinite'
    data-job-postings-url='https://acme.factorialhr.com/job_posting/job-1'
    data-team-id='1' data-location-id='1'>
    <div><span><div class="factorial__headingFontFamily">Backend Engineer</div></span>
    <div><div class="text-gray-350">Engineering</div></div>
    <div><div class="text-gray-350">Remote</div></div></div></li>
    </ul></div></body></html>"""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=page, headers={"Content-Type": "text/html"})
        )
    )
    registry = CollectorRegistry((FactorialCollector(client=client),))
    try:
        outcome = asyncio.run(
            run_probe(
                "factorial",
                {"company_identifier": "acme", "company_name": "Acme"},
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ok is True
    assert outcome.items_seen == 1
    assert outcome.http_requests == 1


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


def test_probe_recognizes_workday_source_type() -> None:
    """F20-28: the sonda knows how to build a Workday request from its configuration."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Backend Engineer",
                        "externalPath": "/job/Remote/Backend-Engineer_R1",
                        "locationsText": "Remote",
                        "bulletFields": ["R1"],
                    }
                ],
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = CollectorRegistry((WorkdayCollector(client=client),))
    try:
        outcome = asyncio.run(
            run_probe(
                "workday",
                {
                    "tenant_identifier": "acme/ExternalCareerSite",
                    "api_region": "wd5",
                    "company_name": "Acme",
                },
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ok is True
    assert outcome.items_seen == 1
    assert calls[0].url.host == "acme.wd5.myworkdayjobs.com"


def test_probe_recognizes_workable_source_type() -> None:
    """F20-30: the sonda knows how to build a Workable request from its configuration."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "abc123",
                        "title": "Backend Engineer",
                        "url": "https://apply.workable.com/acme/j/ABC123/",
                        "location": {"location_str": "Remote"},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = CollectorRegistry((WorkableCollector(client=client),))
    try:
        outcome = asyncio.run(
            run_probe(
                "workable",
                {"account_identifier": "acme", "company_name": "Acme"},
                registry,
                max_items=5,
            )
        )
    finally:
        asyncio.run(client.aclose())

    assert outcome.ok is True
    assert outcome.items_seen == 1
    assert calls[0].url.host == "apply.workable.com"


# --- F48-19: central forbidden-platform list ---------------------------------------


@pytest.mark.parametrize(
    "configuration",
    [
        {"board_identifier": "acme", "careers_url": "https://acme.gupy.io/"},
        {"board_identifier": "acme", "discovery_evidence": "https://wellfound.com/company/acme"},
        {"board_identifier": "acme", "url": "https://www.ycombinator.com/jobs/acme"},
    ],
)
def test_create_source_refuses_forbidden_platform(configuration: dict[str, str]) -> None:
    session = _MemorySession()
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((AshbyCollector(client=httpx.AsyncClient()),)),
    )

    with pytest.raises(AcquisitionError) as refused:
        service.create_source(source_type="ashby", name="Acme", configuration=configuration)

    assert refused.value.code == AcquisitionErrorCode.INVALID_CONFIGURATION
    assert "forbidden platform" in str(refused.value)
    assert session.added == []


def test_create_source_accepts_unrelated_hosts() -> None:
    session = _MemorySession()
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((AshbyCollector(client=httpx.AsyncClient()),)),
    )

    source = service.create_source(
        source_type="ashby",
        name="Acme",
        configuration={
            "board_identifier": "acme",
            "discovery_evidence": "https://news.ycombinator.com/item?id=1",
        },
    )

    assert source.configuration["board_identifier"] == "acme"


# F50-04: target-area counters and the noise filter.


class _MixedTitlesCollector(_Collector):
    """One engineering, one sales and one title no rule recognises."""

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        for external_id, title in (
            ("eng", "Senior Backend Engineer"),
            ("sales", "Account Executive"),
            ("unknown", "Wizard of Light"),
        ):
            yield CollectedItem(
                source_type=self.source_type,
                external_id=external_id,
                title=title,
                raw_payload={"id": external_id, "title": title},
            )


class _ShareRepository(_MemoryRepository):
    """Memory repository that answers `target_area_share` and, like production, returns
    the stored row for an item it already knows (keyed by identity key)."""

    def __init__(self, source: SourceDefinitionModel, share: float | None) -> None:
        super().__init__(source)
        self.share = share
        self.share_calls = 0
        self.known: dict[str, RawItemModel] = {}
        self.presence: list[RawItemModel] = []
        self.presence_flags: list[tuple[RawItemModel, bool]] = []
        self.latest: dict[str, RawItemModel] = {}

    def target_area_share(self, source_id: object, *, runs: int = 3) -> float | None:
        del source_id, runs
        self.share_calls += 1
        return self.share

    def raw_item_by_envelope(  # type: ignore[override]
        self,
        *,
        source_id: object,
        identity_key: str,
        payload_hash: str,
        semantic_hash: str,
        semantic_hash_version: str,
    ) -> RawItemModel | None:
        del source_id, payload_hash, semantic_hash, semantic_hash_version
        return self.known.get(identity_key)

    def latest_raw_item_by_identity(
        self, *, source_id: object, identity_key: str
    ) -> RawItemModel | None:
        del source_id
        return self.latest.get(identity_key)

    def record_presence_observation(
        self,
        *,
        raw_item: RawItemModel,
        source_run_id: object,
        observed_at: object,
        content_hash_matched: bool,
    ) -> None:
        del source_run_id, observed_at
        self.presence.append(raw_item)
        self.presence_flags.append((raw_item, content_hash_matched))


def _filtering_service(
    *,
    share: float | None,
    families: tuple[str, ...] | None = ("SOFTWARE_ENGINEERING", "DATA"),
    floor: float = 0.30,
) -> tuple[AcquisitionService, _MemorySession, _ShareRepository]:
    source = SourceDefinitionModel(
        id=uuid4(), source_type="example", name="Example", enabled=True, configuration={}
    )
    session = _MemorySession()
    repository = _ShareRepository(source, share)
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((_MixedTitlesCollector(),)),
        repository=repository,  # type: ignore[arg-type]
        alerts=SourceAlertService(session),  # type: ignore[arg-type]
        target_role_families=(lambda: families) if families is not None else None,
        target_area_floor=floor,
    )
    return service, session, repository


def _persisted_ids(session: _MemorySession) -> set[str | None]:
    return {item.external_id for item in session.added if isinstance(item, RawItemModel)}


def _run_filtering(service: AcquisitionService):
    return asyncio.run(
        service.execute(
            service.repository.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
        )
    )


def test_run_records_target_area_counts() -> None:
    service, _, _ = _filtering_service(share=None)

    run = _run_filtering(service)

    assert run.items_target_area == 1
    assert run.items_off_target == 1


def test_source_above_floor_persists_every_item() -> None:
    service, session, _ = _filtering_service(share=0.5)

    run = _run_filtering(service)

    assert _persisted_ids(session) == {"eng", "sales", "unknown"}
    assert run.items_persisted == 3


def test_source_below_floor_skips_new_off_target_items() -> None:
    service, session, _ = _filtering_service(share=0.1)

    run = _run_filtering(service)

    assert _persisted_ids(session) == {"eng", "unknown"}
    assert run.items_persisted == 2
    assert run.items_skipped == 1
    assert run.items_off_target == 1


def test_filter_keeps_presence_of_existing_off_target_item() -> None:
    service, session, repository = _filtering_service(share=0.1)
    existing = RawItemModel(external_id="sales", item_metadata={})
    repository.known["external:sales"] = existing

    run = _run_filtering(service)

    assert existing in repository.presence
    assert "sales" not in _persisted_ids(session)
    assert run.items_skipped == 1


def test_filter_off_with_fewer_than_three_measured_runs() -> None:
    service, session, _ = _filtering_service(share=None)

    run = _run_filtering(service)

    assert _persisted_ids(session) == {"eng", "sales", "unknown"}
    assert run.items_skipped == 0


def test_filter_off_without_target_role_families() -> None:
    for families in ((), None):
        service, session, repository = _filtering_service(share=0.0, families=families)

        run = _run_filtering(service)

        assert _persisted_ids(session) == {"eng", "sales", "unknown"}
        assert run.items_target_area is None
        assert run.items_off_target is None
        assert repository.share_calls == 0


def test_floor_zero_disables_filter() -> None:
    service, session, repository = _filtering_service(share=0.0, floor=0.0)

    run = _run_filtering(service)

    assert _persisted_ids(session) == {"eng", "sales", "unknown"}
    assert repository.share_calls == 0
    assert run.items_off_target == 1


def test_filtered_run_is_still_complete() -> None:
    service, _, _ = _filtering_service(share=0.1)

    run = _run_filtering(service)

    assert run.items_seen == 3
    assert run.status == "SUCCEEDED"
    assert run.complete is True


def test_run_succeeds_with_skipped_items_and_valid_items() -> None:
    """F50-12.1: when a collector records only skipped items plus at least one valid item,
    the run succeeds with items_invalid == 0."""
    service, session = _service(_SkippedAndValidItemsCollector())

    run = asyncio.run(
        service.execute(
            service.repository.source.id,  # type: ignore[attr-defined]
            CollectionRequest(),
        )
    )

    assert run.status == "SUCCEEDED"
    assert run.error_code is None
    assert run.items_invalid == 0
    assert run.items_skipped == 1
    assert run.items_persisted == 1


def test_filter_confirms_presence_of_changed_off_target_item_without_new_evidence() -> None:
    service, session, repository = _filtering_service(share=0.1)
    stored = RawItemModel(external_id="sales", item_metadata={})
    # Content changed: the envelope lookup misses, the identity lookup finds the old row.
    repository.latest["external:sales"] = stored

    run = _run_filtering(service)

    assert "sales" not in _persisted_ids(session)
    assert [flag for row, flag in repository.presence_flags if row is stored] == [False]
    assert run.items_skipped == 1


def test_filter_records_nothing_for_a_truly_new_off_target_item() -> None:
    service, session, repository = _filtering_service(share=0.1)

    _run_filtering(service)

    assert "sales" not in _persisted_ids(session)
    assert all(row.external_id != "sales" for row, _ in repository.presence_flags)


class _NoneMetadataCollector(_Collector):
    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield CollectedItem(
            source_type=self.source_type,
            external_id="broken",
            title="Senior Backend Engineer",
            raw_payload={"id": "broken"},
            metadata=None,  # type: ignore[arg-type]
        )
        yield CollectedItem(
            source_type=self.source_type,
            external_id="valid",
            title="Senior Backend Engineer",
            raw_payload={"id": "valid"},
        )


def test_classification_failure_leaves_validity_to_persistence() -> None:
    service, session, _ = _filtering_service(share=None)
    service.registry = CollectorRegistry((_NoneMetadataCollector(),))

    run = _run_filtering(service)

    assert _persisted_ids(session) == {"valid"}
    assert run.items_invalid == 1
    assert run.items_persisted == 1


# F50-03: Workday detail flag and what the service hands the collector.


class _RequestCapturingCollector(_Collector):
    def __init__(self) -> None:
        self.requests: list[CollectionRequest] = []

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        self.requests.append(request)
        for item in ():
            yield item


def test_service_passes_target_role_families_on_the_request() -> None:
    service, _, _ = _filtering_service(share=None, families=("DATA", "SOFTWARE_ENGINEERING"))
    collector = _RequestCapturingCollector()
    service.registry = CollectorRegistry((collector,))

    _run_filtering(service)

    assert collector.requests[0].target_role_families == ("DATA", "SOFTWARE_ENGINEERING")
    assert collector.requests[0].fetch_detail is False


@pytest.mark.parametrize("value", ["true", 1, None])
def test_create_source_rejects_non_boolean_fetch_detail(value: object) -> None:
    session = _MemorySession()
    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((WorkdayCollector(client=httpx.AsyncClient()),)),
    )

    with pytest.raises(AcquisitionError) as refused:
        service.create_source(
            source_type="workday",
            name="Acme",
            configuration={
                "tenant_identifier": "acme/site",
                "api_region": "wd5",
                "fetch_detail": value,
            },
        )

    assert refused.value.code == AcquisitionErrorCode.INVALID_CONFIGURATION
    assert session.added == []


def _workday_detail_run(configuration: dict[str, object]):
    postings = [
        {
            "title": "Senior Backend Engineer",
            "externalPath": f"/job/Remote/Job-{number}_R{number}",
            "locationsText": "Remote",
        }
        for number in range(2)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"total": 2, "jobPostings": postings})
        return httpx.Response(
            200, json={"jobPostingInfo": {"jobDescription": "<p>Synthetic.</p>"}}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source_id = uuid4()
    synthetic_configuration = {
        "tenant_identifier": "acme/site",
        "api_region": "wd5",
        **configuration,
    }
    if configuration.get("fetch_detail") is True:
        # Synthetic approval only for this HTTP fake; never copied into source data.
        synthetic_configuration["detail_approval"] = {
            "source_id": str(source_id),
            "owner": "test fixture",
            "hostname": "acme.wd5.myworkdayjobs.com",
            "reviewed_at": datetime.now(UTC).date().isoformat(),
            "terms_reference": "synthetic fixture policy",
            "decision": "approved",
        }
    source = SourceDefinitionModel(
        id=source_id,
        source_type="workday",
        name="Acme",
        enabled=True,
        configuration=synthetic_configuration,
        rate_limit_policy={"minimum_interval_seconds": 5},
    )
    session = _MemorySession()
    repository = _ShareRepository(source, None)
    budget_calls: list[int] = []

    def record_usage(host: str, *, requests: int, **_: object) -> None:
        del host
        budget_calls.append(requests)

    repository.record_host_budget_usage = record_usage  # type: ignore[method-assign]
    sleeps: list[float] = []

    async def sleeper(delay: float) -> None:
        sleeps.append(delay)

    service = AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((WorkdayCollector(client=client, sleeper=sleeper),)),
        repository=repository,  # type: ignore[arg-type]
        alerts=SourceAlertService(session),  # type: ignore[arg-type]
        target_role_families=lambda: ("SOFTWARE_ENGINEERING",),
        sleeper=sleeper,
    )
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(client.aclose())
    return run, budget_calls, sleeps, session


def test_workday_detail_approval_is_source_local_and_requires_a_valid_nonfuture_date() -> None:
    source_id = uuid4()
    configuration = {
        "detail_approval": {
            "source_id": str(source_id),
            "owner": "operator",
            "hostname": "acme.wd5.myworkdayjobs.com",
            "decision": "approved",
            "terms_reference": "offline policy",
            "reviewed_at": "2026-10-05",
        }
    }

    assert _workday_detail_approval(configuration, source_id, "acme/site", "wd5") == (
        True,
        "approved",
    )
    assert _workday_detail_approval(configuration, uuid4(), "acme/site", "wd5")[0] is False

    configuration["detail_approval"]["reviewed_at"] = "2026-10-05-not-a-date"  # type: ignore[index]
    assert _workday_detail_approval(configuration, source_id, "acme/site", "wd5") == (
        False,
        "approval_invalid_date",
    )
    configuration["detail_approval"]["reviewed_at"] = (
        datetime.now(UTC).date() + timedelta(days=1)
    ).isoformat()  # type: ignore[index]
    assert _workday_detail_approval(configuration, source_id, "acme/site", "wd5") == (
        False,
        "approval_future_date",
    )


def test_workday_detail_requests_count_in_the_run_budget_and_wait_the_interval() -> None:
    run, budget_calls, sleeps, session = _workday_detail_run({"fetch_detail": True})

    assert run.items_seen == 2
    assert budget_calls == [3]  # one listing page + two details
    assert len(sleeps) == 2  # each detail waited out the 5 s interval
    stored = [item for item in session.added if isinstance(item, RawItemModel)]
    assert [row.item_metadata[COLLECTED_ITEM_V1_KEY]["description"] for row in stored] == [
        "<p>Synthetic.</p>"
    ] * 2


def test_workday_without_the_flag_makes_listing_requests_only() -> None:
    run, budget_calls, sleeps, _ = _workday_detail_run({})

    assert run.items_seen == 2
    assert budget_calls == [1]
    assert sleeps == []


# --- F51-13: inventory contracts, announced total, no-progress pagination ---------------


def test_adapter_inventory_contract_matrix() -> None:
    # The matrix is tied to the code: every contract describes a registered collector and
    # agrees with what that collector declares about pagination.
    registry = build_collector_registry(greenhouse_base_url="https://boards-api.greenhouse.io")
    for source_type, contract in INVENTORY_CONTRACTS.items():
        capabilities = registry.resolve(source_type).capabilities
        assert capabilities.pagination is (contract.pagination != PAGINATION_NONE), source_type

    assert INVENTORY_CONTRACTS["workday"].pagination == PAGINATION_OFFSET
    # Teamtailor and Workable have no pagination: no cursor is invented for them.
    for source_type in ("teamtailor", "workable"):
        assert INVENTORY_CONTRACTS[source_type].pagination == PAGINATION_NONE
        assert registry.resolve(source_type).capabilities.pagination is False
    # Of the three the card names, only Workday declares offset pagination.
    assert [
        name
        for name in ("workday", "teamtailor", "workable")
        if registry.resolve(name).capabilities.pagination
    ] == ["workday"]
    # A value nobody verified is stated as such, never filled in.
    assert INVENTORY_CONTRACTS["jobposting"].termination == "not_verifiable"


class _AnnouncingCollector(_Collector):
    def __init__(self, announced: int | None, items: int) -> None:
        self._announced = announced
        self._items = items

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        for index in range(self._items):
            yield CollectedItem(
                source_type=self.source_type,
                external_id=f"job-{index}",
                raw_payload={"title": f"Role {index}"},
            )
        if self._announced is not None:
            request.telemetry.record_items_announced(self._announced)


def test_missing_announced_total_is_not_zero() -> None:
    def execute(collector: _Collector):
        service, _ = _service(collector)
        return asyncio.run(
            service.execute(
                service.repository.source.id,  # type: ignore[attr-defined]
                CollectionRequest(mode=CollectionMode.DISCOVERY),
            )
        )

    unknown = execute(_AnnouncingCollector(announced=None, items=0))
    zero = execute(_AnnouncingCollector(announced=0, items=0))
    counted = execute(_AnnouncingCollector(announced=2, items=2))

    assert unknown.items_announced is None
    assert zero.items_announced == 0
    assert counted.items_announced == 2
    # Both an unknown and an explicit zero total are trusted as complete only on a
    # successful, unbounded run; neither is rewritten into the other.
    assert unknown.complete is True and zero.complete is True


def _workday_posting(identity: str) -> dict[str, str]:
    return {
        "title": f"Engineer {identity}",
        "externalPath": f"/job/Remote/Engineer-{identity}_R{identity}",
        "locationsText": "Remote",
    }


def _paginated_service(source_type: str, configuration: dict[str, object], collector):
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type=source_type,
        name="Paginated",
        enabled=True,
        configuration=configuration,
    )
    session = _MemorySession()
    return AcquisitionService(
        session,  # type: ignore[arg-type]
        registry=CollectorRegistry((collector,)),
        repository=_ShareRepository(source, None),  # type: ignore[arg-type]
        alerts=SourceAlertService(session),  # type: ignore[arg-type]
    ), source


@pytest.mark.parametrize("variant", ["same_page", "same_postings_reordered"])
def test_repeated_cursor_is_bounded_and_partial(variant: str) -> None:
    first = [_workday_posting(str(number)) for number in range(20)]
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = json.loads(request.content)["offset"]
        calls.append(offset)
        if offset == 0:
            return httpx.Response(200, json={"total": 100, "jobPostings": first})
        # The endpoint ignores the offset: it keeps answering with what it already sent.
        repeated = first if variant == "same_page" else list(reversed(first))
        return httpx.Response(200, json={"total": 0, "jobPostings": repeated})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service, source = _paginated_service(
        "workday",
        {"tenant_identifier": "acme/site", "api_region": "wd5"},
        WorkdayCollector(client=client),
    )
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(client.aclose())

    assert calls == [0, 20]  # bounded: it does not walk the announced 100
    assert run.status == "PARTIAL"
    assert run.complete is False
    assert run.items_persisted == 20
    assert run.error_code == AcquisitionErrorCode.PARSER_SCHEMA_CHANGED.value
    assert "without making progress" in (run.error_summary or "")


def test_lever_page_of_already_read_postings_is_no_progress() -> None:
    page = [
        {"id": f"job-{number}", "hostedUrl": f"https://jobs.lever.co/acme/{number}"}
        for number in range(100)
    ]
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["skip"])
        # Page two is a different, shorter slice made only of postings page one had.
        return httpx.Response(200, json=page if len(calls) == 1 else page[:40])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    service, source = _paginated_service(
        "lever", {"site_identifier": "acme"}, LeverCollector(client=client)
    )
    try:
        run = asyncio.run(
            service.execute(source.id, CollectionRequest(mode=CollectionMode.DISCOVERY))
        )
    finally:
        asyncio.run(client.aclose())

    assert calls == ["0", "100"]
    assert run.status == "PARTIAL"
    assert run.complete is False
