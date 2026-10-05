"""A job vanishing from two complete runs in a row closes it; reappearing reopens it.

Only a complete run may change anything here: a partial or failed run tells us nothing
about what the board still has, so absence from it is not evidence.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.opportunities.service import OpportunityService
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


class _Fixture:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="manual",
            name=f"closure probe {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(self.source)
        session.commit()
        self.run_ids: list[UUID] = []
        self.raw_item_ids: list[UUID] = []
        self.opportunity_id: UUID | None = None
        self.occurrence_id: UUID | None = None

    def run(self, *, complete: bool, status: str = "SUCCEEDED") -> SourceRunModel:
        moment = NOW + timedelta(seconds=len(self.run_ids))
        model = SourceRunModel(
            id=uuid4(),
            source_definition_id=self.source.id,
            execution_trigger="SCHEDULED",
            status=status,
            started_at=moment,
            finished_at=moment + timedelta(seconds=1),
            complete=complete,
        )
        self.session.add(model)
        self.session.commit()
        self.run_ids.append(model.id)
        return model

    def opportunity_seen_in(self, run: SourceRunModel) -> OpportunityModel:
        raw_item = RawItemModel(
            id=uuid4(),
            source_run_id=run.id,
            source_definition_id=self.source.id,
            external_id=f"probe-{uuid4().hex[:8]}",
            identity_key=f"external:probe-{uuid4().hex[:8]}",
            payload_hash=uuid4().hex + uuid4().hex,
            item_metadata={},
        )
        self.session.add(raw_item)
        self.session.flush()
        self.raw_item_ids.append(raw_item.id)

        opportunity = OpportunityModel(
            id=uuid4(),
            fingerprint=uuid4().hex + uuid4().hex,
            fingerprint_version="v1",
            canonical_title="Backend Engineer",
            normalized_title="backend engineer",
            work_mode="UNKNOWN",
            seniority="UNKNOWN",
            contract_type="UNKNOWN",
            lifecycle_status="ACTIVE",
            version=1,
        )
        self.session.add(opportunity)
        self.session.flush()
        self.opportunity_id = opportunity.id

        occurrence = SourceOccurrenceModel(
            id=uuid4(),
            opportunity_id=opportunity.id,
            raw_item_id=raw_item.id,
            source_definition_id=self.source.id,
            external_id=raw_item.external_id,
            first_seen_at=run.started_at,
            last_seen_at=run.started_at,
            last_seen_run_id=run.id,
        )
        self.session.add(occurrence)
        self.session.commit()
        self.occurrence_id = occurrence.id
        return opportunity

    def touch(self, run: SourceRunModel) -> None:
        """Simulate normalization seeing the occurrence again in `run`."""
        occurrence = self.session.get(SourceOccurrenceModel, self.occurrence_id)
        assert occurrence is not None
        occurrence.last_seen_run_id = run.id
        occurrence.last_seen_at = run.started_at
        self.session.commit()

    def opportunity(self) -> OpportunityModel:
        opportunity = self.session.get(OpportunityModel, self.opportunity_id)
        assert opportunity is not None
        return opportunity

    def cleanup(self) -> None:
        self.session.execute(
            delete(SourceOccurrenceModel).where(
                SourceOccurrenceModel.source_definition_id == self.source.id
            )
        )
        self.session.execute(
            delete(OpportunityModel).where(OpportunityModel.id == self.opportunity_id)
        )
        self.session.execute(
            delete(RawItemModel).where(RawItemModel.id.in_(self.raw_item_ids))
        )
        self.session.execute(
            delete(SourceRunModel).where(SourceRunModel.id.in_(self.run_ids))
        )
        self.session.execute(
            delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id)
        )
        self.session.commit()


def test_partial_and_failed_runs_never_close_anything() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        service = OpportunityService(session)
        try:
            first = fixture.run(complete=True)
            fixture.opportunity_seen_in(first)

            partial = fixture.run(complete=False, status="PARTIAL")
            failed = fixture.run(complete=False, status="FAILED")
            # Neither run saw the occurrence, but neither is complete.
            service.reconcile_run_closures(partial.id)
            service.reconcile_run_closures(failed.id)

            assert fixture.opportunity().lifecycle_status == "ACTIVE"
        finally:
            fixture.cleanup()


def test_missing_from_two_consecutive_complete_runs_closes_with_evidence() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        service = OpportunityService(session)
        try:
            first = fixture.run(complete=True)
            fixture.opportunity_seen_in(first)

            second = fixture.run(complete=True)
            service.reconcile_run_closures(second.id)
            assert fixture.opportunity().lifecycle_status == "ACTIVE"

            third = fixture.run(complete=True)
            service.reconcile_run_closures(third.id)

            closed = fixture.opportunity()
            assert closed.lifecycle_status == "CLOSED"
            assert closed.closure_evidence == {
                "closed_by_run_ids": [str(second.id), str(third.id)]
            }
        finally:
            fixture.cleanup()


def test_reappearing_reopens_a_closed_opportunity() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        service = OpportunityService(session)
        try:
            first = fixture.run(complete=True)
            fixture.opportunity_seen_in(first)
            second = fixture.run(complete=True)
            service.reconcile_run_closures(second.id)
            third = fixture.run(complete=True)
            service.reconcile_run_closures(third.id)
            assert fixture.opportunity().lifecycle_status == "CLOSED"

            fourth = fixture.run(complete=True)
            fixture.touch(fourth)
            service.reconcile_run_closures(fourth.id)

            reopened = fixture.opportunity()
            assert reopened.lifecycle_status == "ACTIVE"
            assert reopened.closure_evidence["reopened_by_run_id"] == str(fourth.id)
        finally:
            fixture.cleanup()


def _second_source_occurrence(
    session: Session, fixture: _Fixture, *, seen_in_latest_complete: bool
) -> tuple[UUID, list[UUID], UUID]:
    """A second source whose occurrence of the same opportunity is (not) still live."""
    other = SourceDefinitionModel(
        id=uuid4(),
        source_type="manual",
        name=f"closure probe other {uuid4().hex[:8]}",
        enabled=True,
        configuration={},
        rate_limit_policy={},
    )
    session.add(other)
    session.commit()
    runs = []
    for offset in range(2):
        moment = NOW + timedelta(seconds=offset)
        run = SourceRunModel(
            id=uuid4(),
            source_definition_id=other.id,
            execution_trigger="SCHEDULED",
            status="SUCCEEDED",
            started_at=moment,
            finished_at=moment + timedelta(seconds=1),
            complete=True,
        )
        session.add(run)
        runs.append(run)
    session.commit()
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=runs[0].id,
        source_definition_id=other.id,
        external_id=f"probe-{uuid4().hex[:8]}",
        identity_key=f"external:probe-{uuid4().hex[:8]}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    session.add(raw_item)
    session.flush()
    fixture.raw_item_ids.append(raw_item.id)
    seen_run = runs[1] if seen_in_latest_complete else runs[0]
    session.add(
        SourceOccurrenceModel(
            id=uuid4(),
            opportunity_id=fixture.opportunity_id,
            raw_item_id=raw_item.id,
            source_definition_id=other.id,
            external_id=raw_item.external_id,
            first_seen_at=runs[0].started_at,
            last_seen_at=seen_run.started_at,
            last_seen_run_id=seen_run.id,
        )
    )
    session.commit()
    return other.id, [run.id for run in runs], raw_item.id


def _cleanup_other(session: Session, other_id: UUID, run_ids: list[UUID]) -> None:
    session.execute(
        delete(SourceOccurrenceModel).where(
            SourceOccurrenceModel.source_definition_id == other_id
        )
    )
    session.execute(delete(RawItemModel).where(RawItemModel.source_definition_id == other_id))
    session.execute(delete(SourceRunModel).where(SourceRunModel.id.in_(run_ids)))
    session.execute(
        delete(SourceDefinitionModel).where(SourceDefinitionModel.id == other_id)
    )
    session.commit()


def test_an_occurrence_live_in_another_source_keeps_the_opportunity_open() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        service = OpportunityService(session)
        other_id: UUID | None = None
        other_runs: list[UUID] = []
        try:
            first = fixture.run(complete=True)
            fixture.opportunity_seen_in(first)
            other_id, other_runs, _ = _second_source_occurrence(
                session, fixture, seen_in_latest_complete=True
            )

            second = fixture.run(complete=True)
            service.reconcile_run_closures(second.id)
            third = fixture.run(complete=True)
            service.reconcile_run_closures(third.id)

            # Source A dropped it for two runs, source B still lists it.
            assert fixture.opportunity().lifecycle_status == "ACTIVE"
        finally:
            session.rollback()
            if other_id is not None:
                _cleanup_other(session, other_id, other_runs)
            fixture.cleanup()


def test_closes_when_every_source_dropped_the_opportunity() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        service = OpportunityService(session)
        other_id: UUID | None = None
        other_runs: list[UUID] = []
        try:
            first = fixture.run(complete=True)
            fixture.opportunity_seen_in(first)
            other_id, other_runs, _ = _second_source_occurrence(
                session, fixture, seen_in_latest_complete=False
            )

            second = fixture.run(complete=True)
            service.reconcile_run_closures(second.id)
            third = fixture.run(complete=True)
            service.reconcile_run_closures(third.id)

            assert fixture.opportunity().lifecycle_status == "CLOSED"
        finally:
            session.rollback()
            if other_id is not None:
                _cleanup_other(session, other_id, other_runs)
            fixture.cleanup()
