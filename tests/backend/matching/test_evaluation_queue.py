"""Which opportunities the automatic evaluation pass picks up, and how often.

The identity that makes an assessment "current" is the contract here: same opportunity
version, same active profile, same rules, same taxonomy, same UTC day. Every test below is
about one component of it changing, or not changing.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    ProfileSnapshot,
    Skill,
)
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _session() -> Session:
    return Session(create_database_engine(os.environ["DATABASE_URL"]))


def _ensure_active_profile(session: Session) -> UUID:
    """Publish and activate a version, reusing the one already active when there is one.

    Only one version can be active at a time, so a test that unconditionally activated its
    own would archive whatever another test had just set up.
    """
    active = session.scalar(
        select(ProfileVersionModel).where(ProfileVersionModel.status == "ACTIVE")
    )
    if active is not None:
        return active.id
    service = ProfileService(session)
    profile = session.scalar(select(CareerProfileModel).limit(1))
    expected = profile.version if profile is not None else 0
    snapshot = ProfileSnapshot(
        skills=(Skill(canonical_name="python"),),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(work_modes=("REMOTE",), countries=("BR",)),
    )
    version = service.create_version(snapshot, expected)
    profile = session.scalar(select(CareerProfileModel).limit(1))
    assert profile is not None
    service.publish(version.id, profile.version)
    session.refresh(profile)
    service.activate(version.id, profile.version)
    return version.id


def _opportunity(
    session: Session, *, lifecycle_status: str = "ACTIVE", version: int = 1
) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Backend Engineer",
        normalized_title="backend engineer",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status=lifecycle_status,
        version=version,
    )
    session.add(opportunity)
    session.commit()
    return opportunity


def test_only_discovered_and_active_opportunities_are_queued() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        eligible = {
            status: _opportunity(session, lifecycle_status=status).id
            for status in ("DISCOVERED", "ACTIVE")
        }
        excluded = {
            status: _opportunity(session, lifecycle_status=status).id
            for status in ("CLOSED", "ARCHIVED", "REJECTED")
        }

        queued = set(MatchingService(session).pending_evaluation_ids(limit=500))

        assert set(eligible.values()) <= queued
        assert queued.isdisjoint(excluded.values())


def test_an_evaluated_opportunity_leaves_the_queue_for_the_rest_of_the_day() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        assert opportunity.id in service.pending_evaluation_ids(limit=500)

        service.evaluate(opportunity.id)

        assert opportunity.id not in service.pending_evaluation_ids(limit=500)


def test_evaluating_twice_in_a_day_returns_the_same_assessment() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)

        first = service.evaluate(opportunity.id)
        second = service.evaluate(opportunity.id)

        assert first.id == second.id
        assert (
            session.scalar(
                select(func.count(MatchAssessmentModel.id)).where(
                    MatchAssessmentModel.opportunity_id == opportunity.id
                )
            )
            == 1
        )


def test_a_new_opportunity_version_is_queued_without_waiting_for_the_next_day() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        service.evaluate(opportunity.id)
        assert opportunity.id not in service.pending_evaluation_ids(limit=500)

        # The content changed, so the previous assessment describes a posting that no
        # longer exists — the daily cap must not keep the new one waiting.
        opportunity.version = 2
        opportunity.canonical_title = "Staff Backend Engineer"
        session.commit()

        assert opportunity.id in service.pending_evaluation_ids(limit=500)
        service.evaluate(opportunity.id)
        assert (
            session.scalar(
                select(func.count(MatchAssessmentModel.id)).where(
                    MatchAssessmentModel.opportunity_id == opportunity.id
                )
            )
            == 2
        )


def test_the_batch_limit_caps_how_many_opportunities_are_queued() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        for _ in range(3):
            _opportunity(session)

        assert len(MatchingService(session).pending_evaluation_ids(limit=2)) == 2


def test_assessments_are_immutable_history_rather_than_a_mutable_row() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)

        first = service.evaluate(opportunity.id)
        assessed_at, input_hash = first.assessed_at, first.input_hash
        opportunity.version = 2
        session.commit()
        second = service.evaluate(opportunity.id)

        assert second.id != first.id
        reloaded = service.get(first.id)
        assert reloaded.assessed_at == assessed_at
        assert reloaded.input_hash == input_hash


def test_a_pass_without_an_active_profile_is_a_degraded_state_not_a_crash() -> None:
    from opportunity_radar.profile.domain import ProfileNotFoundError

    with _session() as session:
        active = session.scalar(
            select(ProfileVersionModel).where(ProfileVersionModel.status == "ACTIVE")
        )
        if active is None:
            # The worker turns this into a logged degraded state instead of an exception.
            with pytest.raises(ProfileNotFoundError):
                MatchingService(session).pending_evaluation_ids(limit=1)
        else:
            pytest.skip("another test left an active profile version in place")


def test_the_evaluation_identity_covers_the_reference_day() -> None:
    with _session() as session:
        _ensure_active_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)

        assessment = service.evaluate(opportunity.id)

        # The stored identity is a hash of the same inputs the queue asks about, so a
        # restart recomputes it rather than trusting a cached decision.
        assert len(assessment.input_hash) == 64
        assert assessment.assessed_at.date() == datetime.now(UTC).date()
        assert opportunity.id not in service.pending_evaluation_ids(limit=500)
