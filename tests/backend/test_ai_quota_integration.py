"""Database-backed proof of F20-12: atomicity, persistence and window rollover."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.providers.base import RateLimit
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits, minute_window
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_MODEL = "openai/gpt-oss-120b"


def _engine() -> Engine:
    return create_database_engine(os.environ["DATABASE_URL"])


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_quota_usage"))


def _limits(
    *,
    minute_requests: int = 1000,
    minute_tokens: int = 1_000_000,
    day_requests: int = 1000,
    day_tokens: int = 1_000_000,
) -> QuotaLimits:
    return QuotaLimits(
        minute_requests=minute_requests,
        minute_tokens=minute_tokens,
        day_requests=day_requests,
        day_tokens=day_tokens,
    )


def test_concurrent_reservations_never_exceed_the_limit() -> None:
    engine = _engine()
    _reset(engine)
    guard = QuotaGuard(engine, _limits(minute_requests=10))

    def _try_reserve(_: int) -> bool:
        return guard.reserve(_MODEL, estimated_tokens=1) is not None

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(_try_reserve, range(20)))

    assert sum(results) == 10


def test_restart_does_not_reset_the_days_consumption() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(day_requests=5), now=lambda: now)
    for _ in range(5):
        assert guard.reserve(_MODEL, estimated_tokens=1) is not None
    assert guard.reserve(_MODEL, estimated_tokens=1) is None

    # A brand new guard, as a restarted worker would create, sees the same counters.
    restarted = QuotaGuard(engine, _limits(day_requests=5), now=lambda: now)
    assert restarted.reserve(_MODEL, estimated_tokens=1) is None


def test_minute_rollover_frees_the_minute_reservation_but_not_the_day() -> None:
    engine = _engine()
    _reset(engine)
    minute_one = datetime(2026, 9, 26, 12, 0, 30, tzinfo=UTC)
    minute_two = minute_one + timedelta(minutes=1)
    guard = QuotaGuard(engine, _limits(minute_requests=1, day_requests=1), now=lambda: minute_one)
    assert guard.reserve(_MODEL, estimated_tokens=1) is not None
    assert guard.reserve(_MODEL, estimated_tokens=1) is None  # minute exhausted

    guard_next_minute = QuotaGuard(
        engine, _limits(minute_requests=1, day_requests=1), now=lambda: minute_two
    )
    # Still the same UTC day, and the day limit (1) is already spent.
    assert guard_next_minute.reserve(_MODEL, estimated_tokens=1) is None


def test_next_available_at_guesses_the_minute_boundary_on_a_token_near_miss() -> None:
    """A reserve() failure from the estimate overshooting minute tokens (F20-21 baseline:

    observed live against Groq, where the stored total never reaches the ceiling because
    `_window_exhausted` only compares what is already stored) must not be reported as a
    day-long wait — that turns a 60s-away rollover into a multi-hour stall.
    """
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 30, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(minute_tokens=10), now=lambda: now)
    assert guard.reserve(_MODEL, estimated_tokens=8) is not None
    assert guard.reserve(_MODEL, estimated_tokens=5) is None  # 8 + 5 > 10, but 8 < 10

    expected = minute_window(now) + timedelta(minutes=1)
    assert guard.next_available_at(_MODEL) == expected


def test_day_rollover_frees_the_day_reservation() -> None:
    engine = _engine()
    _reset(engine)
    day_one = datetime(2026, 9, 26, 23, 59, 0, tzinfo=UTC)
    day_two = datetime(2026, 9, 27, 0, 0, 30, tzinfo=UTC)
    guard = QuotaGuard(
        engine, _limits(minute_requests=1, day_requests=1), now=lambda: day_one
    )
    assert guard.reserve(_MODEL, estimated_tokens=1) is not None

    guard_next_day = QuotaGuard(
        engine, _limits(minute_requests=1, day_requests=1), now=lambda: day_two
    )
    assert guard_next_day.reserve(_MODEL, estimated_tokens=1) is not None


def test_release_gives_back_the_reservation() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(minute_requests=1, day_requests=5), now=lambda: now)
    reservation = guard.reserve(_MODEL, estimated_tokens=42)
    assert reservation is not None
    assert guard.reserve(_MODEL, estimated_tokens=1) is None  # minute exhausted

    guard.release(reservation)

    assert guard.reserve(_MODEL, estimated_tokens=1) is not None


def test_settle_records_reported_remaining_and_adjusts_tokens() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(minute_tokens=1000, day_tokens=1000), now=lambda: now)
    reservation = guard.reserve(_MODEL, estimated_tokens=100)
    assert reservation is not None

    guard.settle(
        reservation,
        actual_tokens=60,
        rate_limit=RateLimit(
            limit_requests=30,
            limit_tokens=8000,
            remaining_requests=29,
            remaining_tokens=7940,
            reset_requests_seconds=59.0,
            reset_tokens_seconds=59.0,
        ),
    )

    rows = guard.snapshot()
    minute_row = next(row for row in rows if row["window_kind"] == "minute")
    day_row = next(row for row in rows if row["window_kind"] == "day")
    assert minute_row["tokens"] == 60  # 100 reserved, settled down to the real 60
    assert minute_row["remaining_requests_reported"] == 29
    assert minute_row["remaining_tokens_reported"] == 7940
    assert minute_row["requests_ceiling"] == 30
    assert minute_row["tokens_ceiling"] == 8000
    assert day_row["remaining_requests_reported"] is None
    assert day_row["remaining_tokens_reported"] is None


def test_settle_does_not_apply_a_day_remainder_to_the_minute_window() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(), now=lambda: now)
    reservation = guard.reserve(_MODEL, estimated_tokens=1)
    assert reservation is not None

    guard.settle(
        reservation,
        actual_tokens=1,
        rate_limit=RateLimit(1000, 1_000_000, 900, None, 86_400.0, None),
    )

    rows = guard.snapshot()
    minute_row = next(row for row in rows if row["window_kind"] == "minute")
    day_row = next(row for row in rows if row["window_kind"] == "day")
    assert minute_row["remaining_requests_reported"] is None
    assert minute_row["requests_ceiling"] is None
    assert day_row["remaining_requests_reported"] == 900
    assert day_row["requests_ceiling"] == day_row["requests"] + 900


def test_settle_does_not_apply_a_minute_token_remainder_to_the_day_window() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(), now=lambda: now)
    reservation = guard.reserve(_MODEL, estimated_tokens=1)
    assert reservation is not None

    guard.settle(
        reservation,
        actual_tokens=1,
        rate_limit=RateLimit(1000, 1_000_000, None, 900_000, None, 59.0),
    )

    rows = guard.snapshot()
    minute_row = next(row for row in rows if row["window_kind"] == "minute")
    day_row = next(row for row in rows if row["window_kind"] == "day")
    assert minute_row["remaining_tokens_reported"] == 900_000
    assert minute_row["tokens_ceiling"] == minute_row["tokens"] + 900_000
    assert day_row["remaining_tokens_reported"] is None
    assert day_row["tokens_ceiling"] is None


def test_a_provider_refill_never_raises_the_window_ceiling() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    guard = QuotaGuard(engine, _limits(minute_requests=100, day_requests=100), now=lambda: now)
    first = guard.reserve(_MODEL, estimated_tokens=1)
    assert first is not None
    guard.settle(
        first,
        actual_tokens=1,
        rate_limit=RateLimit(100, 100, 5, 5, 59.0, 59.0),
    )

    second = guard.reserve(_MODEL, estimated_tokens=1)
    third = guard.reserve(_MODEL, estimated_tokens=1)
    assert second is not None
    assert third is not None
    guard.settle(
        third,
        actual_tokens=1,
        rate_limit=RateLimit(100, 100, 20, 20, 59.0, 59.0),
    )

    minute_row = next(row for row in guard.snapshot() if row["window_kind"] == "minute")
    assert minute_row["requests_ceiling"] == 6
    assert minute_row["tokens_ceiling"] == 6
    for _ in range(3):
        assert guard.reserve(_MODEL, estimated_tokens=1) is not None
    assert guard.reserve(_MODEL, estimated_tokens=1) is None

