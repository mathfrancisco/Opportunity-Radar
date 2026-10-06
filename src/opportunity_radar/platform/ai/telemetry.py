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
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.providers.tokenharbor import MODEL_PREFIX, TokenHarborProvider

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
    sa.Column("operation_id", PGUUID(as_uuid=True)),
    sa.Column("operation_ordinal", sa.Integer),
    sa.Column("transport_started", sa.Boolean),
    sa.Column("attempt_state", sa.String(16), nullable=False, server_default="completed"),
)

ai_operation_record = sa.Table(
    "ai_operation_record",
    _METADATA,
    sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.Column("task", sa.String(32), nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("error_kind", sa.String(32)),
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
    operation_id: uuid.UUID | None = None
    operation_ordinal: int | None = None
    transport_started: bool | None = None


@dataclass(frozen=True, slots=True)
class AIOperationRecord:
    id: uuid.UUID
    task: str
    state: str
    started_at: datetime
    completed_at: datetime | None = None
    error_kind: str | None = None
    prompt_version: str | None = None


@dataclass(frozen=True, slots=True)
class AIOperationCohort:
    started: int
    terminal: int
    in_flight: int
    recovered: int
    attempts: int


def _provider_for(model: str, default: str) -> str:
    """The backend that serves `model`: a prefixed model name belongs to Token Harbor."""
    return TokenHarborProvider.name if model.startswith(MODEL_PREFIX) else default


def start_operation(
    engine: Engine, *, operation_id: uuid.UUID, task: str,
    prompt_version: str | None = None, now: datetime | None = None,
) -> None:
    """Persist the logical operation before preflight or provider work begins."""
    with engine.begin() as connection:
        connection.execute(sa.insert(ai_operation_record).values(
            id=operation_id,
            task=task,
            state="in_flight",
            started_at=now or datetime.now(UTC),
            prompt_version=prompt_version,
        ))


def finish_operation(
    engine: Engine, *, operation_id: uuid.UUID, state: str,
    error_kind: str | None = None, now: datetime | None = None,
) -> None:
    """Write the one terminal state for an operation, preserving in-flight on crash."""
    with engine.begin() as connection:
        connection.execute(
            sa.update(ai_operation_record)
            .where(ai_operation_record.c.id == operation_id)
            .where(ai_operation_record.c.completed_at.is_(None))
            .values(
                state=state,
                error_kind=error_kind,
                completed_at=now or datetime.now(UTC),
            )
        )


def operation_cohort(
    engine: Engine,
    *,
    since: datetime,
    grace: timedelta = timedelta(minutes=5),
    now: datetime | None = None,
) -> AIOperationCohort:
    """Close expired in-flight operations, then report the start-time cohort."""
    moment = now or datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            sa.update(ai_operation_record)
            .where(ai_operation_record.c.started_at >= since)
            .where(ai_operation_record.c.started_at < moment - grace)
            .where(ai_operation_record.c.completed_at.is_(None))
            .values(
                state="recovered",
                error_kind="operation_timeout",
                completed_at=moment,
            )
        )
        totals = connection.execute(
            sa.select(
                sa.func.count().label("started"),
                sa.func.count(ai_operation_record.c.completed_at).label("terminal"),
                sa.func.count().filter(ai_operation_record.c.completed_at.is_(None)).label("in_flight"),
                sa.func.count()
                .filter(ai_operation_record.c.state == "recovered")
                .label("recovered"),
            ).where(ai_operation_record.c.started_at >= since)
            .where(ai_operation_record.c.started_at <= moment)
        ).one()
        attempt_count = connection.execute(
            sa.select(sa.func.count())
            .select_from(ai_call_record.join(
                ai_operation_record,
                ai_call_record.c.operation_id == ai_operation_record.c.id,
            ))
            .where(ai_operation_record.c.started_at >= since)
            .where(ai_operation_record.c.started_at <= moment)
            .where(ai_call_record.c.transport_started.is_(True))
        ).scalar_one()
    return AIOperationCohort(
        started=totals.started,
        terminal=totals.terminal,
        in_flight=totals.in_flight,
        recovered=totals.recovered,
        attempts=attempt_count,
    )


def records_from_attempts(
    attempts: Sequence["Attempt"],
    *,
    task: str,
    provider: str,
    fallback_used: bool,
    prompt_version: str | None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    operation_id: uuid.UUID | None = None,
) -> list[AICallRecord]:
    """One `AICallRecord` per `AIRouter.run` attempt — success or not (card F20-19).

    Usage attached to an attempt is preserved even for failed HTTP responses. The
    response arguments remain a compatibility fallback for older Attempt producers.

    `provider` is the default; an attempt on a model of another backend (a prefixed model
    name) is recorded under that backend.
    """
    records = []
    for index, attempt in enumerate(attempts):
        succeeded = attempt.error_kind is None
        is_final_success = succeeded and index == len(attempts) - 1
        records.append(
            AICallRecord(
                task=task,
                provider=_provider_for(attempt.model, provider),
                model=attempt.model,
                attempt=attempt.attempt,
                success=succeeded,
                error_kind=attempt.error_kind.value if attempt.error_kind else None,
                http_status=attempt.http_status,
                latency_ms=attempt.latency_ms,
                prompt_tokens=(
                    attempt.prompt_tokens
                    if attempt.prompt_tokens is not None
                    else (prompt_tokens if is_final_success else None)
                ),
                completion_tokens=(
                    attempt.completion_tokens
                    if attempt.completion_tokens is not None
                    else (completion_tokens if is_final_success else None)
                ),
                fallback_used=fallback_used,
                cache_hit=False,
                prompt_version=prompt_version,
                operation_id=operation_id or attempt.operation_id,
                operation_ordinal=attempt.operation_ordinal,
                transport_started=attempt.transport_started,
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
            "operation_id": record.operation_id,
            "operation_ordinal": record.operation_ordinal,
            "transport_started": record.transport_started,
            "attempt_state": "completed",
        }
        for record in records
    ]
    with engine.begin() as connection:
        # Final telemetry updates the durable in-flight row created by the HTTP
        # transport hook. Replays update the same operation/ordinal, never duplicate.
        statement = pg_insert(ai_call_record).values(rows).on_conflict_do_update(
            constraint="uq_ai_call_record_operation_ordinal",
            set_={
                key: getattr(pg_insert(ai_call_record).excluded, key)
                for key in rows[0]
                if key not in {"id", "created_at", "operation_id", "operation_ordinal"}
            },
        )
        connection.execute(statement)


def record_attempt_started(
    engine: Engine,
    *,
    operation_id: uuid.UUID,
    operation_ordinal: int,
    task: str,
    provider: str,
    model: str,
    attempt: int,
    prompt_version: str | None,
    fallback_used: bool,
    now: datetime | None = None,
) -> None:
    """Durably open a provider attempt at the transport boundary.

    A process crash leaves this row in-flight with unknown usage and no fabricated
    outcome. The operation/ordinal constraint is the idempotency key.
    """
    statement = pg_insert(ai_call_record).values(
        id=uuid.uuid4(),
        created_at=now or datetime.now(UTC),
        task=task,
        provider=_provider_for(model, provider),
        model=model,
        attempt=attempt,
        success=False,
        error_kind=None,
        http_status=None,
        latency_ms=None,
        prompt_tokens=None,
        completion_tokens=None,
        fallback_used=fallback_used,
        cache_hit=False,
        prompt_version=prompt_version,
        operation_id=operation_id,
        operation_ordinal=operation_ordinal,
        transport_started=True,
        attempt_state="in_flight",
    ).on_conflict_do_nothing(constraint="uq_ai_call_record_operation_ordinal")
    with engine.begin() as connection:
        connection.execute(statement)


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
    "AIOperationRecord",
    "AIOperationCohort",
    "ai_operation_record",
    "ai_call_record",
    "finish_operation",
    "purge_older_than",
    "record_calls",
    "record_attempt_started",
    "start_operation",
    "operation_cohort",
    "records_from_attempts",
]
