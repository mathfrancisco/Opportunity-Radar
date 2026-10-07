"""F51-08: the collection pass works several hosts at once, never two runs on one host.

Every race is made deterministic with barriers and events, never with sleeps: a fake
`execute` blocks inside the "transport" until the test lets it go, so what is observed
(who is inside at the same time) is a property of the scheduler, not of timing.
"""

from __future__ import annotations

import logging
import threading
from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from opportunity_radar import worker
from opportunity_radar.platform.config import Settings

_TIMEOUT = 10.0
_DATABASE_URL = "postgresql+psycopg://test:test@localhost/test"
_NOON = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _tenant_source(name: str) -> SimpleNamespace:
    """A source on its own budget host (per-tenant type)."""
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        source_type="teamtailor",
        configuration={"company_identifier": name},
    )


def _shared_host_source(name: str) -> SimpleNamespace:
    """Every `ashby` source shares one provider host."""
    return SimpleNamespace(
        id=uuid4(), name=name, source_type="ashby", configuration={"board": name}
    )


class _Harness:
    """A fake acquisition service plus the observations a test asserts on."""

    def __init__(self, sources: list[SimpleNamespace]) -> None:
        self.sources = sources
        self.by_id: dict[UUID, SimpleNamespace] = {s.id: s for s in sources}
        self.lock = threading.Lock()
        self.started: list[str] = []
        self.finished: list[str] = []
        self.active: set[str] = set()
        self.peak = 0
        self.per_host_peak: dict[str, int] = {}
        self.active_by_host: dict[str, int] = {}
        self.threads: dict[str, int] = {}
        self.requests: dict[str, object] = {}
        self.factory_calls = 0
        self.behaviour = lambda source: SimpleNamespace(
            complete=False,
            status="SUCCEEDED",
            id=uuid4(),
            items_persisted=1,
            source=source.name,
        )
        self.on_enter = lambda source: None
        self.summaries: list[dict[str, int]] = []
        self.reconciled: list[object] = []

    def host_of(self, source: SimpleNamespace) -> str:
        return worker.budget_host_for_source(source.source_type, source.configuration)

    def service(self) -> SimpleNamespace:
        harness = self

        class Service:
            def list_collectable_sources(self) -> list[object]:
                return harness.sources

            def get_source(self, source_id: UUID) -> object:
                return harness.by_id[source_id]

            def scheduling_state(self, source: object, *, timezone: str) -> object:
                del timezone
                return source

            async def execute(self, source_id: UUID, request: object, **_kwargs: object):
                source = harness.by_id[source_id]
                host = harness.host_of(source)
                with harness.lock:
                    harness.started.append(source.name)
                    harness.active.add(source.name)
                    harness.peak = max(harness.peak, len(harness.active))
                    count = harness.active_by_host.get(host, 0) + 1
                    harness.active_by_host[host] = count
                    harness.per_host_peak[host] = max(harness.per_host_peak.get(host, 0), count)
                    harness.threads[source.name] = threading.get_ident()
                    harness.requests[source.name] = request
                try:
                    harness.on_enter(source)
                    return harness.behaviour(source)
                finally:
                    with harness.lock:
                        harness.active.discard(source.name)
                        harness.active_by_host[host] -= 1
                        harness.finished.append(source.name)

        def build(_session: object) -> SimpleNamespace:
            with self.lock:
                self.factory_calls += 1
            return Service()  # type: ignore[return-value]

        return build  # type: ignore[return-value]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(worker, "observe_job", lambda *_a, **_k: nullcontext("pass-1"))
        monkeypatch.setattr(
            worker, "Session", lambda _engine: nullcontext(SimpleNamespace(rollback=lambda: None))
        )
        monkeypatch.setattr(
            worker, "evaluate_gate", lambda *_a, **_k: worker.CollectionGate.DUE
        )
        monkeypatch.setattr(
            worker,
            "_scheduled_request_with_rotation",
            lambda _service, source, correlation: (
                SimpleNamespace(keywords=(), correlation_id=correlation, source=source.name),
                None,
                0,
            ),
        )
        monkeypatch.setattr(
            worker,
            "annotate_pass",
            lambda *_a, due_sources, **summary: self.summaries.append(summary),
        )
        harness = self

        class FakeOpportunityService:
            def __init__(self, _session: object) -> None:
                pass

            def normalize_run(self, run_id: object) -> None:
                harness.reconciled.append(("normalize", run_id))

            def reconcile_run_closures(self, run_id: object) -> None:
                harness.reconciled.append(("reconcile", run_id))

        monkeypatch.setattr(worker, "OpportunityService", FakeOpportunityService)

    def run(self, **kwargs: object) -> None:
        worker.collect_enabled_sources(
            object(),  # type: ignore[arg-type]
            service_factory=self.service(),  # type: ignore[arg-type]
            utc_clock=lambda: _NOON,
            **kwargs,  # type: ignore[arg-type]
        )


