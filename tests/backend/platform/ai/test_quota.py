"""Unit tests for the pure calculations `QuotaGuard` relies on.

Atomicity and persistence need real Postgres (`ON CONFLICT ... WHERE ... RETURNING`,
concurrent connections) and live in `tests/backend/test_ai_quota_integration.py`.
"""

from datetime import UTC, datetime

from opportunity_radar.platform.ai.providers.base import RateLimit
from opportunity_radar.platform.ai.quota import (
    _reported_remaining_for_window,
    day_window,
    effective_ceiling,
    minute_window,
)


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


def test_effective_ceiling_without_a_stored_ceiling_is_the_internal_limit() -> None:
    assert effective_ceiling(internal_limit=850, ceiling=None) == 850


def test_effective_ceiling_uses_the_smaller_of_internal_and_stored_values() -> None:
    assert effective_ceiling(internal_limit=850, ceiling=15) == 15


def test_effective_ceiling_above_internal_keeps_the_internal_limit() -> None:
    assert effective_ceiling(internal_limit=850, ceiling=10_000) == 850


def test_reported_day_headers_only_route_to_the_day_window() -> None:
    rate_limit = RateLimit(30, 8000, 29, 7900, 86400.0, 59.0)

    assert _reported_remaining_for_window(rate_limit, "day") == (29, None)
    assert _reported_remaining_for_window(rate_limit, "minute") == (None, 7900)


def test_reported_minute_headers_only_route_to_the_minute_window() -> None:
    rate_limit = RateLimit(30, 8000, 29, 7900, 60.0, 60.0)

    assert _reported_remaining_for_window(rate_limit, "minute") == (29, 7900)
    assert _reported_remaining_for_window(rate_limit, "day") == (None, None)


def test_reported_headers_with_unknown_reset_are_not_routed() -> None:
    rate_limit = RateLimit(30, 8000, 29, 7900, None, None)

    assert _reported_remaining_for_window(rate_limit, "minute") == (None, None)
    assert _reported_remaining_for_window(rate_limit, "day") == (None, None)
