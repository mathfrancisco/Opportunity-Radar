"""R55-E6: superseded, normalized raw items lose their snapshot; nothing else is touched.

The retention commits on its own sessions, so the fixture commits and cleans up by hand and
every assertion is made on the fixture's own rows.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.operations.data_reduction import run_data_reduction
from opportunity_radar.operations.raw_item_retention import (
    LEAN_KEY,
    lean_superseded_raw_items,
)
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)
_SNAPSHOT = {"version": 1, "title": "Probe", "description": "x" * 2000, "metadata": {"a": 1}}


class _Fixture:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="manual",
            name=f"lean probe {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        self.run = SourceRunModel(
            id=uuid4(),
            source_definition_id=self.source.id,
            execution_trigger="ON_DEMAND",
            status="SUCCEEDED",
            started_at=NOW,
            finished_at=NOW,
        )
        session.add_all([self.source, self.run])
        self.opportunity = OpportunityModel(
            fingerprint=uuid4().hex,
            fingerprint_version="v1",
            canonical_title="Lean probe",
            normalized_title="lean probe",
            work_mode="REMOTE",
            seniority="UNKNOWN",
            contract_type="FULL_TIME",
            lifecycle_status="ACTIVE",
            first_seen_at=NOW,
            role_family="UNKNOWN",
            version=1,
        )
        session.add(self.opportunity)
        session.commit()
        self.identity = f"external:{uuid4().hex[:10]}"
        self.raw_ids: list[UUID] = []
        self.occurrence: SourceOccurrenceModel | None = None

    def raw_item(
        self,
        *,
        age_days: int = 5,
        status: str | None = "SUCCEEDED",
        version: str = NORMALIZER_VERSION,
        current: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RawItemModel:
        item = RawItemModel(
            id=uuid4(),
            source_run_id=self.run.id,
            source_definition_id=self.source.id,
            external_id="probe-ext",
            identity_key=self.identity,
            payload_hash=uuid4().hex + uuid4().hex,
            semantic_hash=uuid4().hex + uuid4().hex,
            semantic_hash_version="v1",
            fetched_at=NOW - timedelta(days=age_days),
            item_metadata=metadata
            if metadata is not None
            else {"parser_version": "p1", "collected_item_v1": dict(_SNAPSHOT)},
        )
        item.payload_record = RawItemPayloadModel(payload={"title": "Probe"})
        self.session.add(item)
        self.session.flush()
        self.raw_ids.append(item.id)
        if current or status is not None:
            if self.occurrence is None:
                self.occurrence = SourceOccurrenceModel(
                    id=uuid4(),
                    opportunity_id=self.opportunity.id,
                    raw_item_id=item.id,
                    source_definition_id=self.source.id,
                    external_id="probe-ext",
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                    last_seen_run_id=self.run.id,
                )
                self.session.add(self.occurrence)
                self.session.flush()
            elif current:
                self.occurrence.raw_item_id = item.id
                self.session.flush()
        if status is not None:
            assert self.occurrence is not None
            failed = status == "FAILED"
            self.session.add(
                NormalizationResultModel(
                    raw_item_id=item.id,
                    opportunity_id=None if failed else self.opportunity.id,
                    source_occurrence_id=None if failed else self.occurrence.id,
                    status=status,
                    identity_decision=None if failed else "REFRESHED",
                    error_summary="probe" if failed else None,
                    normalizer_version=version,
                )
            )
        self.session.commit()
        return item

    def metadata(self, item: RawItemModel) -> dict[str, Any]:
        self.session.expire_all()
        loaded = self.session.get(RawItemModel, item.id)
        assert loaded is not None
        return dict(loaded.item_metadata)

    def cleanup(self) -> None:
        from opportunity_radar.opportunities.models import SourceOccurrenceObservationModel

        s = self.session
        s.rollback()
        s.execute(
            delete(SourceOccurrenceObservationModel).where(
                SourceOccurrenceObservationModel.raw_item_id.in_(self.raw_ids)
            )
        )
        s.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id.in_(self.raw_ids)
            )
        )
        s.execute(
            delete(SourceOccurrenceModel).where(
                SourceOccurrenceModel.opportunity_id == self.opportunity.id
            )
        )
        s.execute(delete(RawItemPayloadModel).where(RawItemPayloadModel.raw_item_id.in_(self.raw_ids)))
        s.execute(delete(RawItemModel).where(RawItemModel.id.in_(self.raw_ids)))
        s.execute(delete(OpportunityModel).where(OpportunityModel.id == self.opportunity.id))
        s.execute(delete(SourceRunModel).where(SourceRunModel.id == self.run.id))
        s.execute(delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id))
        s.commit()


def _engine() -> Any:
    return create_database_engine(os.environ["DATABASE_URL"])


def test_apply_shrinks_a_superseded_normalized_item_and_keeps_the_latest() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            old = fixture.raw_item(age_days=6, current=True)
            latest = fixture.raw_item(age_days=5, current=True)
            old_hash = old.payload_hash

            outcome = lean_superseded_raw_items(engine, retention_days=2, dry_run=False)

            assert outcome.raw_items >= 1 and outcome.complete
            shrunk = fixture.metadata(old)
            assert shrunk == {"parser_version": "p1", LEAN_KEY: "e6-v1"}
            assert fixture.metadata(latest)["collected_item_v1"] == _SNAPSHOT
            session.expire_all()
            row = session.get(RawItemModel, old.id)
            assert row is not None and row.payload_hash == old_hash  # envelope intact
            assert row.identity_key == fixture.identity and row.semantic_hash

            # Running again is a no-op for this item.
            again = lean_superseded_raw_items(engine, retention_days=2, dry_run=False)
            assert fixture.metadata(old) == shrunk and again.raw_items >= 0
        finally:
            fixture.cleanup()


def test_dry_run_only_counts() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            old = fixture.raw_item(age_days=6, current=True)
            fixture.raw_item(age_days=5, current=True)

            outcome = lean_superseded_raw_items(engine, retention_days=2, dry_run=True)

            assert outcome.raw_items >= 1 and outcome.batches == 0
            assert fixture.metadata(old)["collected_item_v1"] == _SNAPSHOT
        finally:
            fixture.cleanup()


def test_pending_failed_stale_version_young_and_proposal_items_are_untouched() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            fixture.raw_item(age_days=9, current=True)  # becomes superseded below
            pending = fixture.raw_item(age_days=8, status=None)
            failed = fixture.raw_item(age_days=8, status="FAILED")
            old_version = fixture.raw_item(age_days=8, version="v0-old")
            young = fixture.raw_item(age_days=0)
            proposal = fixture.raw_item(
                age_days=8,
                metadata={"source_proposal_candidate": True, "collected_item_v1": dict(_SNAPSHOT)},
            )
            current = fixture.raw_item(age_days=7, current=True)

            lean_superseded_raw_items(engine, retention_days=2, dry_run=False)

            for kept in (pending, failed, old_version, young, proposal, current):
                assert fixture.metadata(kept)["collected_item_v1"] == _SNAPSHOT
        finally:
            fixture.cleanup()


def test_the_item_the_occurrence_points_at_is_never_shrunk() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            only = fixture.raw_item(age_days=30, current=True)

            lean_superseded_raw_items(engine, retention_days=2, dry_run=False)

            assert fixture.metadata(only)["collected_item_v1"] == _SNAPSHOT
        finally:
            fixture.cleanup()


def test_dedup_of_an_unchanged_recollection_still_matches_a_shrunk_item() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            old = fixture.raw_item(age_days=6, current=True)
            fixture.raw_item(age_days=5, current=True)
            lean_superseded_raw_items(engine, retention_days=2, dry_run=False)
            assert LEAN_KEY in fixture.metadata(old)

            found = AcquisitionRepository(session).raw_item_by_envelope(
                source_id=fixture.source.id,
                identity_key=old.identity_key,
                payload_hash=old.payload_hash,
                semantic_hash=old.semantic_hash or "",
                semantic_hash_version=old.semantic_hash_version or "",
            )
            assert found is not None and found.id == old.id
        finally:
            fixture.cleanup()


def test_a_shrunk_item_is_not_offered_for_normalization() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            old = fixture.raw_item(age_days=6, current=True)
            fixture.raw_item(age_days=5, current=True)
            lean_superseded_raw_items(engine, retention_days=2, dry_run=False)
            # A normalizer bump leaves every item without a result for the new version.
            pending = OpportunityRepository(session).pending_raw_item_ids(10_000, "v-next")
            assert old.id not in pending
        finally:
            fixture.cleanup()


def test_data_reduction_is_gated_by_the_apply_flag() -> None:
    engine = _engine()
    kwargs: dict[str, Any] = {"payload_retention_days": 2, "assessment_retention_days": 1}
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            old = fixture.raw_item(age_days=6, current=True)
            fixture.raw_item(age_days=5, current=True)

            dry = run_data_reduction(engine, apply=False, **kwargs)
            assert dry.raw_items_lean >= 1 and not dry.errors
            assert fixture.metadata(old)["collected_item_v1"] == _SNAPSHOT

            applied = run_data_reduction(engine, apply=True, **kwargs)
            assert applied.raw_items_lean >= 1 and not applied.errors
            assert LEAN_KEY in fixture.metadata(old)
        finally:
            fixture.cleanup()


def test_a_shrunk_item_fails_fast_in_normalization_and_departments() -> None:
    from types import SimpleNamespace

    from opportunity_radar.opportunities.service import (
        NormalizationError,
        _latest_occurrence_departments,
        _normalization_input,
    )

    evidence = SimpleNamespace(raw_item=SimpleNamespace(item_metadata={LEAN_KEY: "e6-v1"}))
    with pytest.raises(NormalizationError, match="shrunk by retention"):
        _normalization_input(evidence)  # type: ignore[arg-type]

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            fixture.raw_item(
                age_days=5, current=True, metadata={"parser_version": "p1", LEAN_KEY: "e6-v1"}
            )
            with pytest.raises(NormalizationError, match="shrunk by retention"):
                _latest_occurrence_departments(session, fixture.opportunity.id)
        finally:
            fixture.cleanup()


def test_the_update_itself_refuses_an_item_an_occurrence_points_at() -> None:
    from sqlalchemy import text

    from opportunity_radar.operations.raw_item_retention import _SHRINK

    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            current = fixture.raw_item(age_days=5, current=True)
            # Simulates the race: the id was locked as eligible, then an occurrence took it.
            with Session(engine) as other, other.begin():
                result = other.execute(text(_SHRINK), {"ids": [current.id], "marker": "e6-v1"})
                assert result.rowcount == 0  # type: ignore[attr-defined]
            assert fixture.metadata(current)["collected_item_v1"] == _SNAPSHOT
        finally:
            fixture.cleanup()
