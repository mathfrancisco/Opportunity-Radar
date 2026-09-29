"""Aggregated AI telemetry for the dashboard API, the Overview and the `doctor`.

SPEC 43 §8.5: requests per model, success rate, 429 rate, fallback rate, average and
p95 latency, tokens per day, JSON validity, quota balance, breaker state. Everything
here reads `platform.ai_call_record` (card F20-19) plus the live `QuotaGuard` and
`CircuitBreaker` a caller already holds — this module never opens its own provider
connection and never sees a prompt or a response body.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.breaker import BreakerState, CircuitBreaker
from opportunity_radar.platform.ai.quota import QuotaGuard, day_window
from opportunity_radar.platform.ai.telemetry import ai_call_record

DEFAULT_WINDOW_HOURS = 24


@dataclass(frozen=True, slots=True)
class ModelAIMetrics:
    model: str
    requests: int
    success_rate: float | None
    rate_limited_rate: float | None
    fallback_rate: float | None
    latency_ms_avg: float | None
    latency_ms_p95: float | None
    prompt_tokens: int
    completion_tokens: int
    json_valid_rate: float | None
    breaker: str
    day_requests_used: int
    day_requests_limit: int | None
    day_tokens_used: int
    day_tokens_limit: int | None

    @property
    def day_requests_remaining_ratio(self) -> float | None:
        """`None` when there is no configured limit to compare against."""
        if not self.day_requests_limit:
            return None
        return max(0.0, 1 - self.day_requests_used / self.day_requests_limit)

    @property
    def day_tokens_remaining_ratio(self) -> float | None:
        if not self.day_tokens_limit:
            return None
        return max(0.0, 1 - self.day_tokens_used / self.day_tokens_limit)


@dataclass(frozen=True, slots=True)
class AIMetricsReport:
    state: str
    window_hours: int
    by_model: tuple[ModelAIMetrics, ...]
    cache_hit_rate: float | None


def ai_metrics(
    engine: Engine,
    *,
    state: str,
    guard: QuotaGuard | None,
    breaker: CircuitBreaker | None,
    day_requests_limit: int | None = None,
    day_tokens_limit: int | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    now: datetime | None = None,
) -> AIMetricsReport:
    """`guard` and `breaker` are `None` when AI is disabled: an empty report follows."""
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=window_hours)
    rows = _aggregates(engine, since, reference)
    total_requests = sum(row.requests for row in rows)
    total_cache_hits = sum(row.cache_hits for row in rows)
    day_usage = _day_usage(guard, day_window(reference)) if guard is not None else {}
    breaker_snapshot = breaker.snapshot() if breaker is not None else {}

    by_model = tuple(
        ModelAIMetrics(
            model=row.model,
            requests=row.requests,
            success_rate=_rate(row.succeeded, row.requests),
            rate_limited_rate=_rate(row.rate_limited, row.requests),
            fallback_rate=_rate(row.fallback_used, row.requests),
            latency_ms_avg=_optional(row.latency_avg),
            latency_ms_p95=_optional(row.latency_p95),
            prompt_tokens=int(row.prompt_tokens or 0),
            completion_tokens=int(row.completion_tokens or 0),
            json_valid_rate=_json_valid_rate(row.invalid_output, row.requests),
            breaker=str(breaker_snapshot.get(row.model, BreakerState.CLOSED).value),
            day_requests_used=day_usage.get(row.model, {}).get("requests", 0),
            day_requests_limit=day_requests_limit,
            day_tokens_used=day_usage.get(row.model, {}).get("tokens", 0),
            day_tokens_limit=day_tokens_limit,
        )
        for row in rows
    )
    return AIMetricsReport(
        state=state,
        window_hours=window_hours,
        by_model=by_model,
        cache_hit_rate=_rate(total_cache_hits, total_requests),
    )


def _aggregates(engine: Engine, since: datetime, until: datetime) -> list[Any]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                sa.select(
                    ai_call_record.c.model.label("model"),
                    sa.func.count().label("requests"),
                    sa.func.count()
                    .filter(ai_call_record.c.success.is_(True))
                    .label("succeeded"),
                    sa.func.count()
                    .filter(ai_call_record.c.error_kind == "quota")
                    .label("rate_limited"),
                    sa.func.count()
                    .filter(ai_call_record.c.fallback_used.is_(True))
                    .label("fallback_used"),
                    sa.func.count()
                    .filter(ai_call_record.c.error_kind == "invalid_output")
                    .label("invalid_output"),
                    sa.func.count()
                    .filter(ai_call_record.c.cache_hit.is_(True))
                    .label("cache_hits"),
                    sa.func.avg(ai_call_record.c.latency_ms).label("latency_avg"),
                    sa.func.percentile_cont(0.95)
                    .within_group(ai_call_record.c.latency_ms)
                    .label("latency_p95"),
                    sa.func.sum(ai_call_record.c.prompt_tokens).label("prompt_tokens"),
                    sa.func.sum(ai_call_record.c.completion_tokens).label("completion_tokens"),
                )
                .where(
                    ai_call_record.c.created_at >= since,
                    ai_call_record.c.created_at <= until,
                )
                .group_by(ai_call_record.c.model)
                .order_by(sa.func.count().desc(), ai_call_record.c.model)
            ).all()
        )


def _day_usage(guard: QuotaGuard, today: datetime) -> dict[str, dict[str, int]]:
    usage: dict[str, dict[str, int]] = {}
    for row in guard.snapshot():
        if row["window_kind"] != "day" or row["window_start"] != today:
            continue
        usage[row["model"]] = {"requests": row["requests"], "tokens": row["tokens"]}
    return usage


def _rate(part: int, total: int) -> float | None:
    return part / total if total else None


def _json_valid_rate(invalid: int, total: int) -> float | None:
    if not total:
        return None
    return 1 - (invalid / total)


def _optional(value: Any) -> float | None:
    return None if value is None else float(value)


__all__ = ["DEFAULT_WINDOW_HOURS", "AIMetricsReport", "ModelAIMetrics", "ai_metrics"]
