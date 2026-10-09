"""A single, bounded operational pipeline window.

This module deliberately knows nothing about schedules.  A caller provides the three
allowed stages, which are run once in their fixed order while a PostgreSQL advisory
lock is held.  It is therefore safe for a timer to invoke and let exit: no polling,
retry loop, analysis, or retention is hidden here.
"""

from __future__ import annotations

import hashlib
import signal
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from time import monotonic
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from opportunity_radar.platform.logging import get_logger

logger = get_logger("opportunity_radar.pipeline")

STAGE_ORDER = ("collect_enabled_sources", "normalize_opportunities", "evaluate_pending")
ANALYSIS_BLOCKED = "analysis is opt-in and disabled for finite pipeline windows"
RETENTION_BLOCKED = "retention is blocked until F53-13 is accepted"


class ExitCode(IntEnum):
    SUCCESS = 0
    CONFIGURATION_ERROR = 2
    DEADLINE_REACHED = 10
    CLAIM_BUSY = 11
    STAGE_FAILED = 12
    INTERRUPTED = 13


class ConfigurationError(ValueError):
    """The window was refused before it touched a database or a source."""


class ClaimBusyError(RuntimeError):
    """A different finite window holds the pipeline claim."""


@dataclass(frozen=True, slots=True)
class StageCounts:
    input: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    stopped: int = 0


class Deadline:
    """A monotonic budget; wall-clock changes cannot lengthen a run."""

    def __init__(self, seconds: float, *, clock: Callable[[], float] = monotonic) -> None:
        if seconds <= 0:
            raise ConfigurationError("deadline_seconds must be greater than zero")
        self.seconds = seconds
        self._clock = clock
        self._ends_at = clock() + seconds

    def expired(self) -> bool:
        return self._clock() >= self._ends_at

    def remaining(self) -> float:
        return max(0.0, self._ends_at - self._clock())


class StopSignal:
    """One-way stop state shared by the signal handler and stage callbacks."""

    def __init__(self) -> None:
        self.reason: str | None = None

    def set(self, reason: str) -> None:
        if self.reason is None:
            self.reason = reason

    def requested(self, deadline: Deadline) -> bool:
        if self.reason is not None:
            return True
        if deadline.expired():
            self.set("deadline")
            return True
        return False


@dataclass(frozen=True, slots=True)
class StageContext:
    owner_sub: str
    deadline: Deadline
    stop: StopSignal

    def should_stop(self) -> bool:
        return self.stop.requested(self.deadline)


StageRun = Callable[[StageContext], StageCounts]


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    run: StageRun


@dataclass(slots=True)
class StageReport:
    name: str
    status: str
    reason: str | None = None
    counts: StageCounts = field(default_factory=StageCounts)
    error: str | None = None
    duration_ms: int = 0


@dataclass(slots=True)
class PipelineReport:
    exit_code: ExitCode
    outcome: str
    stages: list[StageReport] = field(default_factory=list)
    stop_reason: str | None = None
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": int(self.exit_code),
            "outcome": self.outcome,
            "stop_reason": self.stop_reason,
            "correlation_id": self.correlation_id,
            "duration_ms": self.duration_ms,
            "stages": [asdict(stage) for stage in self.stages],
        }


class PostgresWindowClaim:
    """Connection-scoped advisory claim released on exit or process crash."""

    def __init__(self, engine: Engine, *, name: str = "opportunity-radar-pipeline") -> None:
        self.engine = engine
        self.key = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big", signed=True)
        self.connection: Connection | None = None

    def __enter__(self) -> PostgresWindowClaim:
        self.connection = self.engine.connect()
        acquired = self.connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": self.key}
        )
        if not acquired:
            self.connection.close()
            self.connection = None
            raise ClaimBusyError()
        return self

    def __exit__(self, *_args: object) -> None:
        if self.connection is not None:
            try:
                self.connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": self.key})
                self.connection.commit()
            finally:
                self.connection.close()
                self.connection = None


def validate_owner(owner_sub: str | None) -> str:
    """Fail before clock, session, job observation, claims, or external work."""
    if not owner_sub or not owner_sub.strip():
        raise ConfigurationError("an explicit non-blank operational owner is required")
    return owner_sub.strip()


def describe_pipeline(*, owner_sub: str | None, deadline_seconds: float) -> dict[str, Any]:
    """Pure dry-run description: no clock, database, claim, or network access."""
    owner = validate_owner(owner_sub)
    if deadline_seconds <= 0:
        raise ConfigurationError("deadline_seconds must be greater than zero")
    return {
        "dry_run": True,
        "owner_configured": bool(owner),
        "deadline_seconds": deadline_seconds,
        "stages": [{"name": name, "status": "planned"} for name in STAGE_ORDER]
        + [
            {"name": "analyze_pending", "status": "blocked", "reason": ANALYSIS_BLOCKED},
            {"name": "retention", "status": "blocked", "reason": RETENTION_BLOCKED},
        ],
        "touches": "none",
    }


