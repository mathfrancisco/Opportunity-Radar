"""Transactional observation of worker jobs without turning them into a queue."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.operations.models import WorkerJobStateModel, WorkerPassHistoryModel
from opportunity_radar.platform.logging import correlation_scope

#: Passes kept per job. The collection job runs every minute, so this is a few hours of
#: history: enough to see a hole, small enough to never need a retention job of its own.
PASS_HISTORY_LIMIT = 200


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
            session.add(
                WorkerPassHistoryModel(
                    job_name=job_name, correlation_id=correlation_id, started_at=started_at
                )
            )
            session.commit()
        try:
            yield correlation_id
        except Exception as error:
            _finish_job(
                engine, job_name, started_at, success=False, error=str(error),
                correlation_id=correlation_id,
            )
            raise
        else:
            _finish_job(
                engine, job_name, started_at, success=True, error=None,
                correlation_id=correlation_id,
            )


def annotate_pass(
    engine: Engine,
    correlation_id: str,
    *,
    due_sources: int | None = None,
    **details: object,
) -> None:
    """Attach what a pass found (DUE sources, outcome counts) to its history row."""
    with Session(engine) as session:
        row = session.scalar(
            select(WorkerPassHistoryModel).where(
                WorkerPassHistoryModel.correlation_id == correlation_id
            )
        )
        if row is None:  # pragma: no cover - the row is written when the pass starts
            return
        if due_sources is not None:
            row.due_sources = due_sources
        row.details = {**row.details, **details}
        session.commit()


def recent_passes(
    session: Session, job_name: str, *, limit: int = 20
) -> list[WorkerPassHistoryModel]:
    """Newest first."""
    return list(
        session.scalars(
            select(WorkerPassHistoryModel)
            .where(WorkerPassHistoryModel.job_name == job_name)
            .order_by(WorkerPassHistoryModel.started_at.desc())
            .limit(limit)
        )
    )


def _finish_job(
    engine: Engine,
    job_name: str,
    started_at: datetime,
    *,
    success: bool,
    error: str | None,
    correlation_id: str,
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
        session.execute(
            update(WorkerPassHistoryModel)
            .where(WorkerPassHistoryModel.correlation_id == correlation_id)
            .values(
                finished_at=finished_at,
                duration_ms=state.last_duration_ms,
                success=success,
            )
        )
        keep = (
            select(WorkerPassHistoryModel.id)
            .where(WorkerPassHistoryModel.job_name == job_name)
            .order_by(WorkerPassHistoryModel.started_at.desc())
            .limit(PASS_HISTORY_LIMIT)
        )
        session.execute(
            delete(WorkerPassHistoryModel).where(
                WorkerPassHistoryModel.job_name == job_name,
                WorkerPassHistoryModel.id.not_in(keep),
            )
        )
        session.commit()
