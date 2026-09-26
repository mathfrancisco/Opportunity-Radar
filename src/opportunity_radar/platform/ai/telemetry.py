"""Per-call telemetry for the Groq adapter, without PII (SPEC 43, section 8.5).

`platform.ai_call_record` holds one row per HTTP call the router made — not one row per
analysis (`matching.MatchAnalysisModel` already covers that). Retry and fallback can turn
a single analysis into several calls; this table is what lets `platform.ai.metrics`
answer "how often does model X get rate limited" without scanning application rows.

Never write here: prompt text, the model's answer, the candidate's profile, or the API
key. Only shape — task, provider, model, attempt, outcome class, timing, token counts.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.engine import Engine

if TYPE_CHECKING:
    from opportunity_radar.platform.ai.router import Attempt

SCHEMA = "platform"
TABLE_NAME = "ai_call_record"

_METADATA = sa.MetaData(schema=SCHEMA)

ai_call_record = sa.Table(
    TABLE_NAME,
    _METADATA,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("task", sa.String(32), nullable=False),
    sa.Column("provider", sa.String(32), nullable=False),
    sa.Column("model", sa.String(128), nullable=False),
    sa.Column("attempt", sa.SmallInteger, nullable=False),
    sa.Column("success", sa.Boolean, nullable=False),
    sa.Column("error_kind", sa.String(32)),
    sa.Column("http_status", sa.SmallInteger),
    sa.Column("latency_ms", sa.Integer),
    sa.Column("prompt_tokens", sa.Integer),
    sa.Column("completion_tokens", sa.Integer),
    sa.Column("fallback_used", sa.Boolean, nullable=False),
    sa.Column("cache_hit", sa.Boolean, nullable=False),
    sa.Column("prompt_version", sa.String(32)),
)


@dataclass(frozen=True, slots=True)
class AICallRecord:
    """One HTTP call to a provider, or one cache reuse (`cache_hit=True`).

    `id` and `created_at` are assigned at insert time, not here: a record is a plain
    fact about a call, with no identity of its own until it is persisted.
    """

    task: str
    provider: str
    model: str
    attempt: int
    success: bool
    fallback_used: bool
    cache_hit: bool
    error_kind: str | None = None
    http_status: int | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_version: str | None = None


def records_from_attempts(
    attempts: Sequence["Attempt"],
    *,
    task: str,
    provider: str,
    fallback_used: bool,
    prompt_version: str | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
) -> list[AICallRecord]:
    """One `AICallRecord` per `AIRouter.run` attempt — success or not (card F20-19).

    `AIRouter.Attempt` never carries a response's token usage, so only the attempt that
    matches `attempts[-1]` when it succeeded gets `prompt_tokens`/`completion_tokens`;
    every other attempt (a retry, a repair, a model the fallback skipped past) records
    `None` for both, because no usage was billed for it.
    """
    last_index = len(attempts) - 1
    records = []
    for index, attempt in enumerate(attempts):
        succeeded = attempt.error_kind is None
        is_final_success = succeeded and index == last_index
        records.append(
            AICallRecord(
                task=task,
                provider=provider,
                model=attempt.model,
                attempt=attempt.attempt,
                success=succeeded,
                error_kind=attempt.error_kind.value if attempt.error_kind else None,
                http_status=attempt.http_status,
                latency_ms=attempt.latency_ms,
                prompt_tokens=prompt_tokens if is_final_success else None,
                completion_tokens=completion_tokens if is_final_success else None,
                fallback_used=fallback_used,
                cache_hit=False,
                prompt_version=prompt_version,
            )
        )
    return records


def record_calls(
    engine: Engine, records: Sequence[AICallRecord], *, now: datetime | None = None
) -> None:
    """Insert every record in one batch. A no-op for an empty sequence."""
    if not records:
        return
    moment = now or datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "created_at": moment,
            "task": record.task,
            "provider": record.provider,
            "model": record.model,
            "attempt": record.attempt,
            "success": record.success,
            "error_kind": record.error_kind,
            "http_status": record.http_status,
            "latency_ms": record.latency_ms,
            "prompt_tokens": record.prompt_tokens,
            "completion_tokens": record.completion_tokens,
            "fallback_used": record.fallback_used,
            "cache_hit": record.cache_hit,
            "prompt_version": record.prompt_version,
        }
        for record in records
    ]
    with engine.begin() as connection:
        connection.execute(sa.insert(ai_call_record), rows)


def purge_older_than(
    engine: Engine,
    days: int,
    *,
    batch_size: int = 1000,
    now: datetime | None = None,
) -> int:
    """Delete rows older than `days`, in batches. Returns the number of rows removed."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    total = 0
    while True:
        with engine.begin() as connection:
            selected = sa.select(ai_call_record.c.id).where(
                ai_call_record.c.created_at < cutoff
            ).limit(batch_size)
            result = connection.execute(
                sa.delete(ai_call_record).where(ai_call_record.c.id.in_(selected))
            )
            deleted = result.rowcount or 0
        total += deleted
        if deleted < batch_size:
            break
    return total


__all__ = [
    "SCHEMA",
    "TABLE_NAME",
    "AICallRecord",
    "ai_call_record",
    "purge_older_than",
    "record_calls",
    "records_from_attempts",
]