def _run_with_watchdog(action: object, release: threading.Event) -> None:
    """Run the pass; if a test bug deadlocks it, release the fakes so the suite never hangs."""
    timer = threading.Timer(30.0, release.set)
    timer.start()
    try:
        action()  # type: ignore[operator]
    finally:
        timer.cancel()


def test_two_sources_on_distinct_hosts_are_inside_the_transport_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [_tenant_source("a"), _tenant_source("b")]
    harness = _Harness(sources)
    harness.install(monkeypatch)
    barrier = threading.Barrier(2, timeout=_TIMEOUT)
    # Each fake HTTP call waits for the other: serial execution would break the barrier.
    harness.on_enter = lambda _source: barrier.wait()

    harness.run(host_concurrency=2)

    assert sorted(harness.finished) == ["a", "b"]
    assert harness.peak == 2
    assert harness.threads["a"] != harness.threads["b"]
    # Two runs, both under the pass's one correlation, both counted.
    assert {request.correlation_id for request in harness.requests.values()} == {"pass-1"}  # type: ignore[attr-defined]
    assert harness.summaries[0]["completed"] == 2


def test_n_hosts_with_concurrency_four_never_run_more_than_four_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [_tenant_source(f"s{index}") for index in range(7)]
    harness = _Harness(sources)
    harness.install(monkeypatch)
    release = threading.Event()
    four_inside = threading.Event()

    def on_enter(_source: SimpleNamespace) -> None:
        with harness.lock:
            if len(harness.active) == 4:
                four_inside.set()
        # The first four block until the test lets them go; later ones pass straight through.
        if not release.is_set():
            assert release.wait(_TIMEOUT)

    harness.on_enter = on_enter

    def open_gate() -> None:
        assert four_inside.wait(_TIMEOUT)
        release.set()

    gate = threading.Thread(target=open_gate)
    gate.start()
    _run_with_watchdog(lambda: harness.run(host_concurrency=4), release)
    gate.join(_TIMEOUT)

    assert len(harness.finished) == 7
    assert harness.peak == 4
    assert harness.summaries[0]["completed"] == 7


def test_two_sources_on_one_host_never_overlap_while_another_host_progresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first, second = _shared_host_source("first"), _shared_host_source("second")
    other = _tenant_source("other")
    harness = _Harness([first, second, other])
    harness.install(monkeypatch)
    release_first = threading.Event()
    other_done = threading.Event()

    def on_enter(source: SimpleNamespace) -> None:
        if source.name == "first":
            assert release_first.wait(_TIMEOUT)
        if source.name == "other":
            other_done.set()

    harness.on_enter = on_enter

    def open_gate() -> None:
        # The first source holds its host inside the transport until another host has run.
        assert other_done.wait(_TIMEOUT)
        with harness.lock:
            assert "second" not in harness.started
        release_first.set()

    gate = threading.Thread(target=open_gate)
    gate.start()
    _run_with_watchdog(lambda: harness.run(host_concurrency=4), release_first)
    gate.join(_TIMEOUT)

    assert harness.per_host_peak[harness.host_of(first)] == 1
    assert harness.started.index("first") < harness.started.index("second")
    assert harness.finished.index("first") < harness.finished.index("second")
    assert sorted(harness.finished) == ["first", "other", "second"]


