"""R55-C1: `analyze_pending` as the last stage of the finite window, inside the Groq free quota."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from uuid import uuid4

import pytest

from opportunity_radar import worker
from opportunity_radar.matching.analysis import AnalysisStatus
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.pipeline import Deadline, StageContext, StopSignal
from scripts import run_pipeline_once

_URL = "postgresql+psycopg://test:test@localhost/test"
_EMPTY = {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0}


class FakeQuotaGuard:
    """Stands in for `QuotaGuard`: a day balance flag and a request counter."""

    def __init__(self, *, balance: bool = True, requests_left: int = 10_000) -> None:
        self.balance = balance
        self.requests_left = requests_left
        self.balance_reads = 0

    def has_day_balance(self, _model: str, **_kwargs: object) -> bool:
        self.balance_reads += 1
        return self.balance

    def reserve(self, _model: str, _tokens: int, **_kwargs: object) -> object | None:
        if self.requests_left <= 0:
            return None
        self.requests_left -= 1
        return object()

    def release(self, _reservation: object) -> None:
        self.requests_left += 1


class FakeAdapter:
    """The fake AI client: no network; `analyze` below is what the service would call."""

    model = "openai/gpt-oss-120b"
    probe_tokens = 1_100

    def __init__(self, guard: FakeQuotaGuard) -> None:
        self.quota_guard = guard

    async def warm_up(self, *, only_if_idle: bool = False) -> None:
        del only_if_idle


class FakeMatchingService:
    def __init__(self, ids: int, *, status: str = AnalysisStatus.AI_COMPLETED.value) -> None:
        self.ids = [uuid4() for _ in range(ids)]
        self.status = status
        self.read_with: dict[str, object] = {}
        self.analyzed: list[object] = []

    def pending_analysis_ids(self, *, limit: int, **kwargs: object) -> list[object]:
        self.read_with = {"limit": limit, **kwargs}
        return self.ids[:limit]

    async def analyze(self, assessment_id: object, _adapter: object, **_kwargs: object):
        self.analyzed.append(assessment_id)
        return SimpleNamespace(status=self.status, metadata={})


def _patch(monkeypatch: pytest.MonkeyPatch, service: FakeMatchingService) -> None:
    monkeypatch.setattr(worker, "observe_job", lambda *_a, **_k: nullcontext("corr"))
    monkeypatch.setattr(
        worker, "Session", lambda _engine: nullcontext(SimpleNamespace(rollback=lambda: None))
    )
    monkeypatch.setattr(worker, "MatchingService", lambda _session, _owner: service)
    monkeypatch.setattr(worker, "is_reused_analysis", lambda _analysis: False)


def _analyze(adapter: FakeAdapter, **kwargs: object) -> dict[str, int]:
    return worker.analyze_pending(
        object(),  # type: ignore[arg-type]
        adapter,  # type: ignore[arg-type]
        owner_sub="worker-owner-synthetic",
        **kwargs,  # type: ignore[arg-type]
    )


def test_analysis_runs_for_the_pending_assessments(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeMatchingService(3)
    _patch(monkeypatch, service)

    result = _analyze(
        FakeAdapter(FakeQuotaGuard()),
        batch_size=31,
        eligible_verdicts=("HIGH_PRIORITY", "RECOMMENDED"),
    )

    assert result == {"input": 3, "completed": 3, "failed": 0, "skipped": 0, "stopped": 0}
    assert service.analyzed == service.ids
    assert service.read_with["limit"] == 31
    assert service.read_with["eligible_verdicts"] == ("HIGH_PRIORITY", "RECOMMENDED")


def test_one_window_never_analyses_more_than_its_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeMatchingService(200)
    _patch(monkeypatch, service)

    result = _analyze(FakeAdapter(FakeQuotaGuard()), batch_size=31)

    assert result["input"] == 31
    assert len(service.analyzed) == 31


def test_a_day_of_windows_stays_inside_the_free_quota() -> None:
    settings = Settings(database_url=_URL)
    cap = run_pipeline_once.analyze_window_cap(settings)
    ceiling = settings.ai_daily_requests_soft_limit - settings.ai_interactive_reserve_requests
    assert cap == ceiling // 24 == 31
    assert cap * settings.pipeline_analyze_windows_per_day <= ceiling < 1000


@pytest.mark.parametrize(
    ("soft_limit", "reserve", "windows", "expected"),
    [(850, 100, 24, 31), (1000, 0, 24, 41), (850, 100, 1, 750), (100, 99, 24, 1)],
)
def test_the_window_cap_follows_the_quota_settings(
    soft_limit: int, reserve: int, windows: int, expected: int
) -> None:
    settings = Settings(
        database_url=_URL,
        ai_daily_requests_soft_limit=soft_limit,
        ai_interactive_reserve_requests=reserve,
        pipeline_analyze_windows_per_day=windows,
    )
    assert run_pipeline_once.analyze_window_cap(settings) == expected


def test_an_exhausted_day_quota_skips_without_reading_the_queue_or_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeMatchingService(5)
    _patch(monkeypatch, service)
    guard = FakeQuotaGuard(balance=False)

    result = _analyze(FakeAdapter(guard), batch_size=31, daily_cap_fraction=0.8)

    assert result == _EMPTY
    assert guard.balance_reads == 1
    assert service.analyzed == []
    assert service.read_with == {}


def test_quota_running_out_mid_window_leaves_the_rest_pending_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The worker's request ceiling denies every probe: the day is spent.
    guard = FakeQuotaGuard(requests_left=0)
    service = FakeMatchingService(4)
    _patch(monkeypatch, service)
    result = _analyze(FakeAdapter(guard), batch_size=4, worker_requests_ceiling=750)

    assert result == {"input": 4, "completed": 0, "failed": 0, "skipped": 4, "stopped": 0}
    assert service.analyzed == []


def test_a_degraded_provider_is_a_skip_not_a_stage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeMatchingService(2, status=AnalysisStatus.AI_FAILED.value)
    _patch(monkeypatch, service)

    result = _analyze(FakeAdapter(FakeQuotaGuard()), batch_size=5)

    assert result == {"input": 2, "completed": 0, "failed": 0, "skipped": 2, "stopped": 0}


def test_the_window_deadline_stops_between_assessments(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeMatchingService(10)
    _patch(monkeypatch, service)

    result = _analyze(
        FakeAdapter(FakeQuotaGuard()),
        batch_size=10,
        stop_requested=lambda: len(service.analyzed) >= 3,
    )

    assert len(service.analyzed) == 3
    assert result["stopped"] == 1
    assert result["completed"] == 3


# ---- the stage in the pipeline ---------------------------------------------------------


def _context(owner: str = "owner") -> StageContext:
    return StageContext(owner, Deadline(600), StopSignal())


def _stage(settings: Settings, name: str = "analyze_pending"):
    stages = {stage.name: stage for stage in run_pipeline_once._stages(object(), settings)}
    return stages[name]


def test_analysis_is_the_last_stage_of_the_window() -> None:
    stages = run_pipeline_once._stages(object(), Settings(database_url=_URL))
    names = [stage.name for stage in stages]
    assert names == [
        "retention",
        "collect_enabled_sources",
        "normalize_opportunities",
        "evaluate_pending",
        "analyze_pending",
    ]


def test_the_stage_does_nothing_when_ai_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_a: object, **_k: object) -> object:
        pytest.fail("AI is disabled: no adapter and no analysis may be built")

    monkeypatch.setattr(run_pipeline_once, "build_analysis_adapter", fail)
    monkeypatch.setattr(run_pipeline_once, "analyze_pending", fail)

    counts = _stage(Settings(database_url=_URL, ai_enabled=False)).run(_context())

    assert counts.skipped == 1 and counts.completed == 0 and counts.failed == 0
    assert counts.metrics == {"ai_disabled": 1}


def test_the_stage_does_nothing_without_a_key_or_with_the_worker_switch_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_a: object, **_k: object) -> object:
        pytest.fail("no analysis may run")

    monkeypatch.setattr(run_pipeline_once, "build_analysis_adapter", fail)
    monkeypatch.setattr(run_pipeline_once, "analyze_pending", fail)

    no_key = Settings(database_url=_URL, ai_enabled=True, groq_api_key="")
    switched_off = Settings(
        database_url=_URL, ai_enabled=True, groq_api_key="synthetic", worker_analyze_enabled=False
    )
    assert _stage(no_key).run(_context()).skipped == 1
    assert _stage(switched_off).run(_context()).skipped == 1


def test_the_enabled_stage_passes_the_cap_verdicts_and_quota_to_the_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}
    adapter = object()
    monkeypatch.setattr(run_pipeline_once, "build_analysis_adapter", lambda *_a, **_k: adapter)

    def fake_analyze(engine: object, given: object, **kwargs: object) -> dict[str, int]:
        seen.update(kwargs, adapter_is_built_one=given is adapter)
        return {"input": 31, "completed": 30, "failed": 0, "skipped": 1, "stopped": 0}

    monkeypatch.setattr(run_pipeline_once, "analyze_pending", fake_analyze)
    settings = Settings(database_url=_URL, ai_enabled=True, groq_api_key="synthetic")

    counts = _stage(settings).run(_context("window-owner"))

    assert (counts.input, counts.completed, counts.skipped) == (31, 30, 1)
    assert seen["adapter_is_built_one"] is True
    assert seen["batch_size"] == 31
    assert seen["eligible_verdicts"] == ("HIGH_PRIORITY", "RECOMMENDED")
    assert seen["daily_cap_fraction"] == settings.worker_analyze_daily_cap_fraction
    assert seen["worker_requests_ceiling"] == 750
    assert seen["owner_sub"] == "window-owner"
    assert callable(seen["stop_requested"])


def test_a_stopped_window_does_not_start_the_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_a: object, **_k: object) -> object:
        pytest.fail("a stopped window must not build or run the analysis")

    monkeypatch.setattr(run_pipeline_once, "build_analysis_adapter", fail)
    stop = StopSignal()
    stop.set("interrupted")
    context = StageContext("owner", Deadline(600), stop)
    settings = Settings(database_url=_URL, ai_enabled=True, groq_api_key="synthetic")

    assert _stage(settings).run(context).stopped == 1
