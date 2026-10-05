"""Card F50-10: `matching.current_assessment` follows every assessment written.

Currency is not stored in the table; these tests also pin that a pointed row goes stale at
read time exactly as the Inbox used to report it.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
from opportunity_radar.matching.models import CurrentAssessmentModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import ProfileVersionModel
from tests.backend.dashboard.test_queries import (
    _assessment,
    _company,
    _opportunity,
    _profile_version,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _activate(session: Session, version: ProfileVersionModel) -> None:
    session.execute(
        update(ProfileVersionModel)
        .where(ProfileVersionModel.id != version.id)
        .values(status="ARCHIVED")
    )
    version.status = "ACTIVE"
    session.flush()


def _pointers(session: Session, opportunity_id: UUID) -> dict[UUID, CurrentAssessmentModel]:
    rows = session.scalars(
        select(CurrentAssessmentModel).where(
            CurrentAssessmentModel.opportunity_id == opportunity_id
        )
    ).all()
    return {row.profile_version_id: row for row in rows}


def test_pointer_follows_a_newer_assessment_and_ignores_an_older_one_written_later() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        profile = _profile_version(session)
        opportunity = _opportunity(
            session, _company(session, "normal"), title="Pointer", published_at=NOW
        )
        first = _assessment(
            session,
            opportunity,
            profile.id,
            verdict="WATCHLIST",
            score="40.0000",
            assessed_at=NOW - timedelta(hours=3),
        )
        assert _pointers(session, opportunity.id)[profile.id].assessment_id == first.id

        second = _assessment(
            session,
            opportunity,
            profile.id,
            verdict="HIGH_PRIORITY",
            score="91.0000",
            assessed_at=NOW - timedelta(hours=1),
        )
        pointer = _pointers(session, opportunity.id)[profile.id]
        assert pointer.assessment_id == second.id
        assert (pointer.verdict, str(pointer.score)) == ("HIGH_PRIORITY", "91.0000")

        _assessment(
            session,
            opportunity,
            profile.id,
            verdict="LOW_MATCH",
            score="10.0000",
            assessed_at=NOW - timedelta(hours=2),
        )
        session.refresh(pointer)
        assert pointer.assessment_id == second.id
        assert pointer.verdict == "HIGH_PRIORITY"
        session.rollback()


def test_pointer_follows_a_profile_change_and_the_inbox_reads_only_the_active_version() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        old_profile = _profile_version(session)
        new_profile = _profile_version(session)
        _activate(session, old_profile)
        company = _company(session, "normal")
        both = _opportunity(session, company, title="Both", published_at=NOW)
        old_only = _opportunity(session, company, title="Old only", published_at=NOW)
        for opportunity in (both, old_only):
            _assessment(
                session,
                opportunity,
                old_profile.id,
                verdict="WATCHLIST",
                score="40.0000",
                assessed_at=NOW,
            )
        _activate(session, new_profile)
        new_assessment = _assessment(
            session,
            both,
            new_profile.id,
            verdict="RECOMMENDED",
            score="75.0000",
            assessed_at=NOW,
        )

        # New keys, old keys untouched.
        assert set(_pointers(session, both.id)) == {old_profile.id, new_profile.id}
        assert set(_pointers(session, old_only.id)) == {old_profile.id}

        items = {
            item.opportunity_id: item
            for item in list_opportunity_inbox(
                session,
                InboxQuery(company_id=company.id, profile_version_id=new_profile.id),
            ).items
        }
        assert items[both.id].assessment_id == new_assessment.id
        assert items[old_only.id].assessment_id is None
        session.rollback()


def test_a_bumped_posting_version_is_stale_at_read_time() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        profile = _profile_version(session)
        _activate(session, profile)
        company = _company(session, "normal")
        bumped = _opportunity(session, company, title="Bumped", published_at=NOW)
        untouched = _opportunity(session, company, title="Untouched", published_at=NOW)
        for opportunity in (bumped, untouched):
            _assessment(
                session,
                opportunity,
                profile.id,
                verdict="WATCHLIST",
                score="40.0000",
                assessed_at=NOW,
            )
        # Nothing about the pointer changes: the posting did.
        bumped.version = 2
        session.flush()

        items = {
            item.opportunity_id: item
            for item in list_opportunity_inbox(session, InboxQuery(company_id=company.id)).items
        }
        assert items[bumped.id].is_stale is True
        assert items[untouched.id].is_stale is False
        session.rollback()


def test_a_posting_that_crossed_a_recency_band_is_stale_at_read_time() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        profile = _profile_version(session)
        _activate(session, profile)
        company = _company(session, "normal")
        # Age 1 day when assessed (band 0), 10 days now (band 2).
        crossed = _opportunity(
            session, company, title="Crossed", published_at=NOW - timedelta(days=10)
        )
        same_band = _opportunity(
            session, company, title="Same band", published_at=NOW - timedelta(days=10)
        )
        _assessment(
            session,
            crossed,
            profile.id,
            verdict="WATCHLIST",
            score="40.0000",
            assessed_at=NOW - timedelta(days=9),
        )
        _assessment(
            session,
            same_band,
            profile.id,
            verdict="WATCHLIST",
            score="40.0000",
            assessed_at=NOW - timedelta(hours=1),
        )

        items = {
            item.opportunity_id: item
            for item in list_opportunity_inbox(
                session, InboxQuery(company_id=company.id, only_recent=False)
            ).items
        }
        assert items[crossed.id].is_stale is True
        assert items[same_band.id].is_stale is False
        session.rollback()