def run_pipeline(
    stages: list[StageSpec],
    *,
    owner_sub: str | None,
    deadline_seconds: float,
    claim_factory: Callable[[], PostgresWindowClaim],
    clock: Callable[[], float] = monotonic,
    stop: StopSignal | None = None,
) -> PipelineReport:
    """Run each allowed stage once. A returned failure never triggers a retry."""
    owner = validate_owner(owner_sub)
    if tuple(stage.name for stage in stages) != STAGE_ORDER:
        raise ConfigurationError("stages must be collect, normalize, then evaluate")
    deadline = Deadline(deadline_seconds, clock=clock)
    stop = stop or StopSignal()
    if stop.requested(deadline):
        return _stopped_report(stages, stop.reason or "deadline")
    started_at = clock()
    try:
        with claim_factory():
            reports: list[StageReport] = []
            context = StageContext(owner, deadline, stop)
            for index, stage in enumerate(stages):
                if context.should_stop():
                    reports.append(StageReport(stage.name, "skipped", f"not_started_{stop.reason}"))
                    continue
                stage_started_at = clock()
                try:
                    counts = stage.run(context)
                except Exception as error:
                    reports.append(
                        StageReport(
                            stage.name,
                            "failed",
                            "stage_failed",
                            error=_safe_error(error),
                            duration_ms=_duration_ms(clock, stage_started_at),
                        )
                    )
                    reports.extend(
                        StageReport(rest.name, "skipped", "previous_stage_failed")
                        for rest in stages[index + 1 :]
                    )
                    return PipelineReport(
                        ExitCode.STAGE_FAILED,
                        "stage_failed",
                        reports,
                        stop.reason,
                        duration_ms=_duration_ms(clock, started_at),
                    )
                if context.should_stop() or counts.stopped:
                    reports.append(
                        StageReport(
                            stage.name,
                            "stopped",
                            stop.reason or "stopped",
                            counts,
                            duration_ms=_duration_ms(clock, stage_started_at),
                        )
                    )
                    reports.extend(
                        StageReport(rest.name, "skipped", "previous_stage_stopped")
                        for rest in stages[index + 1 :]
                    )
                    break
                reports.append(
                    StageReport(
                        stage.name,
                        "completed",
                        counts=counts,
                        duration_ms=_duration_ms(clock, stage_started_at),
                    )
                )
            if stop.reason == "interrupted":
                return PipelineReport(
                    ExitCode.INTERRUPTED,
                    "interrupted",
                    reports,
                    stop.reason,
                    duration_ms=_duration_ms(clock, started_at),
                )
            if stop.reason == "deadline":
                return PipelineReport(
                    ExitCode.DEADLINE_REACHED,
                    "deadline_reached",
                    reports,
                    stop.reason,
                    duration_ms=_duration_ms(clock, started_at),
                )
            return PipelineReport(
                ExitCode.SUCCESS, "success", reports, duration_ms=_duration_ms(clock, started_at)
            )
    except ClaimBusyError:
        return PipelineReport(
            ExitCode.CLAIM_BUSY,
            "claim_busy",
            [StageReport(stage.name, "skipped", "claim_busy") for stage in stages],
        )
    except Exception as error:
        logger.error("pipeline claim unavailable", extra={"error": _safe_error(error)})
        return PipelineReport(
            ExitCode.CONFIGURATION_ERROR,
            "claim_unavailable",
            [StageReport(stage.name, "skipped", "claim_unavailable") for stage in stages],
        )


def _stopped_report(stages: list[StageSpec], reason: str) -> PipelineReport:
    code = ExitCode.INTERRUPTED if reason == "interrupted" else ExitCode.DEADLINE_REACHED
    return PipelineReport(
        code,
        "interrupted" if code == ExitCode.INTERRUPTED else "deadline_reached",
        [StageReport(stage.name, "skipped", f"not_started_{reason}") for stage in stages],
        reason,
    )


def _safe_error(error: BaseException) -> str:
    """Do not put stage messages (which can carry URLs/payloads) in the report."""
    return type(error).__name__


def _duration_ms(clock: Callable[[], float], started_at: float) -> int:
    return round(max(0.0, clock() - started_at) * 1000)


@contextmanager
def signal_stop(stop: StopSignal) -> Iterator[None]:
    """Stop taking new units on SIGINT/SIGTERM; the current unit decides its own boundary."""
    previous = {
        number: signal.signal(number, lambda *_args: stop.set("interrupted"))
        for number in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
