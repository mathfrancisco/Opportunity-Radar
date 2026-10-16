"""R55-B1: bumping NORMALIZER_VERSION to v7 renormalizes stored rows, and retention waits for it.

The v7 bump is what lets the clean-HTML, `seniority-v7` and `regions-v2` rules (PR #101) reach
rows normalized earlier. Retention only expires a payload that has a result at the *current*
version, so an old-version item keeps its body until it has been renormalized; and an item
whose body is already gone renormalizes from its stored snapshot or description instead.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.acquisition.models import RawItemModel, RawItemPayloadModel
from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY
from opportunity_radar.operations.retention import PayloadRetentionService
from opportunity_radar.opportunities.models import NormalizationResultModel, OpportunityModel
from opportunity_radar.opportunities.service import (
    NORMALIZER_VERSION,
    OpportunityService,
    recompute_from_stored_description,
)
from tests.backend.acquisition.test_delta_presence_resume import (
    _engine,
    _Fixture,
    _item,
    _StaticCollector,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

LONG_AGO = datetime.now(UTC) - timedelta(days=30)


def test_the_normalizer_is_at_v7() -> None:
    assert NORMALIZER_VERSION == "v7"


def _collect_and_normalize(session: Session, fixture: _Fixture) -> RawItemModel:
    item = _item(
        fixture.source_type,
        external_id="v7-job",
        title="Backend Engineer",
        description="Required Python.",
    )
    collector = _StaticCollector(fixture.source_type, [[item]])
    asyncio.run(
        fixture.service(collector).execute(
            fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
        )
    )
    [raw_item] = fixture.raw_items()
    OpportunityService(session).normalize(raw_item.id)
    return raw_item


def _age_payload(session: Session, raw_item: RawItemModel) -> None:
    session.execute(
        update(RawItemPayloadModel)
        .where(RawItemPayloadModel.raw_item_id == raw_item.id)
        .values(stored_at=LONG_AGO)
    )
    session.commit()


def _as_old_version(session: Session, raw_item: RawItemModel) -> None:
    """Make the raw item look as it did before the bump: its only result is a v6 one."""
    session.execute(
        update(NormalizationResultModel)
        .where(NormalizationResultModel.raw_item_id == raw_item.id)
        .values(normalizer_version="v6")
    )
    session.commit()


def _expire(session: Session) -> int:
    return PayloadRetentionService(session, retention_days=1).expire_due_payloads().expired


def test_retention_keeps_the_payload_of_an_old_version_item_until_it_is_renormalized() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raw_item = _collect_and_normalize(session, fixture)
            _age_payload(session, raw_item)
            _as_old_version(session, raw_item)

            assert _expire(session) == 0  # only a v6 result: pending work outranks the calendar
            session.expire_all()
            assert session.get(RawItemPayloadModel, raw_item.id).payload is not None

            OpportunityService(session).normalize(raw_item.id)  # renormalized at v7

            assert _expire(session) == 1
            session.expire_all()
            assert session.get(RawItemPayloadModel, raw_item.id).payload is None
        finally:
            fixture.cleanup()


def test_an_old_version_item_is_pending_again_for_the_window() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raw_item = _collect_and_normalize(session, fixture)
            service = OpportunityService(session)
            assert raw_item.id not in service.repository.pending_raw_item_ids(500, "v7")

            _as_old_version(session, raw_item)

            assert raw_item.id in service.repository.pending_raw_item_ids(500, NORMALIZER_VERSION)
            batch = service.normalize_pending(limit=500)
            assert batch.processed >= 1
            versions = set(
                session.scalars(
                    select(NormalizationResultModel.normalizer_version).where(
                        NormalizationResultModel.raw_item_id == raw_item.id
                    )
                )
            )
            assert versions == {"v6", "v7"}
        finally:
            fixture.cleanup()


def test_an_item_whose_payload_already_expired_renormalizes_from_its_snapshot() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raw_item = _collect_and_normalize(session, fixture)
            _age_payload(session, raw_item)
            assert _expire(session) == 1  # expired while it still had its current result
            _as_old_version(session, raw_item)  # ... and then the version moved on
            session.expire_all()
            assert session.get(RawItemPayloadModel, raw_item.id).payload is None
            assert COLLECTED_ITEM_V1_KEY in session.get(RawItemModel, raw_item.id).item_metadata

            result = OpportunityService(session).normalize(raw_item.id)

            assert result.normalizer_version == NORMALIZER_VERSION
            assert result.status in {"SUCCEEDED", "REVIEW_REQUIRED"}
            assert result.error_summary is None
        finally:
            fixture.cleanup()


def test_recompute_from_the_stored_description_works_with_the_payload_gone() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raw_item = _collect_and_normalize(session, fixture)
            _age_payload(session, raw_item)
            assert _expire(session) == 1
            opportunity = session.scalar(select(OpportunityModel).where(
                OpportunityModel.id.in_(
                    select(NormalizationResultModel.opportunity_id).where(
                        NormalizationResultModel.raw_item_id == raw_item.id
                    )
                )
            ))
            assert opportunity is not None
            opportunity.description = "We need Docker and Kubernetes. Senior engineer, 8+ years."
            session.commit()
            before = {skill.canonical_name for skill in opportunity.skills}

            changed = recompute_from_stored_description(session, opportunity.id)
            session.commit()

            session.refresh(opportunity)
            after = {skill.canonical_name for skill in opportunity.skills}
            assert changed is True
            assert {"docker", "kubernetes"} <= after
            assert before != after
            assert session.get(RawItemPayloadModel, raw_item.id).payload is None
        finally:
            fixture.cleanup()


def test_a_pre_contract_item_without_payload_fails_cleanly_and_keeps_the_opportunity() -> None:
    """No snapshot and no body: only a new collection can help, and nothing is invented."""
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            raw_item = _collect_and_normalize(session, fixture)
            _age_payload(session, raw_item)
            assert _expire(session) == 1
            metadata = dict(session.get(RawItemModel, raw_item.id).item_metadata)
            metadata.pop(COLLECTED_ITEM_V1_KEY)
            session.execute(
                update(RawItemModel).where(RawItemModel.id == raw_item.id).values(
                    item_metadata=metadata
                )
            )
            _as_old_version(session, raw_item)

            result = OpportunityService(session).normalize(raw_item.id)

            assert result.normalizer_version == NORMALIZER_VERSION
            assert result.status == "FAILED"
            assert result.reasons == [{"code": "PAYLOAD_EXPIRED_RECOLLECTION_REQUIRED"}]
            opportunity_id = session.scalar(
                select(NormalizationResultModel.opportunity_id).where(
                    NormalizationResultModel.raw_item_id == raw_item.id,
                    NormalizationResultModel.normalizer_version == "v6",
                )
            )
            assert opportunity_id is not None
            assert session.get(OpportunityModel, opportunity_id) is not None
            # The stored description cannot recover it either: without a snapshot there is
            # no evidence to rebuild a candidate from, so the recompute is a safe no-op.
            assert recompute_from_stored_description(session, opportunity_id) is False
        finally:
            fixture.cleanup()
