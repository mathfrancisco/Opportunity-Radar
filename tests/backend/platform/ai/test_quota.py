"""Unit tests for the pure calculations `QuotaGuard` relies on.

Atomicity and persistence need real Postgres (`ON CONFLICT ... WHERE ... RETURNING`,
concurrent connections) and live in `tests/backend/test_ai_quota_integration.py`.
"""

from datetime import UTC, datetime

from opportunity_radar.platform.ai.quota import day_window, effective_limit, minute_window


def test_minute_window_truncates_to_the_minute() -> None:
    moment = datetime(2026, 9, 26, 14, 37, 42, 123456, tzinfo=UTC)

    assert minute_window(moment) == datetime(2026, 9, 26, 14, 37, 0, tzinfo=UTC)


def test_day_window_truncates_to_the_utc_day() -> None:
    moment = datetime(2026, 9, 26, 23, 59, 59, tzinfo=UTC)

    assert day_window(moment) == datetime(2026, 9, 26, 0, 0, 0, tzinfo=UTC)


def test_minute_window_normalizes_a_non_utc_timezone() -> None:
    from datetime import timedelta, timezone

    moment = datetime(2026, 9, 26, 11, 37, 0, tzinfo=timezone(timedelta(hours=-3)))

    assert minute_window(moment) == datetime(2026, 9, 26, 14, 37, 0, tzinfo=UTC)


def test_effective_limit_without_a_reported_value_is_the_internal_limit() -> None:
    assert effective_limit(internal_limit=850, remaining_reported=None, already_used=10) == 850


def test_effective_limit_uses_the_smaller_of_internal_and_reported() -> None:
    # Provider reports 5 left after 10 already counted this window => ceiling is 15,
    # below the internal 850.
    assert effective_limit(internal_limit=850, remaining_reported=5, already_used=10) == 15


def test_effective_limit_reported_above_internal_keeps_the_internal_limit() -> None:
    assert effective_limit(internal_limit=850, remaining_reported=10_000, already_used=0) == 850
