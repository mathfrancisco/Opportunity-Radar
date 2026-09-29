"""F20-39 regression coverage for normalization after delta collection."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import CollectionMode, CollectionRequest
from opportunity_radar.opportunities import service as opportunity_service_module
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.service import OpportunityService
from tests.backend.acquisition.test_delta_presence_resume import (
    _engine,
    _Fixture,
    _item,
    _StaticCollector,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _collect(fixture: _Fixture, collector: _StaticCollector):
    return asyncio.run(
        fixture.service(collector).execute(
            fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
        )
    )


def _described_item(source_type: str, *, external_id: str, title: str, description: str):
    return replace(
        _item(
            source_type,
            external_id=external_id,
            title=title,
            description=description,
        ),
        description=description,
    )


def test_stale_material_evidence_does_not_regress_canonical_content_or_enrichment() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            stale = _described_item(
                fixture.source_type,
                external_id="job-1",
                title="Junior Java Engineer",
                description="Required Java. Salary USD 20000 per year.",
            )
            current = _described_item(
                fixture.source_type,
                external_id="job-1",
                title="Senior Python Engineer",
                description="Required Python. Salary USD 120000 per year.",
            )
            collector = _StaticCollector(fixture.source_type, [[stale], [current]])
            _collect(fixture, collector)
            _collect(fixture, collector)
            stale_raw, current_raw = fixture.raw_items()
            service = OpportunityService(session)

            service.normalize(current_raw.id)
            stale_result = service.normalize(stale_raw.id)
            opportunity = stale_result.opportunity
            assert opportunity is not None
            assert opportunity.canonical_title == "Senior Python Engineer"
            assert {skill.canonical_name for skill in opportunity.skills} == {"python"}
            assert {item.amount_min for item in opportunity.compensations} == {120000}
        finally:
            fixture.cleanup()


def test_revisits_before_normalization_link_all_observations_and_keep_latest_presence() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            item = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            collector = _StaticCollector(fixture.source_type, [[item], [item]])
            first_run = _collect(fixture, collector)
            latest_run = _collect(fixture, collector)
            [raw_item] = fixture.raw_items()

            result = OpportunityService(session).normalize(raw_item.id)
            occurrence = result.source_occurrence
            assert occurrence is not None
            assert occurrence.last_seen_run_id == latest_run.id
            observations = list(
                session.scalars(
                    select(SourceOccurrenceObservationModel).where(
                        SourceOccurrenceObservationModel.source_occurrence_id == occurrence.id
                    )
                )
            )
            assert {item.source_run_id for item in observations} == {first_run.id, latest_run.id}
            assert occurrence.last_seen_at == max(item.observed_at for item in observations)
        finally:
            fixture.cleanup()


def test_material_content_replaces_canonical_evidence_while_presence_uses_latest_visit() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            original = _item(fixture.source_type, external_id="job-1", title="Backend Engineer")
            changed = _described_item(
                fixture.source_type,
                external_id="job-1",
                title="Backend Engineer",
                description="Required Python. Salary USD 120000 per year.",
            )
            collector = _StaticCollector(fixture.source_type, [[original], [changed], [changed]])
            _collect(fixture, collector)
            _collect(fixture, collector)
            latest_run = _collect(fixture, collector)
            original_raw, changed_raw = fixture.raw_items()
            service = OpportunityService(session)

            service.normalize(original_raw.id)
            result = service.normalize(changed_raw.id)
            occurrence = result.source_occurrence
            assert occurrence is not None
            assert occurrence.raw_item_id == changed_raw.id
            assert result.opportunity is not None
            assert result.opportunity.canonical_title == "Backend Engineer"
            assert {skill.canonical_name for skill in result.opportunity.skills} == {"python"}
            assert {item.amount_min for item in result.opportunity.compensations} == {120000}
            assert occurrence.last_seen_run_id == latest_run.id
        finally:
            fixture.cleanup()


@pytest.mark.parametrize("prior_status", ["FAILED", "REVIEW_REQUIRED"])
def test_non_successful_prior_normalization_cannot_take_the_cosmetic_shortcut(
    monkeypatch: pytest.MonkeyPatch, prior_status: str
) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            first = _item(
                fixture.source_type,
                external_id="job-1",
                title="Backend Engineer",
                description="Build things.  Ship things.",
            )
            cosmetic = _item(
                fixture.source_type,
                external_id="job-1",
                title="Backend Engineer",
                description="Build things. Ship things.",
            )
            collector = _StaticCollector(fixture.source_type, [[first], [cosmetic]])
            _collect(fixture, collector)
            [first_raw] = fixture.raw_items()
            current_version = opportunity_service_module.NORMALIZER_VERSION
            monkeypatch.setattr(opportunity_service_module, "NORMALIZER_VERSION", "older-version")
            prior = OpportunityService(session).normalize(first_raw.id)
            monkeypatch.setattr(opportunity_service_module, "NORMALIZER_VERSION", current_version)
            failed_values = {
                "raw_item_id": first_raw.id,
                "status": prior_status,
                "normalizer_version": current_version,
                "reasons": [{"code": "TEST_FAILURE"}],
            }
            if prior_status == "FAILED":
                failed_values["identity_decision"] = None
                failed_values["error_summary"] = "test failure"
            else:
                failed_values.update(
                    opportunity=prior.opportunity,
                    source_occurrence=prior.source_occurrence,
                    identity_decision="REVIEW",
                )
            session.add(
                NormalizationResultModel(**failed_values)  # type: ignore[arg-type]
            )
            session.commit()
            _collect(fixture, collector)
            _, cosmetic_raw = fixture.raw_items()

            result = OpportunityService(session).normalize(cosmetic_raw.id)
            assert not any(
                reason.get("code") == "COSMETIC_CHANGE_SEMANTIC_HASH_UNCHANGED"
                for reason in result.reasons
            )
        finally:
            fixture.cleanup()