def test_concurrency_one_is_the_serial_pass_in_source_order_on_one_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [
        _tenant_source("a"),
        _shared_host_source("b"),
        _tenant_source("c"),
        _shared_host_source("d"),
    ]
    harness = _Harness(sources)
    harness.install(monkeypatch)
    caller = threading.get_ident()

    harness.run(host_concurrency=1)

    assert harness.started == ["a", "b", "c", "d"]
    assert harness.finished == ["a", "b", "c", "d"]
    assert harness.peak == 1
    assert set(harness.threads.values()) == {caller}
    assert harness.factory_calls == 1
    assert harness.summaries == [
        {"completed": 4, "failed": 0, "skipped": 0, "blocked": 0}
    ]


def test_the_default_host_concurrency_of_the_function_is_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness([_tenant_source("a"), _tenant_source("b")])
    harness.install(monkeypatch)

    harness.run()

    assert harness.factory_calls == 1
    assert harness.started == ["a", "b"]


def test_a_failing_run_does_not_cancel_or_fail_the_other_hosts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sources = [_tenant_source("boom"), _tenant_source("ok1"), _tenant_source("ok2")]
    harness = _Harness(sources)
    harness.install(monkeypatch)
    barrier = threading.Barrier(3, timeout=_TIMEOUT)

    def behaviour(source: SimpleNamespace) -> object:
        barrier.wait()  # all three are in flight together before any of them ends
        if source.name == "boom":
            raise RuntimeError("provider exploded")
        return SimpleNamespace(
            complete=False, status="SUCCEEDED", id=uuid4(), items_persisted=1
        )

    harness.behaviour = behaviour

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        harness.run(host_concurrency=3)

    assert sorted(harness.finished) == ["boom", "ok1", "ok2"]
    assert harness.summaries == [{"completed": 2, "failed": 1, "skipped": 0, "blocked": 0}]
    assert any(record.message == "scheduled collection failed" for record in caplog.records)


def test_a_run_ending_failed_is_counted_failed_and_the_batch_log_keeps_its_meaning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    harness = _Harness([_tenant_source("bad"), _tenant_source("good")])
    harness.install(monkeypatch)
    harness.behaviour = lambda source: SimpleNamespace(
        complete=False,
        status="FAILED" if source.name == "bad" else "SUCCEEDED",
        id=uuid4(),
        items_persisted=0,
    )

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        harness.run(host_concurrency=2)

    batch = [r for r in caplog.records if r.message == "collection batch finished"]
    assert len(batch) == 1
    assert (batch[0].completed, batch[0].failed, batch[0].skipped, batch[0].blocked) == (
        1,
        1,
        0,
        0,
    )


def test_the_pass_deadline_starts_no_new_host_once_it_has_passed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    sources = [_tenant_source("a"), _tenant_source("b"), _tenant_source("late")]
    harness = _Harness(sources)
    harness.install(monkeypatch)
    clock = [0.0]
    inside = threading.Barrier(2, timeout=_TIMEOUT)

    def on_enter(source: SimpleNamespace) -> None:
        if source.name != "late":
            inside.wait()  # both pool threads are busy; "late" is still queued
            clock[0] = 5.0  # the pass deadline (1s) is over before either one ends

    harness.on_enter = on_enter

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        harness.run(
            host_concurrency=2,
            pass_deadline_seconds=1.0,
            monotonic_clock=lambda: clock[0],
        )

    assert sorted(harness.started) == ["a", "b"]
    assert [r.reason for r in caplog.records if r.message == "scheduled collection skipped"] == [
        "pass_deadline"
    ]
    assert harness.summaries == [{"completed": 2, "failed": 0, "skipped": 1, "blocked": 0}]


def test_in_flight_runs_get_the_remaining_pass_time_as_their_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _Harness([_tenant_source("a")])
    harness.install(monkeypatch)
    seen: list[object] = []

    class Service:
        def list_collectable_sources(self) -> list[object]:
            return harness.sources

        def get_source(self, source_id: UUID) -> object:
            return harness.by_id[source_id]

        def scheduling_state(self, source: object, *, timezone: str) -> object:
            del timezone
            return source

        async def execute(self, _source_id: UUID, _request: object, **kwargs: object):
            seen.append(kwargs["deadline_seconds"])
            return SimpleNamespace(complete=False, status="PARTIAL", id=uuid4(), items_persisted=0)

    ticks = iter([0.0])

    def clock() -> float:
        return next(ticks, 40.0)  # the pass starts at 0; 40s have gone by when the run starts

    worker.collect_enabled_sources(
        object(),  # type: ignore[arg-type]
        service_factory=lambda _s: Service(),  # type: ignore[arg-type,return-value]
        utc_clock=lambda: _NOON,
        host_concurrency=2,
        source_deadline_seconds=600.0,
        pass_deadline_seconds=100.0,
        monotonic_clock=clock,
    )

    assert seen == [60.0]


