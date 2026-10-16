"""R55-E6: the daily reduction expires finished payloads, prunes, measures, and honours the gate."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    PayloadRetentionEventModel,
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.operations import data_reduction
from opportunity_radar.operations.data_reduction import (
    measure_database_size,
    run_data_reduction,
)
from opportunity_radar.opportunities.models import NormalizationResultModel
from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from opportunity_radar.platform.database import create_database_engine

NOW = datetime.now(UTC)
_KWARGS: dict[str, Any] = {
    "payload_retention_days": 2,
    "assessment_retention_days": 1,
}


class _Fixture:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="manual",
            name=f"reduction probe {uuid4().hex[:8]}",
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
        session.commit()
        self.ids: list[Any] = []

    def raw_item(self, *, age_days: int, normalized: bool = True) -> Any:
        item = RawItemModel(
            id=uuid4(),
            source_run_id=self.run.id,
            source_definition_id=self.source.id,
            external_id=f"probe-{uuid4().hex[:8]}",
            identity_key=f"external:probe-{uuid4().hex[:8]}",
            payload_hash=uuid4().hex + uuid4().hex,
            item_metadata={},
        )
        item.payload_record = RawItemPayloadModel(
            payload={"title": "Reduction probe"}, stored_at=NOW - timedelta(days=age_days)
        )
        self.session.add(item)
        self.session.flush()
        if normalized:
            self.session.add(
                NormalizationResultModel(
                    raw_item_id=item.id,
                    status="FAILED",
                    normalizer_version=NORMALIZER_VERSION,
                    error_summary="probe",
                    reasons=[],
                )
            )
        self.session.commit()
        self.ids.append(item.id)
        return item

    def payload_is_present(self, item: Any) -> bool:
        self.session.expire_all()
        record = self.session.get(RawItemPayloadModel, item.id)
        return record is not None and record.payload is not None

    def cleanup(self) -> None:
        for model, column in (
            (PayloadRetentionEventModel, PayloadRetentionEventModel.raw_item_id),
            (NormalizationResultModel, NormalizationResultModel.raw_item_id),
            (RawItemPayloadModel, RawItemPayloadModel.raw_item_id),
        ):
            self.session.execute(delete(model).where(column.in_(self.ids)))
        self.session.execute(delete(RawItemModel).where(RawItemModel.id.in_(self.ids)))
        self.session.execute(delete(SourceRunModel).where(SourceRunModel.id == self.run.id))
        self.session.execute(
            delete(SourceDefinitionModel).where(SourceDefinitionModel.id == self.source.id)
        )
        self.session.commit()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
class TestAgainstTheDatabase:
    def test_apply_expires_only_old_normalized_payloads(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            fixture = _Fixture(session)
            try:
                old = fixture.raw_item(age_days=5)
                fresh = fixture.raw_item(age_days=0)
                pending = fixture.raw_item(age_days=5, normalized=False)

                report = run_data_reduction(engine, apply=True, **_KWARGS)

                assert report.payloads >= 1 and report.complete and not report.errors
                assert not fixture.payload_is_present(old)
                assert fixture.payload_is_present(fresh)
                assert fixture.payload_is_present(pending)  # not normalized: never expired
                envelope = session.get(RawItemModel, old.id)
                assert envelope is not None and envelope.payload_hash == old.payload_hash
            finally:
                fixture.cleanup()

    def test_without_the_gate_nothing_is_expired_but_it_is_counted(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            fixture = _Fixture(session)
            try:
                old = fixture.raw_item(age_days=5)

                report = run_data_reduction(engine, apply=False, **_KWARGS)

                assert report.applied is False and report.payloads >= 1
                assert fixture.payload_is_present(old)
                assert report.database_size_bytes and report.database_size_bytes > 0
            finally:
                fixture.cleanup()

    def test_size_alert_flag_follows_the_threshold(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        size, alert = measure_database_size(engine, limit_bytes=10**12, alert_ratio=0.7)
        assert size > 0 and alert is False
        _, alert = measure_database_size(engine, limit_bytes=1000, alert_ratio=0.7)
        assert alert is True
        report = run_data_reduction(engine, apply=False, size_limit_bytes=1000, **_KWARGS)
        assert report.size_alert is True


class _Prune:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, raises: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        outer = self

        def prune(_engine: object, **kwargs: Any) -> SimpleNamespace:
            outer.calls.append(kwargs)
            if raises:
                raise RuntimeError("boom")
            return SimpleNamespace(deleted=3)

        monkeypatch.setattr(data_reduction, "prune_superseded_assessments", prune)
        monkeypatch.setattr(data_reduction, "_payloads", lambda *_a: 2)
        monkeypatch.setattr(data_reduction, "measure_database_size", lambda *_a, **_k: (800, True))


def test_assessments_are_pruned_only_when_applying(monkeypatch: pytest.MonkeyPatch) -> None:
    prune = _Prune(monkeypatch)
    applied = run_data_reduction(object(), apply=True, **_KWARGS)  # type: ignore[arg-type]
    dry = run_data_reduction(object(), apply=False, **_KWARGS)  # type: ignore[arg-type]

    assert [call["dry_run"] for call in prune.calls] == [False, True]
    assert all(call["retention_days"] == 1 for call in prune.calls)
    assert (applied.payloads, applied.assessments, applied.size_alert) == (2, 3, True)
    assert applied.complete and dry.complete


def test_a_failing_step_is_reported_and_does_not_hide_the_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _Prune(monkeypatch, raises=True)
    report = run_data_reduction(object(), apply=True, **_KWARGS)  # type: ignore[arg-type]

    assert report.errors == {"assessments": "RuntimeError"}
    assert report.complete is False and report.stopped is False
    assert report.database_size_bytes == 800


def test_a_stop_request_before_the_start_runs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    prune = _Prune(monkeypatch)
    report = run_data_reduction(
        object(),  # type: ignore[arg-type]
        apply=True,
        should_stop=lambda: True,
        **_KWARGS,
    )

    assert report.stopped is True and report.complete is False
    assert prune.calls == [] and report.database_size_bytes is None
