"""R55-C1 review: the analysis stage never starts a provider call the window cannot finish."""

from __future__ import annotations

import pytest

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.pipeline import Deadline, StageContext, StopSignal
from scripts import run_pipeline_once
from tests.backend.test_pipeline_analyze_stage import (
    _URL,
    FakeAdapter,
    FakeMatchingService,
    FakeQuotaGuard,
    _analyze,
    _patch,
    _stage,
)


def _enabled() -> Settings:
    return Settings(database_url=_URL, ai_enabled=True, groq_api_key="synthetic")


def test_a_window_without_time_for_one_call_defers_the_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_a: object, **_k: object) -> object:
        pytest.fail("no time for a call: nothing may be built or run")

    monkeypatch.setattr(run_pipeline_once, "build_analysis_adapter", fail)
    monkeypatch.setattr(run_pipeline_once, "analyze_pending", fail)
    # 25 s * (2 retries + 1) + 5 s margin = 80 s worst case; the window has 60 s left.
    context = StageContext("owner", Deadline(60), StopSignal())

    counts = _stage(_enabled()).run(context)

    assert counts.skipped == 1 and counts.failed == 0
    assert counts.metrics == {"deadline_deferred": 1}


def test_an_adapter_that_cannot_be_built_skips_the_stage_instead_of_failing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("provider setup failed")

    monkeypatch.setattr(run_pipeline_once, "build_analysis_adapter", boom)
    context = StageContext("owner", Deadline(600), StopSignal())

    counts = _stage(_enabled()).run(context)

    assert counts.skipped == 1 and counts.failed == 0
    assert counts.metrics == {"adapter_error": 1}


def test_analysis_declines_a_call_it_could_not_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeMatchingService(10)
    _patch(monkeypatch, service)
    left = [200.0]
    original = service.analyze

    async def analyze(assessment_id: object, adapter: object, **kwargs: object):
        left[0] -= 60.0  # each call costs a minute of the window
        return await original(assessment_id, adapter, **kwargs)

    service.analyze = analyze  # type: ignore[method-assign]

    result = _analyze(
        FakeAdapter(FakeQuotaGuard()),
        batch_size=10,
        time_left=lambda: left[0],
        min_call_seconds=80.0,
    )

    # 200 -> 140 -> 80 -> 20: the third call leaves 20 s, so a fourth is not started.
    assert len(service.analyzed) == 3
    assert result["completed"] == 3
    assert result["deadline_deferred"] == 7 and result["skipped"] == 7
    assert result["failed"] == 0 and result["stopped"] == 0


def test_no_time_at_all_defers_before_the_warm_up(monkeypatch: pytest.MonkeyPatch) -> None:
    service = FakeMatchingService(4)
    _patch(monkeypatch, service)

    class Adapter(FakeAdapter):
        async def warm_up(self, *, only_if_idle: bool = False) -> None:
            pytest.fail("warm-up is a provider call: not with the window about to close")

    result = _analyze(
        Adapter(FakeQuotaGuard()), batch_size=4, time_left=lambda: 10.0, min_call_seconds=80.0
    )

    assert service.analyzed == []
    assert result["skipped"] == 4 and result["deadline_deferred"] == 4
