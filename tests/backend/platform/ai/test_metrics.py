"""Card F20-20: `ai_metrics` aggregates `platform.ai_call_record` plus live quota/breaker.

Database-backed, like `test_ai_quota_integration.py`: the percentile and rate math needs
real Postgres (`percentile_cont`), and the quota balance comes from the same persisted
table `QuotaGuard` uses.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.breaker import BreakerState, CircuitBreaker
from opportunity_radar.platform.ai.metrics import ai_metrics, ai_period_comparison
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits
from opportunity_radar.platform.ai.telemetry import AICallRecord, record_calls
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_MODEL = "openai/gpt-oss-120b"
NOW = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)


def _engine() -> Engine:
    return create_database_engine(os.environ["DATABASE_URL"])


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_call_record"))
        connection.execute(text("TRUNCATE platform.ai_quota_usage"))


def _record(**overrides: object) -> AICallRecord:
    base = dict(
        task="job_match",
        provider="groq",
        model=_MODEL,
        attempt=0,
        success=True,
        fallback_used=False,
        cache_hit=False,
        latency_ms=1000,
        prompt_tokens=500,
        completion_tokens=100,
        prompt_version="v2",
    )
    base.update(overrides)
    return AICallRecord(**base)  # type: ignore[arg-type]


def test_aggregates_success_rate_limit_fallback_and_invalid_json() -> None:
    engine = _engine()
    _reset(engine)
    record_calls(
        engine,
        [
            _record(latency_ms=1000),
            _record(latency_ms=2000),
            _record(success=False, error_kind="quota", http_status=429, latency_ms=None),
            _record(fallback_used=True, latency_ms=1500),
            _record(
                success=False,
                error_kind="invalid_output",
                latency_ms=800,
            ),
        ],
        now=NOW - timedelta(minutes=5),
    )

    report = ai_metrics(engine, state="enabled", guard=None, breaker=None, now=NOW)

    assert len(report.by_model) == 1
    model = report.by_model[0]
    assert model.model == _MODEL
    assert model.requests == 5
    assert model.success_rate == pytest.approx(3 / 5)
    assert model.rate_limited_rate == pytest.approx(1 / 5)
    assert model.fallback_rate == pytest.approx(1 / 5)
    assert model.json_valid_rate == pytest.approx(1 - 1 / 5)
    assert model.prompt_tokens == 5 * 500
    assert model.completion_tokens == 5 * 100


def test_cache_hit_rate_spans_every_model() -> None:
    engine = _engine()
    _reset(engine)
    record_calls(
        engine,
        [_record(cache_hit=True, attempt=0), _record(cache_hit=False)],
        now=NOW - timedelta(minutes=1),
    )

    report = ai_metrics(engine, state="enabled", guard=None, breaker=None, now=NOW)

    assert report.cache_hit_rate == pytest.approx(0.5)


def test_a_call_outside_the_window_is_excluded() -> None:
    engine = _engine()
    _reset(engine)
    record_calls(engine, [_record()], now=NOW - timedelta(hours=25))

    report = ai_metrics(engine, state="enabled", guard=None, breaker=None, now=NOW)

    assert report.by_model == ()


def test_breaker_and_quota_snapshots_are_reflected_per_model() -> None:
    engine = _engine()
    _reset(engine)
    record_calls(engine, [_record()], now=NOW - timedelta(minutes=1))
    guard = QuotaGuard(
        engine,
        QuotaLimits(
            minute_requests=100, minute_tokens=100_000, day_requests=850, day_tokens=170_000
        ),
        now=lambda: NOW,
    )
    guard.reserve(_MODEL, estimated_tokens=600)
    breaker = CircuitBreaker()
    breaker.record_failure(_MODEL)

    report = ai_metrics(
        engine,
        state="enabled",
        guard=guard,
        breaker=breaker,
        day_requests_limit=850,
        day_tokens_limit=170_000,
        now=NOW,
    )

    model = report.by_model[0]
    assert model.day_requests_used == 1
    assert model.day_tokens_used == 600
    assert model.breaker == BreakerState.CLOSED.value  # one failure never opens it


def test_ai_selective_metrics_include_denominators_and_gaps() -> None:
    engine = _engine()
    _reset(engine)
    baseline = (NOW - timedelta(days=2), NOW - timedelta(days=1))
    pilot = (NOW - timedelta(days=1), NOW)
    record_calls(
        engine,
        [
            _record(prompt_tokens=100, completion_tokens=50),
            _record(prompt_tokens=200, completion_tokens=40),
            _record(prompt_tokens=None, completion_tokens=None, success=False, error_kind="quota"),
            _record(cache_hit=True, prompt_tokens=None, completion_tokens=None),
            # Another task in the same window is a different cohort.
            _record(task="job_classification", prompt_tokens=999, completion_tokens=999),
        ],
        now=baseline[0] + timedelta(hours=1),
    )
    record_calls(
        engine,
        [
            _record(prompt_tokens=70, completion_tokens=30),
            _record(prompt_tokens=60, completion_tokens=20),
            _record(cache_hit=True, prompt_tokens=None, completion_tokens=None),
            _record(cache_hit=True, prompt_tokens=None, completion_tokens=None),
        ],
        now=pilot[0] + timedelta(hours=1),
    )

    report = ai_period_comparison(
        engine, task="job_match", baseline=baseline, pilot=pilot, prompt_version="v2"
    )

    assert (report.baseline.requests, report.baseline.cache_hits) == (3, 1)
    assert report.baseline.recorded_tokens == 390
    assert report.baseline.requests_without_tokens == 1
    assert (report.pilot.requests, report.pilot.cache_hits) == (2, 2)
    assert report.pilot.recorded_tokens == 180
    assert report.pilot.requests_without_tokens == 0
    # Useful results have no telemetry: named as a gap, never reported as zero. The pilot
    # period has all its tokens, so only the baseline's missing tokens are named.
    assert report.baseline.useful_results is None and report.pilot.useful_results is None
    assert report.gaps == ("useful_results", "baseline.tokens")
    # Absolute numbers only: every figure is a count, none a rate.
    for period in (report.baseline, report.pilot):
        assert all(
            value is None or type(value) is int
            for value in (
                period.requests,
                period.cache_hits,
                period.recorded_tokens,
                period.requests_without_tokens,
                period.useful_results,
            )
        )

    supplied = ai_period_comparison(
        engine,
        task="job_match",
        baseline=baseline,
        pilot=pilot,
        prompt_version="v2",
        baseline_useful_results=4,
        pilot_useful_results=5,
    )

    assert (supplied.baseline.useful_results, supplied.pilot.useful_results) == (4, 5)
    assert supplied.gaps == ("baseline.tokens",)