def test_a_partial_run_keeps_presence_while_a_complete_run_on_another_host_reconciles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timed_out, complete = _tenant_source("timeout"), _tenant_source("complete")
    harness = _Harness([timed_out, complete])
    harness.install(monkeypatch)
    run_ids = {"timeout": uuid4(), "complete": uuid4()}
    both_in = threading.Barrier(2, timeout=_TIMEOUT)

    def behaviour(source: SimpleNamespace) -> object:
        both_in.wait()
        return SimpleNamespace(
            complete=source.name == "complete",
            status="SUCCEEDED" if source.name == "complete" else "PARTIAL",
            id=run_ids[source.name],
            items_persisted=1,
        )

    harness.behaviour = behaviour

    harness.run(host_concurrency=2)

    # Only the complete inventory is normalized and reconciled (closure); the partial one is not.
    assert sorted(harness.reconciled, key=str) == sorted(
        [("normalize", run_ids["complete"]), ("reconcile", run_ids["complete"])], key=str
    )
    assert harness.summaries == [{"completed": 2, "failed": 0, "skipped": 0, "blocked": 0}]


def test_a_source_claimed_elsewhere_is_skipped_without_costing_the_other_hosts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    held, free = _tenant_source("held"), _tenant_source("free")
    harness = _Harness([held, free])
    harness.install(monkeypatch)

    def behaviour(source: SimpleNamespace) -> object:
        if source.name == "held":
            raise worker.SourceClaimedElsewhereError(source.id)
        return SimpleNamespace(complete=False, status="SUCCEEDED", id=uuid4(), items_persisted=1)

    harness.behaviour = behaviour

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        harness.run(host_concurrency=2)

    assert [r.reason for r in caplog.records if r.message == "scheduled collection skipped"] == [
        "claimed_elsewhere"
    ]
    assert harness.summaries == [{"completed": 1, "failed": 0, "skipped": 1, "blocked": 0}]


def test_a_host_that_cannot_start_fails_only_its_own_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = [_shared_host_source("x1"), _shared_host_source("x2"), _tenant_source("fine")]
    harness = _Harness(sources)
    harness.install(monkeypatch)
    build = harness.service()
    builds: list[int] = []
    gate = threading.Lock()

    def flaky_factory(session: object) -> object:
        with gate:
            builds.append(1)
            nth = len(builds)
        if nth == 2:  # the first call lists the sources; the second is the first host group
            raise RuntimeError("no service for this host")
        return build(session)

    worker.collect_enabled_sources(
        object(),  # type: ignore[arg-type]
        service_factory=flaky_factory,  # type: ignore[arg-type]
        utc_clock=lambda: _NOON,
        host_concurrency=1 + 1,
    )

    # One host group failed to start (two sources if it was the shared host, one otherwise);
    # the other host ran regardless, and every source ended in exactly one bucket.
    summary = harness.summaries[0]
    assert sum(summary.values()) == 3
    assert summary["failed"] in {1, 2}
    assert summary["completed"] == 3 - summary["failed"]


def test_the_host_concurrency_setting_defaults_to_four_and_rejects_zero() -> None:
    assert Settings(database_url=_DATABASE_URL).collection_host_concurrency == 4
    with pytest.raises(ValueError):
        Settings(database_url=_DATABASE_URL, collection_host_concurrency=0)


def test_the_scheduler_passes_the_host_concurrency_to_the_collection_job() -> None:
    scheduler = worker.build_scheduler(
        Settings(database_url=_DATABASE_URL, collection_host_concurrency=1)
    )
    job = scheduler.get_job("collect-enabled-sources")

    assert job is not None
    assert job.kwargs["host_concurrency"] == 1
