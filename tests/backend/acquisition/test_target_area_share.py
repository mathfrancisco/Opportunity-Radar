"""F50-04: `AcquisitionRepository.target_area_share` over a source's last complete runs."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel, SourceRunModel
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _source(session: Session) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        source_type="example", name=f"Share {uuid4().hex[:8]}", enabled=True, configuration={}
    )
    session.add(source)
    session.flush()
    return source


def _run(
    session: Session,
    source: SourceDefinitionModel,
    *,
    age: int,
    target: int | None,
    off_target: int | None,
    complete: bool = True,
) -> None:
    started = datetime(2026, 10, 1, tzinfo=UTC) - timedelta(days=age)
    session.add(
        SourceRunModel(
            source_definition_id=source.id,
            status="SUCCEEDED",
            started_at=started,
            finished_at=started,
            complete=complete,
            items_target_area=target,
            items_off_target=off_target,
        )
    )
    session.flush()


def test_share_is_the_pooled_ratio_of_the_last_three_complete_runs() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        source = _source(session)
        _run(session, source, age=1, target=2, off_target=8)
        _run(session, source, age=2, target=3, off_target=7)
        _run(session, source, age=3, target=1, off_target=9)
        # Older than the window: must not move the share.
        _run(session, source, age=4, target=10, off_target=0)

        share = AcquisitionRepository(session).target_area_share(source.id)

        assert share == pytest.approx(0.2)
        session.rollback()


def test_an_incomplete_or_unmeasured_run_is_ignored() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        source = _source(session)
        _run(session, source, age=1, target=2, off_target=8)
        _run(session, source, age=2, target=10, off_target=0, complete=False)
        _run(session, source, age=3, target=None, off_target=None)
        _run(session, source, age=4, target=3, off_target=7)
        _run(session, source, age=5, target=1, off_target=9)

        share = AcquisitionRepository(session).target_area_share(source.id)

        assert share == pytest.approx(0.2)
        session.rollback()


def test_fewer_than_three_measured_runs_gives_no_share() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        source = _source(session)
        _run(session, source, age=1, target=2, off_target=8)
        _run(session, source, age=2, target=3, off_target=7)

        assert AcquisitionRepository(session).target_area_share(source.id) is None
        session.rollback()
