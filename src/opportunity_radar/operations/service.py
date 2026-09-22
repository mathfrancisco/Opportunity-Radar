"""Transactional observation of worker jobs without turning them into a queue."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.operations.models import WorkerJobStateModel
from opportunity_radar.platform.logging import correlation_scope


@contextmanager
def observe_job(
    engine: Engine,
    *,
    job_name: str,
    interval: timedelta,
) -> Iterator[str]:
    """Persist start and finish independently so failures retain the last success."""
    started_at = datetime.now(UTC)
    with correlation_scope() as correlation_id:
        with Session(engine) as session:
            state = session.get(WorkerJobStateModel, job_name)
            if state is None:
                state = WorkerJobStateModel(
                    job_name=job_name,
                    last_attempt_at=started_at,
                    next_run_at=started_at + interval,
                    last_correlation_id=correlation_id,
                )
                session.add(state)
            else:
                state.last_attempt_at = started_at
                state.next_run_at = started_at + interval
                state.last_correlation_id = correlation_id
            session.commit()
        try:
            yield correlation_id
        except Exception as error:
            _finish_job(engine, job_name, started_at, success=False, error=str(error))
            raise
        else:
            _finish_job(engine, job_name, started_at, success=True, error=None)


def _finish_job(
    engine: Engine,
    job_name: str,
    started_at: datetime,
    *,
    success: bool,
    error: str | None,
) -> None:
    finished_at = datetime.now(UTC)
    with Session(engine) as session:
        state = session.get(WorkerJobStateModel, job_name)
        if state is None:  # pragma: no cover - start and finish are committed together by caller
            raise RuntimeError(f"worker job state disappeared: {job_name}")
        state.last_duration_ms = round((finished_at - started_at).total_seconds() * 1000)
        state.last_error = error
        if success:
            state.last_success_at = finished_at
        else:
            state.last_failure_at = finished_at
        session.commit()
