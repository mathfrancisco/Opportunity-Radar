"""F48-09: a source's `external_id` is the identity; the duplicate finder also covers REVIEW."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import CollectedItem, CollectionMode, CollectionRequest
from opportunity_radar.opportunities.models import DuplicateCandidateModel
from opportunity_radar.opportunities.service import OpportunityService
from scripts import backfill_identity_refresh
from tests.backend.acquisition.test_delta_presence_resume import (
    _engine,
    _Fixture,
    _StaticCollector,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _posting(
    source_type: str,
    external_id: str,
    *,
    remote: bool = False,
    company: str | None = None,
    title: str = "Backend Engineer",
    location: str | None = None,
    published_at: datetime | None = None,
) -> CollectedItem:
    return CollectedItem(
        source_type=source_type,
        external_id=external_id,
        title=title,
        company_name=company,
        location_text=location,
        published_at=published_at,
        raw_payload={"id": external_id, "title": title, "remote": remote, "loc": location},
        metadata={"remote": True} if remote else {},
        cursor=external_id,
    )


def _collect(fixture: _Fixture, collector: _StaticCollector) -> None:
    asyncio.run(
        fixture.service(collector).execute(
            fixture.source.id, CollectionRequest(mode=CollectionMode.DISCOVERY)
        )
    )


def _competing_identity_fixture(session: Session) -> _Fixture:
    """job-1 changes into exactly the identity job-2 already owns."""
    fixture = _Fixture(session)
    job_1 = _posting(fixture.source_type, "job-1", company="Acme")
    job_2 = _posting(fixture.source_type, "job-2", remote=True, company="Acme")
    job_1_remote = _posting(fixture.source_type, "job-1", remote=True, company="Acme")
    collector = _StaticCollector(fixture.source_type, [[job_1, job_2], [job_1_remote]])
    _collect(fixture, collector)
    _collect(fixture, collector)
    return fixture


def test_same_external_id_with_new_work_mode_refreshes_the_opportunity() -> None:
    with Session(_engine()) as session:
        fixture = _Fixture(session)
        try:
            before = _posting(fixture.source_type, "job-1", company="Acme")
            after = _posting(fixture.source_type, "job-1", remote=True, company="Acme")
            collector = _StaticCollector(fixture.source_type, [[before], [after]])
            _collect(fixture, collector)
            _collect(fixture, collector)
            first_raw, second_raw = fixture.raw_items()
            service = OpportunityService(session)

            created = service.normalize(first_raw.id)
            assert created.opportunity is not None
            assert created.opportunity.work_mode == "UNKNOWN"
            old_fingerprint = created.opportunity.fingerprint
            version = created.opportunity.version

            result = service.normalize(second_raw.id)

            assert result.identity_decision == "REFRESHED"
            assert result.status == "SUCCEEDED"
            assert result.reasons[0]["code"] == "IDENTITY_REFRESHED_SAME_EXTERNAL_ID"
            opportunity = result.opportunity
            assert opportunity is not None and opportunity.id == created.opportunity.id
            assert opportunity.work_mode == "REMOTE"
            assert opportunity.fingerprint != old_fingerprint
            assert opportunity.version == version + 1
            change = opportunity.closure_evidence["identity_refresh"]
            assert change["previous_fingerprint"] == old_fingerprint
            assert change["fingerprint"] == opportunity.fingerprint
        finally:
            fixture.cleanup()


def test_two_opportunities_competing_for_the_identity_stay_review_required() -> None:
    with Session(_engine()) as session:
        fixture = _competing_identity_fixture(session)
        try:
            first, second, third = fixture.raw_items()
            service = OpportunityService(session)
            original = service.normalize(first.id).opportunity
            competing_result = service.normalize(second.id)
            assert original is not None
            fingerprint = original.fingerprint
            competing = competing_result.opportunity
            assert competing is not None

            result = service.normalize(third.id)

            assert result.status == "REVIEW_REQUIRED"
            reason = result.reasons[0]
            assert reason["code"] == "EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED"
            assert reason["competing_opportunity_id"] == str(competing.id)
            assert reason["candidate_fingerprint"] == competing.fingerprint
            assert reason["candidate_fingerprint_version"] == competing.fingerprint_version
            session.refresh(original)
            assert original.fingerprint == fingerprint
            assert original.work_mode == "UNKNOWN"
        finally:
            fixture.cleanup()


def test_silent_refresh_path_has_no_competing_opportunity_id() -> None:
    """Silent-refresh path has no competing_opportunity_id in the reason."""
    with Session(_engine()) as session:
        fixture = _Fixture(session)
        try:
            before = _posting(fixture.source_type, "job-1", company="Acme")
            after = _posting(fixture.source_type, "job-1", remote=True, company="Acme")
            collector = _StaticCollector(fixture.source_type, [[before], [after]])
            _collect(fixture, collector)
            _collect(fixture, collector)
            first_raw, second_raw = fixture.raw_items()
            service = OpportunityService(session)

            service.normalize(first_raw.id)
            result = service.normalize(second_raw.id)

            # This path should be IDENTITY_REFRESHED_SAME_EXTERNAL_ID with no competing opportunity
            assert result.identity_decision == "REFRESHED"
            assert result.status == "SUCCEEDED"
            reason = result.reasons[0]
            assert reason["code"] == "IDENTITY_REFRESHED_SAME_EXTERNAL_ID"
            assert "competing_opportunity_id" not in reason
        finally:
            fixture.cleanup()


def test_review_created_opportunity_runs_the_title_location_window_finder() -> None:
    with Session(_engine()) as session:
        fixture = _Fixture(session)
        try:
            day = datetime(2026, 9, 1, 12, tzinfo=UTC)
            first = _posting(
                fixture.source_type,
                "aig-1",
                company="AIG",
                title="Collections Supervisor",
                location="Mexico City",
                published_at=day,
            )
            second = _posting(
                fixture.source_type,
                "aig-2",
                company="AIG",
                title="Collections Supervisor",
                location="Mexico City",
                published_at=day + timedelta(days=3),
            )
            _collect(fixture, _StaticCollector(fixture.source_type, [[first, second]]))
            service = OpportunityService(session)
            results = [service.normalize(raw.id) for raw in fixture.raw_items()]

            assert sorted(item.identity_decision for item in results) == ["NEW", "REVIEW"]
            opportunity_ids = {item.opportunity.id for item in results if item.opportunity}
            pairs = [
                item
                for item in session.scalars(select(DuplicateCandidateModel))
                if {item.opportunity_id, item.duplicate_opportunity_id} == opportunity_ids
            ]
            assert len(pairs) == 1
            assert pairs[0].status == "PENDING"
            assert pairs[0].rule == "title_location_window"
        finally:
            fixture.cleanup()


def test_backfill_dry_run_writes_nothing_and_real_run_clears_the_review_result() -> None:
    with Session(_engine()) as session:
        fixture = _competing_identity_fixture(session)
        try:
            service = OpportunityService(session)
            for raw in fixture.raw_items():
                service.normalize(raw.id)

            def stored() -> int:
                return session.execute(
                    text("SELECT count(*) FROM opportunities.normalization_result")
                ).scalar_one()

            def mine(result: dict) -> list[dict]:
                return [i for i in result["items"] if i["source"] == fixture.source.name]

            before = stored()
            dry = backfill_identity_refresh.backfill(session, dry_run=True)
            assert len(mine(dry)) == 1 and dry["deleted"] == 0
            assert stored() == before

            real = backfill_identity_refresh.backfill(session, dry_run=False)
            assert real["deleted"] == dry["affected"]
            assert stored() == before - real["deleted"]
            assert mine(backfill_identity_refresh.backfill(session, dry_run=True)) == []
        finally:
            fixture.cleanup()
