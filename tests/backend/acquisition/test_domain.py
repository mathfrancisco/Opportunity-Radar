from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionMode,
    CollectionNetworkPolicy,
    CollectionRequest,
    ExecutionTrigger,
    HealthResult,
    ManualInput,
    ManualInputKind,
    SourceRun,
    SourceRunStatus,
)


def test_manual_request_requires_input() -> None:
    with pytest.raises(ValueError, match="requires at least one"):
        CollectionRequest(mode=CollectionMode.MANUAL)


def test_health_result_requires_error_for_unhealthy_result() -> None:
    with pytest.raises(ValueError, match="requires an error code"):
        HealthResult(healthy=False)


def test_source_run_enforces_lifecycle_and_metrics() -> None:
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run = SourceRun(source_definition_id=uuid4())

    run.start(started_at)
    run.record_items(seen=3, persisted=2, invalid=1)
    run.record_http_request(retries=1)
    run.finish(SourceRunStatus.PARTIAL, at=started_at + timedelta(seconds=3))

    assert run.status is SourceRunStatus.PARTIAL
    assert run.items_seen == 3
    assert run.items_persisted == 2
    assert run.items_invalid == 1
    assert run.http_requests == 1
    assert run.retry_count == 1


def test_execution_trigger_is_independent_from_collection_mode() -> None:
    request = CollectionRequest(
        mode=CollectionMode.INCREMENTAL,
        execution_trigger=ExecutionTrigger.SCHEDULED,
    )
    run = SourceRun(
        source_definition_id=uuid4(), execution_trigger=request.execution_trigger
    )

    assert request.mode is CollectionMode.INCREMENTAL
    assert run.execution_trigger is ExecutionTrigger.SCHEDULED


def test_failed_run_requires_structured_error() -> None:
    run = SourceRun(source_definition_id=uuid4())
    run.start()
    error = AcquisitionError(AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "unexpected field")

    run.finish(SourceRunStatus.FAILED, error=error)

    assert run.error_code is AcquisitionErrorCode.PARSER_SCHEMA_CHANGED
    assert run.error_summary == "unexpected field"


def test_manual_input_types_are_explicit() -> None:
    manual_input = ManualInput(kind=ManualInputKind.TEXT, value="job description")

    assert manual_input.kind is ManualInputKind.TEXT


def test_run_interval_is_independent_from_request_retry_delays() -> None:
    policy = CollectionNetworkPolicy(
        max_retry_delay_seconds=30,
        minimum_run_interval_seconds=21_600,
    )

    assert policy.minimum_interval_seconds == 0
    assert policy.minimum_run_interval_seconds == 21_600

    with pytest.raises(ValueError, match="cannot exceed 604800"):
        CollectionNetworkPolicy(minimum_run_interval_seconds=604_801)


def test_collection_request_rejects_invalid_keywords() -> None:
    with pytest.raises(ValueError, match="at most 10 non-empty strings"):
        CollectionRequest(keywords=("",))
