"""Persistent, per-model quota reservation (SPEC 43, sections 4.1 and 7.1).

Counters live in `platform.ai_quota_usage` so the API and the worker — which may call
Groq at the same time, and which may restart — share the same count instead of each
keeping its own in memory. The guard itself is synchronous (the worker's `Engine` is
synchronous); the async router calls it through `asyncio.to_thread`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.providers.base import RateLimit

SCHEMA = "platform"
TABLE_NAME = "ai_quota_usage"

_METADATA = sa.MetaData(schema=SCHEMA)

ai_quota_usage = sa.Table(
    TABLE_NAME,
    _METADATA,
    sa.Column("model", sa.String(128), primary_key=True),
    sa.Column("window_kind", sa.String(8), primary_key=True),
    sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
    sa.Column("requests", sa.Integer, nullable=False, server_default="0"),
    sa.Column("tokens", sa.Integer, nullable=False, server_default="0"),
    sa.Column("remaining_requests_reported", sa.Integer),
    sa.Column("remaining_tokens_reported", sa.Integer),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class QuotaLimits:
    minute_requests: int
    minute_tokens: int
    day_requests: int
    day_tokens: int


@dataclass(frozen=True)
class Reservation:
    model: str
    minute_start: datetime
    day_start: datetime
    tokens: int


class _WindowExhausted(Exception):
    """Raised inside a transaction to roll back a reservation that only half fit."""


def minute_window(now: datetime) -> datetime:
    """The `minute` window a moment falls in, truncated to the minute (UTC)."""
    return now.astimezone(UTC).replace(second=0, microsecond=0)


def day_window(now: datetime) -> datetime:
    """The `day` window a moment falls in, truncated to the day (UTC)."""
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def effective_limit(internal_limit: int, remaining_reported: int | None, already_used: int) -> int:
    """The smaller of the configured soft limit and what the provider last reported.

    `remaining_reported` is "how many are left", so it is turned back into an absolute
    ceiling by adding what this window already used before that header arrived.
    """
    if remaining_reported is None:
        return internal_limit
    return min(internal_limit, remaining_reported + already_used)


_RESERVE_SQL = text(
    f"""
    INSERT INTO {SCHEMA}.{TABLE_NAME}
        (model, window_kind, window_start, requests, tokens, updated_at)
    VALUES (:model, :window_kind, :window_start, 1, :tokens, now())
    ON CONFLICT (model, window_kind, window_start) DO UPDATE SET
        requests = {TABLE_NAME}.requests + 1,
        tokens = {TABLE_NAME}.tokens + EXCLUDED.tokens,
        updated_at = now()
    WHERE
        {TABLE_NAME}.requests + 1 <= CASE
            WHEN {TABLE_NAME}.remaining_requests_reported IS NULL THEN :requests_limit
            ELSE LEAST(
                :requests_limit,
                {TABLE_NAME}.remaining_requests_reported + {TABLE_NAME}.requests
            )
        END
        AND {TABLE_NAME}.tokens + :tokens <= CASE
            WHEN {TABLE_NAME}.remaining_tokens_reported IS NULL THEN :tokens_limit
            ELSE LEAST(:tokens_limit, {TABLE_NAME}.remaining_tokens_reported + {TABLE_NAME}.tokens)
        END
    RETURNING requests, tokens
    """
)

_SELECT_SQL = text(
    f"""
    SELECT requests, tokens, remaining_requests_reported, remaining_tokens_reported
    FROM {SCHEMA}.{TABLE_NAME}
    WHERE model = :model AND window_kind = :window_kind AND window_start = :window_start
    """
)

_SETTLE_SQL = text(
    f"""
    UPDATE {SCHEMA}.{TABLE_NAME}
    SET tokens = GREATEST(0, tokens + :token_delta),
        remaining_requests_reported = COALESCE(:remaining_requests, remaining_requests_reported),
        remaining_tokens_reported = COALESCE(:remaining_tokens, remaining_tokens_reported),
        updated_at = now()
    WHERE model = :model AND window_kind = :window_kind AND window_start = :window_start
    """
)

_RELEASE_SQL = text(
    f"""
    UPDATE {SCHEMA}.{TABLE_NAME}
    SET requests = GREATEST(0, requests - 1),
        tokens = GREATEST(0, tokens - :tokens),
        updated_at = now()
    WHERE model = :model AND window_kind = :window_kind AND window_start = :window_start
    """
)


class QuotaGuard:
    """Reserves quota before a call and settles it after, atomically, in Postgres."""

    def __init__(
        self,
        engine: Engine,
        limits: QuotaLimits,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._engine = engine
        self._limits = limits
        self._now = now

    def _reserve_window(
        self,
        connection: Any,
        model: str,
        window_kind: str,
        window_start: datetime,
        tokens: int,
        requests_limit: int,
        tokens_limit: int,
    ) -> bool:
        result = connection.execute(
            _RESERVE_SQL,
            {
                "model": model,
                "window_kind": window_kind,
                "window_start": window_start,
                "tokens": tokens,
                "requests_limit": requests_limit,
                "tokens_limit": tokens_limit,
            },
        )
        return result.first() is not None

    def reserve(self, model: str, estimated_tokens: int) -> Reservation | None:
        """`None` = no balance in the minute or the day window. Atomic across both."""
        now = self._now()
        minute_start = minute_window(now)
        day_start = day_window(now)
        try:
            with self._engine.begin() as connection:
                if not self._reserve_window(
                    connection,
                    model,
                    "minute",
                    minute_start,
                    estimated_tokens,
                    self._limits.minute_requests,
                    self._limits.minute_tokens,
                ):
                    raise _WindowExhausted
                if not self._reserve_window(
                    connection,
                    model,
                    "day",
                    day_start,
                    estimated_tokens,
                    self._limits.day_requests,
                    self._limits.day_tokens,
                ):
                    raise _WindowExhausted
        except _WindowExhausted:
            return None
        return Reservation(
            model=model, minute_start=minute_start, day_start=day_start, tokens=estimated_tokens
        )

    def settle(
        self,
        reservation: Reservation,
        actual_tokens: int | None,
        rate_limit: RateLimit | None,
    ) -> None:
        token_delta = 0 if actual_tokens is None else actual_tokens - reservation.tokens
        remaining_requests = rate_limit.remaining_requests if rate_limit else None
        remaining_tokens = rate_limit.remaining_tokens if rate_limit else None
        with self._engine.begin() as connection:
            for window_kind, window_start in (
                ("minute", reservation.minute_start),
                ("day", reservation.day_start),
            ):
                connection.execute(
                    _SETTLE_SQL,
                    {
                        "model": reservation.model,
                        "window_kind": window_kind,
                        "window_start": window_start,
                        "token_delta": token_delta,
                        "remaining_requests": remaining_requests,
                        "remaining_tokens": remaining_tokens,
                    },
                )

    def release(self, reservation: Reservation) -> None:
        """Give back one request and the reserved tokens (a call that never consumed)."""
        with self._engine.begin() as connection:
            for window_kind, window_start in (
                ("minute", reservation.minute_start),
                ("day", reservation.day_start),
            ):
                connection.execute(
                    _RELEASE_SQL,
                    {
                        "model": reservation.model,
                        "window_kind": window_kind,
                        "window_start": window_start,
                        "tokens": reservation.tokens,
                    },
                )

    def next_available_at(self, model: str) -> datetime:
        """Best-guess time a reservation might succeed again: the next window boundary."""
        now = self._now()
        minute_start = minute_window(now)
        day_start = day_window(now)
        with self._engine.connect() as connection:
            minute_row = (
                connection.execute(
                    _SELECT_SQL,
                    {"model": model, "window_kind": "minute", "window_start": minute_start},
                )
                .mappings()
                .first()
            )
            day_row = (
                connection.execute(
                    _SELECT_SQL,
                    {"model": model, "window_kind": "day", "window_start": day_start},
                )
                .mappings()
                .first()
            )
        if minute_row is not None and self._window_exhausted(
            minute_row, self._limits.minute_requests, self._limits.minute_tokens
        ):
            return minute_start + timedelta(minutes=1)
        if day_row is not None and self._window_exhausted(
            day_row, self._limits.day_requests, self._limits.day_tokens
        ):
            return day_start + timedelta(days=1)
        # Neither window looked exhausted from here; a concurrent reservation likely
        # filled it between the check and this read. The day boundary is the safer of
        # the two guesses to wait for.
        return day_start + timedelta(days=1)

    def _window_exhausted(
        self, row: Any, requests_limit: int, tokens_limit: int
    ) -> bool:
        limit = effective_limit(
            requests_limit, row["remaining_requests_reported"], row["requests"]
        )
        token_limit = effective_limit(
            tokens_limit, row["remaining_tokens_reported"], row["tokens"]
        )
        return bool(row["requests"] >= limit or row["tokens"] >= token_limit)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                sa.select(ai_quota_usage).order_by(
                    ai_quota_usage.c.model, ai_quota_usage.c.window_kind
                )
            ).mappings()
            return [dict(row) for row in rows]


__all__ = [
    "SCHEMA",
    "TABLE_NAME",
    "QuotaGuard",
    "QuotaLimits",
    "Reservation",
    "ai_quota_usage",
    "day_window",
    "effective_limit",
    "minute_window",
]
