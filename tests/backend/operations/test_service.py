"""Database-backed proof that worker observations survive success and failure."""

from __future__ import annotations

import os
from datetime import timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.operations.models import WorkerJobStateModel
from opportunity_radar.operations.service import observe_job
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def test_job_state_preserves_the_last_success_after_a_failure() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_database_engine(database_url)
    job_name = "test:job-state"
    with Session(engine) as session:
        session.execute(
            delete(WorkerJobStateModel).where(WorkerJobStateModel.job_name == job_name)
        )
        session.commit()

    with observe_job(engine, job_name=job_name, interval=timedelta(minutes=1)):
        pass
    with pytest.raises(RuntimeError, match="controlled failure"):
        with observe_job(engine, job_name=job_name, interval=timedelta(minutes=1)):
            raise RuntimeError("controlled failure")

    with Session(engine) as session:
        state = session.scalar(
            select(WorkerJobStateModel).where(WorkerJobStateModel.job_name == job_name)
        )

    assert state is not None
    assert state.last_success_at is not None
    assert state.last_failure_at is not None
    assert state.last_failure_at >= state.last_success_at
    assert state.last_error == "controlled failure"
    assert state.last_duration_ms is not None
    assert state.next_run_at > state.last_attempt_at
