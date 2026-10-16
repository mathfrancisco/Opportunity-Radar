"""Daily data reduction for the 1 GB Neon ceiling (card R55-E6).

Three steps run once per UTC day inside the pipeline's `retention` stage, after the
opportunity retention itself, and all share its `OPPORTUNITY_RETENTION_APPLY` gate because
two of them destroy data:

* expire raw payloads of items that finished normalization (the envelope, the hash and the
  occurrence stay; see `operations/retention.py`, which never touches an item still waiting
  for the current normalizer);
* prune superseded match assessments (the current one and anything protected is kept; see
  `operations/assessment_retention.py`);
* measure `pg_database_size` and warn above a share of the limit. The measurement is
  read-only, so it also runs while the gate is off.

Without the gate the first two only count. Each step captures its own error so one failing
step cannot hide the others; a deadline or signal ends the pass without being a failure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from opportunity_radar.operations.assessment_retention import prune_superseded_assessments
from opportunity_radar.operations.retention import PayloadRetentionService
from opportunity_radar.platform.logging import get_logger

DEFAULT_SIZE_LIMIT_BYTES = 1_000_000_000
DEFAULT_SIZE_ALERT_RATIO = 0.7

logger = get_logger("opportunity_radar.operations.data_reduction")


@dataclass(slots=True)
class DataReductionReport:
    applied: bool
    #: Expired by this run, or (dry run) what a run would expire now.
    payloads: int = 0
    #: Deleted by this run, or (dry run) what a run would delete under the batch bound.
    assessments: int = 0
    database_size_bytes: int | None = None
    size_limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES
    size_alert: bool = False
    stopped: bool = False
    complete: bool = True
    errors: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def measure_database_size(
    engine: Engine,
    *,
    limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES,
    alert_ratio: float = DEFAULT_SIZE_ALERT_RATIO,
) -> tuple[int, bool]:
    """`pg_database_size` of the connected database and whether it is above the alert share."""
    with engine.connect() as connection:
        size = int(
            connection.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        )
    return size, size > limit_bytes * alert_ratio


def run_data_reduction(
    engine: Engine,
    *,
    apply: bool,
    payload_retention_days: int,
    payload_batch_size: int = 500,
    assessment_retention_days: int,
    assessment_batch_size: int = 500,
    size_limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES,
    size_alert_ratio: float = DEFAULT_SIZE_ALERT_RATIO,
    max_batches: int = 50,
    should_stop: Callable[[], bool] | None = None,
    now: datetime | None = None,
) -> DataReductionReport:
    stop = should_stop or (lambda: False)
    moment = now or datetime.now(UTC)
    report = DataReductionReport(applied=apply, size_limit_bytes=size_limit_bytes)

    if stop():
        report.stopped, report.complete = True, False
        return report

    try:
        report.payloads = _payloads(
            engine, apply, payload_retention_days, payload_batch_size, max_batches, stop, moment
        )
    except Exception as error:
        _fail(report, "payloads", error)

    if stop():
        report.stopped, report.complete = True, False
    else:
        try:
            pruned = prune_superseded_assessments(
                engine,
                retention_days=assessment_retention_days,
                batch_size=assessment_batch_size,
                max_batches=max_batches,
                dry_run=not apply,
                now=moment,
            )
            report.assessments = pruned.deleted
        except Exception as error:
            _fail(report, "assessments", error)

    # Cheap and read-only: measured even after a stop request so the day's number is logged.
    _measure(engine, report, size_limit_bytes, size_alert_ratio)

    if stop() and not report.errors:
        report.stopped, report.complete = True, False
    logger.info(
        "data reduction finished",
        extra={"job": "data_reduction", **{k: v for k, v in report.as_dict().items()}},
    )
    return report


def check_database_size(
    engine: Engine,
    *,
    size_limit_bytes: int = DEFAULT_SIZE_LIMIT_BYTES,
    size_alert_ratio: float = DEFAULT_SIZE_ALERT_RATIO,
) -> DataReductionReport:
    """Only the size measurement: no payload is expired and no assessment pruned.

    Used when the opportunity retention is switched off (`OPPORTUNITY_RETENTION_DAYS=0`):
    the off switch stops deletions, never the 1 GB watch.
    """
    report = DataReductionReport(applied=False, size_limit_bytes=size_limit_bytes)
    _measure(engine, report, size_limit_bytes, size_alert_ratio)
    return report


def _measure(
    engine: Engine, report: DataReductionReport, limit_bytes: int, alert_ratio: float
) -> None:
    try:
        size, alert = measure_database_size(
            engine, limit_bytes=limit_bytes, alert_ratio=alert_ratio
        )
    except Exception as error:
        _fail(report, "database_size", error)
        return
    report.database_size_bytes = size
    report.size_alert = alert
    extra = {
        "job": "data_reduction",
        "database_size_bytes": size,
        "limit_bytes": limit_bytes,
        "alert_ratio": alert_ratio,
    }
    if alert:
        logger.warning("database size above alert threshold", extra=extra)
    else:
        logger.info("database size measured", extra=extra)


def _payloads(
    engine: Engine,
    apply: bool,
    retention_days: int,
    batch_size: int,
    max_batches: int,
    stop: Callable[[], bool],
    moment: datetime,
) -> int:
    with Session(engine) as session:
        service = PayloadRetentionService(
            session, retention_days=retention_days, batch_size=batch_size
        )
        if not apply:
            return service.count_due_payloads(now=moment)
        expired = 0
        for _ in range(max_batches):
            if stop():
                break
            outcome = service.expire_due_payloads(now=moment)
            expired += outcome.expired
            if outcome.examined < batch_size:
                break
        return expired


def _fail(report: DataReductionReport, step: str, error: Exception) -> None:
    report.errors[step] = type(error).__name__
    report.complete = False
    logger.warning(
        "data reduction step failed",
        extra={"job": "data_reduction", "step": step, "error": type(error).__name__},
    )


__all__ = [
    "DEFAULT_SIZE_ALERT_RATIO",
    "DEFAULT_SIZE_LIMIT_BYTES",
    "DataReductionReport",
    "check_database_size",
    "measure_database_size",
    "run_data_reduction",
]
