"""Framework-free contracts and lifecycle rules for source acquisition."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from math import isfinite
from typing import Any, Mapping
from uuid import UUID, uuid4


class AcquisitionErrorCode(StrEnum):
    """Stable error categories exposed across acquisition adapters."""

    SOURCE_TIMEOUT = "SOURCE_TIMEOUT"
    SOURCE_RATE_LIMITED = "SOURCE_RATE_LIMITED"
    SOURCE_UNAUTHORIZED = "SOURCE_UNAUTHORIZED"
    SOURCE_FORBIDDEN = "SOURCE_FORBIDDEN"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_SERVER_ERROR = "SOURCE_SERVER_ERROR"
    INVALID_CONFIGURATION = "INVALID_CONFIGURATION"
    PARSER_SCHEMA_CHANGED = "PARSER_SCHEMA_CHANGED"
    INVALID_ITEM = "INVALID_ITEM"
    CHECKPOINT_ERROR = "CHECKPOINT_ERROR"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    UNKNOWN_EXTERNAL_ERROR = "UNKNOWN_EXTERNAL_ERROR"
    MANUAL_INPUT_INVALID = "MANUAL_INPUT_INVALID"


class AcquisitionError(Exception):
    """A domain error that retains a stable category for callers and metrics."""

    def __init__(
        self,
        code: AcquisitionErrorCode,
        summary: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = retryable


class InvalidSourceRunTransitionError(AcquisitionError):
    def __init__(self, summary: str) -> None:
        super().__init__(AcquisitionErrorCode.INVALID_CONFIGURATION, summary)


@dataclass(frozen=True, slots=True)
class CollectorCapabilities:
    company_jobs: bool = False
    keyword_search: bool = False
    location_search: bool = False
    incremental_cursor: bool = False
    etag: bool = False
    last_modified: bool = False
    closed_detection: bool = False
    authentication: bool = False
    pagination: bool = False
    direct_input: bool = False


class CollectionMode(StrEnum):
    DISCOVERY = "DISCOVERY"
    INCREMENTAL = "INCREMENTAL"
    MANUAL = "MANUAL"


class ManualInputKind(StrEnum):
    URL = "URL"
    TEXT = "TEXT"
    FILE = "FILE"


@dataclass(frozen=True, slots=True)
class ManualInput:
    """An explicit manual input submitted directly by the user."""

    kind: ManualInputKind
    value: str
    content: bytes | None = None
    content_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind is ManualInputKind.FILE and self.content is None:
            raise ValueError("manual file input requires content")
        if self.kind is not ManualInputKind.FILE and self.content is not None:
            raise ValueError("only manual file input accepts binary content")


@dataclass(slots=True)
class CollectionTelemetry:
    """Per-request network counters that collectors report to the run owner."""

    http_requests: int = 0
    retry_count: int = 0
    rate_limit_events: int = 0
    last_http_attempt_at: datetime | None = None
    invalid_items: int = 0
    last_invalid_item_error: str | None = None

    def record_http_attempt(self, *, retry: bool = False) -> None:
        self.http_requests += 1
        self.last_http_attempt_at = datetime.now(timezone.utc)
        if retry:
            self.retry_count += 1

    def record_rate_limit(self) -> None:
        self.rate_limit_events += 1

    def record_invalid_item(self, summary: str) -> None:
        self.invalid_items += 1
        self.last_invalid_item_error = summary


@dataclass(frozen=True, slots=True)
class CollectionNetworkPolicy:
    """Validated network limits applied to one source run."""

    max_retries: int = 2
    retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 30.0
    minimum_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.max_retries > 5:
            raise ValueError("max_retries must be between 0 and 5")
        delays = (
            self.retry_delay_seconds,
            self.max_retry_delay_seconds,
            self.minimum_interval_seconds,
        )
        if any(not isfinite(value) or value < 0 for value in delays):
            raise ValueError("network delays must be finite and non-negative")
        if self.max_retry_delay_seconds > 300:
            raise ValueError("max_retry_delay_seconds cannot exceed 300")
        if self.minimum_interval_seconds > 60:
            raise ValueError("minimum_interval_seconds cannot exceed 60")
        if self.max_retry_delay_seconds < self.minimum_interval_seconds:
            raise ValueError(
                "max_retry_delay_seconds cannot be below minimum_interval_seconds"
            )


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    source_definition_id: UUID | None = None
    mode: CollectionMode = CollectionMode.DISCOVERY
    company_reference: str | None = None
    company_name: str | None = None
    keywords: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    cursor: str | None = None
    since: datetime | None = None
    max_items: int | None = None
    correlation_id: str | None = None
    manual_inputs: tuple[ManualInput, ...] = ()
    telemetry: CollectionTelemetry = field(
        default_factory=CollectionTelemetry, compare=False, repr=False
    )
    network_policy: CollectionNetworkPolicy | None = None

    def __post_init__(self) -> None:
        if self.max_items is not None and self.max_items < 1:
            raise ValueError("max_items must be positive")
        if self.mode is CollectionMode.MANUAL and not self.manual_inputs:
            raise ValueError("manual collection requires at least one manual input")
        if self.mode is not CollectionMode.MANUAL and self.manual_inputs:
            raise ValueError("manual inputs require manual collection mode")


@dataclass(frozen=True, slots=True)
class CollectedItem:
    """Pre-normalization data emitted by a collector without fabricated values."""

    source_type: str
    raw_payload: Mapping[str, Any]
    external_id: str | None = None
    url: str | None = None
    title: str | None = None
    company_name: str | None = None
    location_text: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    updated_at: datetime | None = None
    cursor: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealthcheckContext:
    correlation_id: str | None = None


@dataclass(frozen=True, slots=True)
class HealthResult:
    healthy: bool
    summary: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_code: AcquisitionErrorCode | None = None

    def __post_init__(self) -> None:
        if self.healthy and self.error_code is not None:
            raise ValueError("healthy result cannot have an error code")
        if not self.healthy and self.error_code is None:
            raise ValueError("unhealthy result requires an error code")


class SourceRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            SourceRunStatus.SUCCEEDED,
            SourceRunStatus.PARTIAL,
            SourceRunStatus.FAILED,
            SourceRunStatus.CANCELLED,
        }


@dataclass(slots=True)
class SourceRun:
    """Lifecycle and counters for one bounded collection attempt."""

    source_definition_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: SourceRunStatus = SourceRunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items_seen: int = 0
    items_persisted: int = 0
    items_skipped: int = 0
    items_invalid: int = 0
    http_requests: int = 0
    retry_count: int = 0
    rate_limit_events: int = 0
    error_code: AcquisitionErrorCode | None = None
    error_summary: str | None = None
    checkpoint_before: str | None = None
    checkpoint_after: str | None = None

    def start(self, at: datetime | None = None) -> None:
        if self.status is not SourceRunStatus.PENDING:
            raise InvalidSourceRunTransitionError("only a pending source run can start")
        self.started_at = at or datetime.now(timezone.utc)
        self.status = SourceRunStatus.RUNNING

    def record_items(
        self,
        *,
        seen: int = 0,
        persisted: int = 0,
        skipped: int = 0,
        invalid: int = 0,
    ) -> None:
        self._require_running()
        values = (seen, persisted, skipped, invalid)
        if any(value < 0 for value in values):
            raise ValueError("source run counters cannot be negative")
        self.items_seen += seen
        self.items_persisted += persisted
        self.items_skipped += skipped
        self.items_invalid += invalid

    def record_http_request(self, retries: int = 0) -> None:
        self._require_running()
        if retries < 0:
            raise ValueError("retry count cannot be negative")
        self.http_requests += 1
        self.retry_count += retries

    def record_http_activity(
        self, *, requests: int, retries: int, rate_limit_events: int = 0
    ) -> None:
        self._require_running()
        if (
            requests < 0
            or retries < 0
            or retries > requests
            or rate_limit_events < 0
            or rate_limit_events > requests
        ):
            raise ValueError("invalid HTTP activity counters")
        self.http_requests += requests
        self.retry_count += retries
        self.rate_limit_events += rate_limit_events

    def finish(
        self,
        status: SourceRunStatus,
        *,
        at: datetime | None = None,
        error: AcquisitionError | None = None,
        checkpoint_after: str | None = None,
    ) -> None:
        if not status.is_terminal:
            raise InvalidSourceRunTransitionError("source run must finish in a terminal status")
        if self.status is not SourceRunStatus.RUNNING:
            raise InvalidSourceRunTransitionError("only a running source run can finish")
        if status is SourceRunStatus.SUCCEEDED and error is not None:
            raise ValueError("a successful source run cannot retain a fatal error")
        if status is SourceRunStatus.FAILED and error is None:
            raise ValueError("a failed source run requires an acquisition error")
        finished_at = at or datetime.now(timezone.utc)
        if self.started_at is not None and finished_at < self.started_at:
            raise ValueError("source run cannot finish before it starts")
        self.status = status
        self.finished_at = finished_at
        self.error_code = error.code if error else None
        self.error_summary = error.summary if error else None
        self.checkpoint_after = checkpoint_after

    def _require_running(self) -> None:
        if self.status is not SourceRunStatus.RUNNING:
            raise InvalidSourceRunTransitionError("source run is not running")
