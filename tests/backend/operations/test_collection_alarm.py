"""F48-07: alarm for a hole in scheduled collection, with a controlled clock."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel, SourceRunModel
from opportunity_radar.operations.collection_alarm import cadence_seconds, collection_gap_report
from opportunity_radar.operations.service import observe_job, recent_passes
from opportunity_radar.platform.database import create_database_engine
from scripts.doctor import OK, WARN, describe_collection_gap

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

_db = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def test_cadence_is_the_longest_normal_gap() -> None:
    assert cadence_seconds("0 */6 * * *", reference=NOW) == 6 * 3600
    assert cadence_seconds("0 0 * * *", reference=NOW) == 24 * 3600
    assert cadence_seconds("0 0 * * 0", reference=NOW) == 7 * 24 * 3600
    # Weekdays only: Friday to Monday is the longest gap, not the mean.
    assert cadence_seconds("0 0 * * 1-5", reference=NOW) == 3 * 24 * 3600


def _source(
    session: Session, schedule: str | None, *, enabled: bool = True
) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="greenhouse",
        name=f"gap {uuid4().hex[:8]}",
        enabled=enabled,
        schedule=schedule,
        configuration={"board_token": "gap"},
        rate_limit_policy={},
        created_at=NOW - timedelta(days=30),
    )
    session.add(source)
    session.flush()
    return source


def _scheduled_run(session: Session, source: SourceDefinitionModel, ago: timedelta) -> None:
    started = NOW - ago
    session.add(
        SourceRunModel(
            id=uuid4(),
            source_definition_id=source.id,
            execution_trigger="SCHEDULED",
            status="SUCCEEDED",
            started_at=started,
            finished_at=started + timedelta(seconds=1),
        )
    )
    session.flush()


@_db
def test_overdue_sources_and_global_gap_use_twice_the_cadence() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        try:
            # The shared database may hold other scheduled sources: hide them for this
            # transaction, which is rolled back and never committed.
            session.execute(update(SourceDefinitionModel).values(enabled=False))
            fresh = _source(session, "0 */6 * * *")
            late = _source(session, "0 */6 * * *")
            edge = _source(session, "0 */6 * * *")
            never = _source(session, "0 0 * * *")
            _source(session, None)  # unscheduled: nothing to miss
            _source(session, "0 */6 * * *", enabled=False)
            _scheduled_run(session, fresh, timedelta(hours=1))
            _scheduled_run(session, late, timedelta(hours=12, minutes=1))
            _scheduled_run(session, edge, timedelta(hours=12))  # exactly 2x: not late yet

            report = collection_gap_report(session, now=NOW)

            assert report.evaluated_sources == 4
            assert {gap.source_definition_id for gap in report.overdue_sources} == {
                late.id,
                never.id,
            }
            assert report.global_overdue is False
            assert report.global_cadence_seconds == 6 * 3600
            assert report.last_scheduled_run_at == NOW - timedelta(hours=1)
            check = describe_collection_gap(report)
            assert check.status == WARN
            assert "2 source(s) overdue" in check.detail

            # Twelve hours and a minute later nothing has run anywhere: global gap too.
            later = collection_gap_report(session, now=NOW + timedelta(hours=12, minutes=1))
            assert later.global_overdue is True
        finally:
            session.rollback()


@_db
def test_healthy_schedule_is_ok() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        try:
            session.execute(update(SourceDefinitionModel).values(enabled=False))
            source = _source(session, "0 0 * * *")
            _scheduled_run(session, source, timedelta(hours=30))
            report = collection_gap_report(session, now=NOW)
            assert not report.alarming
            assert describe_collection_gap(report).status == OK
        finally:
            session.rollback()


@_db
def test_worker_passes_are_recorded_and_pruned() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    job = f"alarm_test_{uuid4().hex[:8]}"
    with observe_job(engine, job_name=job, interval=timedelta(seconds=60)) as correlation:
        from opportunity_radar.operations.service import annotate_pass

        annotate_pass(engine, correlation, due_sources=7, completed=5)
    try:
        with pytest.raises(RuntimeError):
            with observe_job(engine, job_name=job, interval=timedelta(seconds=60)):
                raise RuntimeError("boom")
        with Session(engine) as session:
            passes = recent_passes(session, job)
            assert [row.success for row in passes] == [False, True]
            assert passes[1].due_sources == 7
            assert passes[1].details == {"completed": 5}
            assert passes[1].duration_ms is not None
    finally:
        from sqlalchemy import delete

        from opportunity_radar.operations.models import (
            WorkerJobStateModel,
            WorkerPassHistoryModel,
        )

        with Session(engine) as session:
            session.execute(
                delete(WorkerPassHistoryModel).where(WorkerPassHistoryModel.job_name == job)
            )
            session.execute(delete(WorkerJobStateModel).where(WorkerJobStateModel.job_name == job))
            session.commit()
