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
from opportunity_radar.platform.ai.metrics import ai_metrics
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
