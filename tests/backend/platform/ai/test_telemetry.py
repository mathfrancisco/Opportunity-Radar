"""Card F20-19: per-call telemetry carries shape, never PII.

`records_from_attempts` is pure and covered here without a database; `record_calls` and
`purge_older_than` touch Postgres and are proven in the integration tests below, gated
the same way `test_ai_quota_integration.py` gates its own database tests.
"""

from __future__ import annotations

import os
from dataclasses import fields
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from opportunity_radar.platform.ai.errors import ErrorKind
from opportunity_radar.platform.ai.router import Attempt
from opportunity_radar.platform.ai.telemetry import (
    AICallRecord,
    purge_older_than,
    record_calls,
    records_from_attempts,
)
from opportunity_radar.platform.database import create_database_engine

_SECRET_PAYLOAD = {
    "GROQ_API_KEY": "gsk_super_secret_value",
    "profile": {"name": "Ana Candidate", "email": "ana@example.com"},
    "posting": {"description": "we pay well, contact ana@example.com"},
}


def test_a_retry_and_a_fallback_produce_three_coherent_records() -> None:
    """One transient failure, one retry-that-fails-again would loop; here: fail, then
    fall back to a second model that succeeds — the shape SPEC 43 §7.3 describes."""
    attempts = (
        Attempt("model-a", 0, ErrorKind.TRANSIENT, None, 503),
        Attempt("model-a", 1, ErrorKind.TRANSIENT, None, 503),
        Attempt("model-b", 0, None, 850, 200),
    )

    records = records_from_attempts(
        attempts,
        task="job_match",
        provider="groq",
        fallback_used=True,
        prompt_version="v2",
        prompt_tokens=250,
        completion_tokens=40,
    )

    assert len(records) == 3
    assert [record.model for record in records] == ["model-a", "model-a", "model-b"]
    assert [record.attempt for record in records] == [0, 1, 0]
    assert [record.success for record in records] == [False, False, True]
    assert [record.error_kind for record in records] == ["transient", "transient", None]
    assert [record.http_status for record in records] == [503, 503, 200]
    # Only the call that actually answered billed tokens.
    assert records[0].prompt_tokens is None and records[0].completion_tokens is None
    assert records[1].prompt_tokens is None and records[1].completion_tokens is None
    assert records[2].prompt_tokens == 250
    assert records[2].completion_tokens == 40
    assert all(record.fallback_used for record in records)
    assert all(record.cache_hit is False for record in records)
    assert all(record.prompt_version == "v2" for record in records)


def test_every_attempt_failing_still_builds_one_record_per_attempt() -> None:
    attempts = (
        Attempt("model-a", 0, ErrorKind.QUOTA, None, 429),
        Attempt("model-b", 0, ErrorKind.QUOTA, None, 429),
    )

    records = records_from_attempts(
        attempts,
        task="job_match",
        provider="groq",
        fallback_used=False,
        prompt_version="v2",
    )

    assert len(records) == 2
    assert all(not record.success for record in records)
    assert all(record.prompt_tokens is None for record in records)


def test_no_field_on_any_record_carries_a_value_from_the_test_payload() -> None:
    """No column is free text beyond `error_kind` (card's "Não fazer"): walking every
    declared field of a record built from a request that *would* have leaked PII if the
    adapter forwarded it must never surface a fragment of that payload."""
    attempts = (Attempt("model-a", 0, None, 900, 200),)

    records = records_from_attempts(
        attempts,
        task="job_match",
        provider="groq",
        fallback_used=False,
        prompt_version="v2",
        prompt_tokens=100,
        completion_tokens=20,
    )

    haystack = str(_SECRET_PAYLOAD)
    field_names = [f.name for f in fields(AICallRecord)]
    for record in records:
        for name in field_names:
            value = getattr(record, name)
            assert str(value) not in haystack or value in (None, False, True)
    # Sanity: the record's own field set is exactly the shape SPEC 43 §8.5 promises,
    # never a free-text column beyond `error_kind`.
    assert set(field_names) == {
        "task",
        "provider",
        "model",
        "attempt",
        "success",
        "fallback_used",
        "cache_hit",
        "error_kind",
        "http_status",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "prompt_version",
    }


def test_cache_hit_record_has_no_tokens_and_attempt_zero() -> None:
    record = AICallRecord(
        task="job_match",
        provider="groq",
        model="model-a",
        attempt=0,
        success=True,
        fallback_used=False,
        cache_hit=True,
        prompt_version="v2",
    )

    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.attempt == 0
    assert record.success is True


def _engine() -> Engine:
    return create_database_engine(os.environ["DATABASE_URL"])


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_call_record"))


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_record_calls_inserts_every_record() -> None:
    engine = _engine()
    _reset(engine)
    records = [
        AICallRecord(
            task="job_match",
            provider="groq",
            model="model-a",
            attempt=0,
            success=True,
            fallback_used=False,
            cache_hit=False,
            prompt_tokens=10,
            completion_tokens=5,
            prompt_version="v2",
        ),
        AICallRecord(
            task="job_match",
            provider="groq",
            model="model-b",
            attempt=0,
            success=False,
            error_kind="quota",
            http_status=429,
            fallback_used=True,
            cache_hit=False,
        ),
    ]

    record_calls(engine, records)

    with engine.connect() as connection:
        count = connection.execute(
            text("SELECT count(*) FROM platform.ai_call_record")
        ).scalar_one()
    assert count == 2


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
def test_purge_removes_only_records_older_than_the_limit() -> None:
    engine = _engine()
    _reset(engine)
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=UTC)
    old_record = AICallRecord(
        task="job_match",
        provider="groq",
        model="model-a",
        attempt=0,
        success=True,
        fallback_used=False,
        cache_hit=False,
    )
    record_calls(engine, [old_record], now=now - timedelta(days=31))
    record_calls(engine, [old_record], now=now - timedelta(days=1))

    purged = purge_older_than(engine, 30, now=now)

    assert purged == 1
    with engine.connect() as connection:
        remaining = connection.execute(
            text("SELECT count(*) FROM platform.ai_call_record")
        ).scalar_one()
    assert remaining == 1
