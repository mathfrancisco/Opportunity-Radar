"""Framework-free contracts and lifecycle rules for source acquisition."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from enum import StrEnum
from math import isfinite
from typing import Any, Mapping
from uuid import UUID, uuid4

from opportunity_radar.acquisition.scheduling import ConditionalRequestHeaders


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
    #: The provider says the calling account has exhausted its account-wide credit or
    #: usage budget (Tavily HTTP 433). CREDIT_BUDGET_EXCEEDED separately reports the
    #: per-run ceiling configured by the radar.
    SOURCE_QUOTA_EXHAUSTED = "SOURCE_QUOTA_EXHAUSTED"
    #: The radar stopped this run at its own Tavily credit ceiling. This is separate
    #: from SOURCE_QUOTA_EXHAUSTED, which reports the provider's account-wide quota.
    CREDIT_BUDGET_EXCEEDED = "CREDIT_BUDGET_EXCEEDED"


class AcquisitionError(Exception):
    """A domain error that retains a stable category for callers and metrics."""

    def __init__(
        self,
        code: AcquisitionErrorCode,
        summary: str,
        *,
        retryable: bool = False,
        field: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = retryable
        # The request field that caused a configuration error, dotted for nested keys
        # ("configuration.board_token"), so a form can show the refusal where it belongs.
        self.field = field
        # Only set for SOURCE_RATE_LIMITED, parsed from the response's Retry-After header
        # (F20-25): lets a caller batching several probes wait the right amount.
        self.retry_after_seconds = retry_after_seconds


class InvalidSourceRunTransitionError(AcquisitionError):
    def __init__(self, summary: str) -> None:
        super().__init__(AcquisitionErrorCode.INVALID_CONFIGURATION, summary)


def parse_retry_after_seconds(header_value: str | None) -> float | None:
    """Parse a `Retry-After` header value (delta-seconds or HTTP-date) into seconds.

    Returns `None` when the header is absent or unparseable, so a caller can fall back to
    its own default without pretending the server gave a number.
    """
    if header_value is None:
        return None
    try:
        seconds = float(header_value)
    except ValueError:
        try:
            parsed_date = parsedate_to_datetime(header_value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
        seconds = (parsed_date - datetime.now(timezone.utc)).total_seconds()
    if not isfinite(seconds):
        return None
    return max(0.0, seconds)


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


class ExecutionTrigger(StrEnum):
    """The actor that initiated a source run, independently of collection mode."""

    ON_DEMAND = "ON_DEMAND"
    SCHEDULED = "SCHEDULED"


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
    #: Items the source returned that are not opportunities (e.g. an untitled Workday
    #: posting): counted as seen and skipped, never as invalid (F20-75).
    skipped_items: int = 0
    last_invalid_item_error: str | None = None
    #: What the source's own API said the board holds, when it says so at all. `None`
    #: means the collector never learned a total, not that the board announced zero.
    items_announced: int | None = None
    #: Credits charged by the provider during this request. It is copied to the
    #: run by AcquisitionService after collection completes.
    credits_used: int = 0
    #: The representation's validators from this attempt's response, when the collector
    #: read and reported them (F20-38). `None` means the collector did not report one, not
    #: that the response lacked it — a collector without HTTP-conditional support simply
    #: never calls `record_conditional_response`.
    response_etag: str | None = None
    response_last_modified: str | None = None
    #: Whether this attempt's response was a bare 304. A 304 revalidates the checkpoint's
    #: representation; it never proves the board is fully read (SPEC 39 §7 — only F20-39's
    #: manifest check may do that), so `AcquisitionService` must not read this as coverage.
    not_modified: bool = False
    #: How many 304 responses this run received across every representation it revalidated
    #: (F20-39). Counted separately from `not_modified` (which only says "at least one")
    #: so `AcquisitionService` can tell a single bare 304 apart from every page of a
    #: declared manifest revalidating together.
    not_modified_count: int = 0
    #: How many representations (pages/categories) this run's collector declared it would
    #: check, when it declared one at all (F20-39). `None` means no manifest was declared —
    #: a bare 304 with no manifest can never prove full coverage, only that the one
    #: representation it touched is unchanged.
    manifest_size: int | None = None

    def record_conditional_response(
        self,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        not_modified: bool = False,
    ) -> None:
        if etag is not None:
            self.response_etag = etag
        if last_modified is not None:
            self.response_last_modified = last_modified
        if not_modified:
            self.not_modified = True
            self.not_modified_count += 1

    def record_manifest(self, total_representations: int) -> None:
        """A collector declares how many representations make up this run's manifest.

        Only a declared manifest, fully revalidated (every representation's own 304),
        can let a later run reuse a previously persisted complete inventory — a bare 304
        with no declared manifest stays incomplete (SPEC 39 §7).
        """
        if total_representations < 1:
            raise ValueError("manifest_size must be positive")
        self.manifest_size = total_representations

    def record_items_announced(self, total: int) -> None:
        if total < 0:
            raise ValueError("items_announced cannot be negative")
        self.items_announced = total

    def record_http_attempt(self, *, retry: bool = False) -> None:
        self.http_requests += 1
        self.last_http_attempt_at = datetime.now(timezone.utc)
        if retry:
            self.retry_count += 1

    def record_rate_limit(self) -> None:
        self.rate_limit_events += 1

    def record_credits(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("credits cannot be negative")
        self.credits_used += amount

    def record_skipped_item(self) -> None:
        self.skipped_items += 1

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
    minimum_run_interval_seconds: float | None = None

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
            raise ValueError("max_retry_delay_seconds cannot be below minimum_interval_seconds")
        run_interval = self.minimum_run_interval_seconds
        if run_interval is not None and (not isfinite(run_interval) or run_interval < 0):
            raise ValueError("minimum_run_interval_seconds must be finite and non-negative")
        if run_interval is not None and run_interval > 604_800:
            raise ValueError("minimum_run_interval_seconds cannot exceed 604800")


@dataclass(frozen=True, slots=True)
class CollectionRequest:
    source_definition_id: UUID | None = None
    mode: CollectionMode = CollectionMode.DISCOVERY
    execution_trigger: ExecutionTrigger = ExecutionTrigger.ON_DEMAND
    company_reference: str | None = None
    company_name: str | None = None
    api_region: str | None = None
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
    known_ats_boards: frozenset[tuple[str, str]] | None = field(
        default=None, compare=False, repr=False
    )
    #: `If-None-Match`/`If-Modified-Since` for this request's representation, built by
    #: `AcquisitionService` from the checkpoint's stored validators (F20-38). `None` when
    #: there is no checkpoint yet, or the checkpoint belongs to a different scope. A
    #: collector that supports HTTP-conditional requests (`CollectorCapabilities.etag`/
    #: `last_modified`) reads this to send the headers; one that does not simply ignores it.
    conditional_headers: ConditionalRequestHeaders | None = None
    #: An interrupted run this collection continues (F20-39 "retomada da mesma execução").
    #: Purely a provenance link recorded on the new run — it never derives `cursor`
    #: automatically. The caller supplies both together: the id of the persisted prefix it
    #: is resuming, and the explicit cursor to resume it from.
    resume_of_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.max_items is not None and self.max_items < 1:
            raise ValueError("max_items must be positive")
        if len(self.keywords) > 10 or any(
            not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 100
            for keyword in self.keywords
        ):
            raise ValueError(
                "keywords must contain at most 10 non-empty strings up to 100 characters"
            )
        if self.mode is CollectionMode.MANUAL and not self.manual_inputs:
            raise ValueError("manual collection requires at least one manual input")
        if self.mode is not CollectionMode.MANUAL and self.manual_inputs:
            raise ValueError("manual inputs require manual collection mode")
        if self.resume_of_run_id is not None and self.cursor is None:
            raise ValueError("resuming a run requires an explicit cursor")


def item_payload_bytes(item: CollectedItem) -> int:
    """UTF-8 size of the item's raw payload as serialized, the run's received-bytes unit."""
    return len(json.dumps(item.raw_payload, ensure_ascii=False, default=str).encode("utf-8"))


def newest_item_age_seconds(newest: datetime | None, at: datetime) -> int | None:
    """Age of the newest dated item at `at`; `None` when no item carried a date."""
    if newest is None:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return max(0, int((at - newest).total_seconds()))


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
    #: Explicit application-window deadline (schema.org `JobPosting.validThrough`,
    #: card F20-61). `None` for every collector that does not expose one — never
    #: guessed. A future date is a recency-filter exception independent of contract
    #: type or age.
    valid_through: datetime | None = None
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
    execution_trigger: ExecutionTrigger = ExecutionTrigger.ON_DEMAND
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
    #: Provider credits spent by this run (e.g. Tavily's usage.credits), a different unit
    #: from http_requests/retry_count, which keep counting HTTP calls regardless of what a
    #: source charges per call. A generic field, not Tavily-specific: any future paid API
    #: source can report spend the same way (F20-43, docs/41-spec-tavily.md section 6).
    credits_used: int = 0
    error_code: AcquisitionErrorCode | None = None
    error_summary: str | None = None
    checkpoint_before: str | None = None
    checkpoint_after: str | None = None
    #: What the source announced this run, when it said so. `None` means unknown, not zero.
    items_announced: int | None = None
    #: Whether this run read the whole board: `SUCCEEDED`, unbounded by `max_items`, and
    #: (when a total is known) `items_seen` reached it. Only a complete run may close a
    #: job that stopped appearing — see `evaluate_completeness`.
    complete: bool = False
    #: Serialized size of the items this run received, and how old its newest dated item
    #: was when the run ended (F48-07). `None` = not measured, never a guessed zero.
    bytes_received: int | None = None
    newest_item_age_seconds: int | None = None

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
        if requests < 0 or retries < 0 or retries > requests or rate_limit_events < 0:
            raise ValueError("invalid HTTP activity counters")
        self.http_requests += requests
        self.retry_count += retries
        self.rate_limit_events += rate_limit_events

    def record_credits(self, amount: int) -> None:
        self._require_running()
        if amount < 0:
            raise ValueError("credits cannot be negative")
        self.credits_used += amount

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


def evaluate_completeness(
    *,
    status: SourceRunStatus,
    max_items: int | None,
    items_seen: int,
    items_announced: int | None,
) -> bool:
    """Did this run read the whole board?

    Only a `SUCCEEDED` run that was never bounded by `max_items` can be complete, because a
    capped run stopping short of the total is by design, not evidence of anything missing.
    Without a known total the run is trusted as complete on those two conditions alone; a
    known total additionally requires `items_seen` to have reached it, which is what makes
    a shrunk `items_seen` from broken pagination visible.
    """
    if status is not SourceRunStatus.SUCCEEDED:
        return False
    if max_items is not None:
        return False
    if items_announced is None:
        return True
    return items_seen >= items_announced


SEMANTIC_HASH_VERSION = "semantic-hash-v1"
# Only volatile collector bookkeeping is ignored. Posting timestamps remain material.
SEMANTIC_HASH_NOISE_KEYS_V1 = frozenset(
    {"scraped_at", "fetched_at", "accessed_at", "retrieved_at", "crawled_at", "views", "view_count"}
)


@dataclass(frozen=True, slots=True)
class ContentHashes:
    raw_hash: str
    semantic_hash: str
    semantic_hash_version: str


def semantic_hash(payload: Mapping[str, Any], *, version: str = SEMANTIC_HASH_VERSION) -> str:
    if version != SEMANTIC_HASH_VERSION:
        raise ValueError(f"unknown semantic hash version: {version}")

    def clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in SEMANTIC_HASH_NOISE_KEYS_V1
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):
            return " ".join(value.split())
        return value

    serialized = json.dumps(
        clean(dict(payload)), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(f"{version}:{serialized}".encode("utf-8")).hexdigest()


def content_hashes(payload: Mapping[str, Any], *, raw_hash: str) -> ContentHashes:
    return ContentHashes(raw_hash, semantic_hash(payload), SEMANTIC_HASH_VERSION)
