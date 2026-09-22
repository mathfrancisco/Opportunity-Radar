"""Retention takes the body and leaves the envelope, once, and says so in writing."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    PayloadRetentionEventModel,
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.operations.retention import (
    RETENTION_POLICY_VERSION,
    PayloadRetentionService,
)
from opportunity_radar.opportunities.models import NormalizationResultModel
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


class _Fixture:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="manual",
            name=f"retention probe {uuid4().hex[:8]}",
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
        self.raw_item_ids: list[UUID] = []

    def raw_item(
        self, *, stored_at: datetime, normalized: bool = True
    ) -> RawItemModel:
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
            payload={"title": "Retention probe"}, stored_at=stored_at
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
        self.raw_item_ids.append(item.id)
        return item

    def cleanup(self) -> None:
        self.session.execute(
            delete(PayloadRetentionEventModel).where(
                PayloadRetentionEventModel.raw_item_id.in_(self.raw_item_ids)
            )
        )
        self.session.execute(
            delete(NormalizationResultModel).where(
                NormalizationResultModel.raw_item_id.in_(self.raw_item_ids)
            )
        )
        self.session.execute(
            delete(RawItemPayloadModel).where(
                RawItemPayloadModel.raw_item_id.in_(self.raw_item_ids)
            )
        )
        self.session.execute(
            delete(RawItemModel).where(RawItemModel.id.in_(self.raw_item_ids))
        )
        self.session.execute(
            delete(SourceRunModel).where(SourceRunModel.id == self.run.id)
        )
        self.session.execute(
            delete(SourceDefinitionModel).where(
                SourceDefinitionModel.id == self.source.id
            )
        )
        self.session.commit()


def _service(session: Session) -> PayloadRetentionService:
    return PayloadRetentionService(session, retention_days=365)


def test_only_old_and_finished_payloads_expire() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            due = fixture.raw_item(stored_at=NOW - timedelta(days=400))
            recent = fixture.raw_item(stored_at=NOW - timedelta(days=10))
            pending = fixture.raw_item(
                stored_at=NOW - timedelta(days=400), normalized=False
            )

            outcome = _service(session).expire_due_payloads(now=NOW)

            assert outcome.expired == 1
            assert outcome.retention_days == 365
            session.expire_all()
            assert session.get(RawItemPayloadModel, due.id).payload is None
            assert session.get(RawItemPayloadModel, recent.id).payload is not None
            assert session.get(RawItemPayloadModel, pending.id).payload is not None
        finally:
            fixture.cleanup()


def test_the_envelope_and_its_provenance_survive_the_expiry() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = fixture.raw_item(stored_at=NOW - timedelta(days=400))
            identity = (item.id, item.payload_hash, item.identity_key, item.external_id)

            _service(session).expire_due_payloads(now=NOW)

            session.expire_all()
            envelope = session.get(RawItemModel, item.id)
            assert envelope is not None
            assert (
                envelope.id,
                envelope.payload_hash,
                envelope.identity_key,
                envelope.external_id,
            ) == identity
            assert envelope.source_run_id == fixture.run.id
            assert envelope.source_definition_id == fixture.source.id
            assert envelope.payload is None
            assert envelope.payload_retained is False
            assert envelope.payload_expired_at is not None
        finally:
            fixture.cleanup()


def test_every_expiry_is_recorded_once() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = fixture.raw_item(stored_at=NOW - timedelta(days=400))

            _service(session).expire_due_payloads(now=NOW)
            second = _service(session).expire_due_payloads(now=NOW)

            assert second.expired == 0
            events = list(
                session.scalars(
                    select(PayloadRetentionEventModel).where(
                        PayloadRetentionEventModel.raw_item_id == item.id
                    )
                )
            )
            assert len(events) == 1
            assert events[0].retention_policy_version == RETENTION_POLICY_VERSION
            assert events[0].retention_days == 365
            assert events[0].payload_hash == item.payload_hash
            assert events[0].source_definition_id == fixture.source.id
        finally:
            fixture.cleanup()


def test_a_shorter_policy_is_honoured() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            fixture.raw_item(stored_at=NOW - timedelta(days=40))

            outcome = PayloadRetentionService(
                session, retention_days=30
            ).expire_due_payloads(now=NOW)

            assert outcome.expired == 1
            assert outcome.retention_days == 30
        finally:
            fixture.cleanup()


def test_a_non_positive_policy_is_rejected() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        with pytest.raises(ValueError, match="retention_days"):
            PayloadRetentionService(session, retention_days=0)
