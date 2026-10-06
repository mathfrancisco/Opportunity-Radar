"""Re-evaluation after an input version moves, and what survives an interrupted batch.

Each scenario changes exactly one component of the identity and then asserts two things:
the opportunity comes back into the queue, and the assessment written before the change is
still there, unchanged. Append-only is the whole point — the old score is the record of
what the system believed at the time, and a re-evaluation that edited it would destroy the
only evidence that the decision ever differed.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company  # noqa: F401  (metadata)
from opportunity_radar.matching import service as matching_service
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.opportunities.models import OpportunityModel, OpportunitySkillModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import (
    EmploymentPreference,
    ProfileSnapshot,
    Skill,
)
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService
from opportunity_radar.worker import evaluate_pending

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _engine():
    return create_database_engine(os.environ["DATABASE_URL"])


def _session() -> Session:
    return Session(_engine())


def _activate_new_profile(
    session: Session,
    *,
    countries: tuple[str, ...] = ("BR",),
    work_modes: tuple[str, ...] = ("REMOTE",),
) -> ProfileVersionModel:
    """Publish and activate a fresh version, archiving whichever one was active."""
    service = ProfileService(session)
    profile = session.scalar(select(CareerProfileModel).limit(1))
    expected = profile.version if profile is not None else 0
    snapshot = ProfileSnapshot(
        skills=(Skill(canonical_name="python"),),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(work_modes=work_modes, countries=countries),
    )
    version = service.create_version(snapshot, expected)
    profile = session.scalar(select(CareerProfileModel).limit(1))
    assert profile is not None
    service.publish(version.id, profile.version)
    session.refresh(profile)
    service.activate(version.id, profile.version)
    stored = session.get(ProfileVersionModel, version.id)
    assert stored is not None
    return stored


def _opportunity(
    session: Session,
    *,
    with_skill: bool = False,
    published_at: datetime | None = None,
) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Backend Engineer",
        normalized_title="backend engineer",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
        published_at=published_at,
    )
    session.add(opportunity)
    session.flush()
    if with_skill:
        session.add(
            OpportunitySkillModel(
                opportunity_id=opportunity.id,
                canonical_name="python",
                display_name="Python",
                requirement="REQUIRED",
                taxonomy_version="skills-v1",
                normalizer_version="normalizer-v1",
                evidence=[],
            )
        )
    session.commit()
    return opportunity


def _assessment_count(session: Session, opportunity_id) -> int:
    return (
        session.scalar(
            select(func.count(MatchAssessmentModel.id)).where(
                MatchAssessmentModel.opportunity_id == opportunity_id
            )
        )
        or 0
    )


def test_activating_a_profile_makes_previous_assessments_pending_again() -> None:
    with _session() as session:
        _activate_new_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)
        first_id, first_assessed_at = first.id, first.assessed_at
        assert opportunity.id not in service.pending_evaluation_ids(limit=500)

        _activate_new_profile(session, countries=("BR", "PT"))

        assert opportunity.id in service.pending_evaluation_ids(limit=500)
        second = service.evaluate(opportunity.id)
        assert second.id != first_id
        preserved = service.get(first_id)
        assert preserved.assessed_at == first_assessed_at
        assert _assessment_count(session, opportunity.id) == 2


def test_updating_the_opportunity_content_produces_an_assessment_for_the_new_version() -> None:
    with _session() as session:
        _activate_new_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)

        opportunity.version = 2
        opportunity.canonical_title = "Staff Backend Engineer"
        session.commit()

        assert opportunity.id in service.pending_evaluation_ids(limit=500)
        second = service.evaluate(opportunity.id)
        assert second.opportunity_version == 2
        assert service.get(first.id).opportunity_version == 1


def test_changing_the_accepted_work_mode_changes_the_reassessment_verdict() -> None:
    with _session() as session:
        _activate_new_profile(session, work_modes=("REMOTE",))
        opportunity = _opportunity(session)
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)
        assert first.verdict != "INELIGIBLE"

        _activate_new_profile(session, work_modes=("ONSITE",))

        assert opportunity.id in service.pending_evaluation_ids(limit=500)
        second = service.evaluate(opportunity.id)
        assert second.verdict == "INELIGIBLE"
        assert service.get(first.id).verdict != "INELIGIBLE"


def test_a_ruleset_bump_requeues_without_touching_the_previous_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _session() as session:
        _activate_new_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)
        assert opportunity.id not in service.pending_evaluation_ids(limit=500)

        # The bump is detected by comparing the persisted version with the active
        # constant, so no migration or event is needed to notice it.
        monkeypatch.setattr(matching_service, "RULES_VERSION", "matching-v6")

        assert opportunity.id in service.pending_evaluation_ids(limit=500)
        second = service.evaluate(opportunity.id)
        assert second.rules_version == "matching-v6"
        assert service.get(first.id).rules_version == "matching-v5"


def test_a_taxonomy_bump_requeues_the_opportunity() -> None:
    with _session() as session:
        _activate_new_profile(session)
        opportunity = _opportunity(session, with_skill=True)
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)
        assert first.taxonomy_version == "skills-v1"
        assert opportunity.id not in service.pending_evaluation_ids(limit=500)

        skill = session.scalar(
            select(OpportunitySkillModel).where(
                OpportunitySkillModel.opportunity_id == opportunity.id
            )
        )
        assert skill is not None
        skill.taxonomy_version = "skills-v2"
        session.commit()

        assert opportunity.id in service.pending_evaluation_ids(limit=500)
        assert service.evaluate(opportunity.id).taxonomy_version == "skills-v2"


def test_an_interrupted_batch_resumes_without_duplicating_results() -> None:
    engine = _engine()
    with _session() as session:
        _activate_new_profile(session)
        opportunities = [_opportunity(session).id for _ in range(3)]

    # One opportunity per pass, as if the worker had been killed between each. Progress
    # lives in the database, so a restart re-derives the remaining work rather than
    # resuming a plan it no longer has. The queue is catalogue-wide and ordered by
    # creation, and activating a profile above makes every row other tests left behind
    # pending too, so the pass budget is the size of the queue at the start (each pass
    # retires one row) rather than a fixed count that shared-database leftovers can exceed.
    with _session() as session:
        queue_size = len(MatchingService(session).pending_evaluation_ids(limit=100_000))
    for _ in range(queue_size + 1):
        with _session() as session:
            pending = set(MatchingService(session).pending_evaluation_ids(limit=100_000))
        if not pending.intersection(opportunities):
            break
        evaluate_pending(engine, batch_size=1)
    else:  # pragma: no cover - only reached if the queue never drains
        pytest.fail("the queue never reached the opportunities under test")

    with _session() as session:
        for opportunity_id in opportunities:
            assert _assessment_count(session, opportunity_id) == 1

    # A further pass after everything is current must add nothing at all.
    evaluate_pending(engine, batch_size=50)
    with _session() as session:
        for opportunity_id in opportunities:
            assert _assessment_count(session, opportunity_id) == 1


def test_a_pass_reports_what_it_processed() -> None:
    engine = _engine()
    with _session() as session:
        _activate_new_profile(session)
        opportunity_id = _opportunity(session).id

    logger = logging.getLogger("opportunity_radar.worker")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logger.addHandler(handler)
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    try:
        for _ in range(200):
            evaluate_pending(engine, batch_size=50)
            with _session() as session:
                if _assessment_count(session, opportunity_id) == 1:
                    break
        else:  # pragma: no cover - only reached if the queue never reaches this item
            pytest.fail("the queue never reached the opportunity under test")
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    finished = [
        record for record in records if record.getMessage() == "matching batch finished"
    ]
    assert finished, "the pass reported no progress"
    assert getattr(finished[-1], "processed") >= 1
    assert getattr(finished[-1], "failed") == 0
    with _session() as session:
        assert _assessment_count(session, opportunity_id) == 1


def test_assessments_written_before_a_change_stay_readable() -> None:
    with _session() as session:
        _activate_new_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)
        snapshot = (first.score, first.verdict, first.input_hash, first.assessed_at)

        _activate_new_profile(session, countries=("BR", "AR"))
        service.evaluate(opportunity.id)

        reloaded = service.get(first.id)
        assert (
            reloaded.score,
            reloaded.verdict,
            reloaded.input_hash,
            reloaded.assessed_at,
        ) == snapshot


def test_the_current_assessment_is_the_one_matching_the_active_inputs() -> None:
    with _session() as session:
        _activate_new_profile(session)
        opportunity = _opportunity(session)
        service = MatchingService(session)
        stale = service.evaluate(opportunity.id)

        _activate_new_profile(session, countries=("BR", "CL"))

        # Every stored assessment is now stale, which is not the same as never scored.
        assert service.current_assessment(opportunity.id) is None
        fresh = service.evaluate(opportunity.id)
        current = service.current_assessment(opportunity.id)
        assert current is not None
        assert current.id == fresh.id
        assert current.id != stale.id


def test_a_posting_that_crossed_a_recency_band_is_queued_and_scored_lower() -> None:
    with _session() as session:
        _activate_new_profile(session)
        today = datetime.now(UTC)
        tomorrow = today + timedelta(days=1)
        # Three days old today (best band), four tomorrow (next band).
        opportunity = _opportunity(session, published_at=today - timedelta(days=3))
        service = MatchingService(session)
        first = service.evaluate(opportunity.id)
        assert opportunity.id not in service.pending_evaluation_ids(limit=500)

        # The next UTC day alone queues nothing: the band is the same.
        sameband = _opportunity(session, published_at=today - timedelta(days=10))
        service.evaluate(sameband.id)
        queued = service.pending_evaluation_ids(limit=5000, now=tomorrow)
        assert sameband.id not in queued
        # The posting that crossed the band is offered again, and its stored assessment
        # no longer describes the inputs, so the Inbox may call it out of date.
        assert opportunity.id in queued
        assert service.current_assessment(opportunity.id) is not None

        class _Tomorrow(datetime):
            @classmethod
            def now(cls, tz=None):  # type: ignore[no-untyped-def]
                return tomorrow

        original = matching_service.datetime
        matching_service.datetime = _Tomorrow  # type: ignore[misc,assignment]
        try:
            second = service.evaluate(opportunity.id)
        finally:
            matching_service.datetime = original  # type: ignore[misc]

        def recency(assessment: MatchAssessmentModel) -> object:
            return next(f.raw_score for f in assessment.factors if f.factor_code == "RECENCY")

        assert second.id != first.id
        assert recency(second) < recency(first)  # type: ignore[operator]
        assert second.score < first.score
        assert opportunity.id not in service.pending_evaluation_ids(limit=5000, now=tomorrow)


@pytest.fixture(autouse=True)
def _empty_catalogue() -> None:
    """The queue reads the oldest pending postings first, up to its limit. Postings left by
    earlier test modules are pending for every new profile version, and past the limit they
    push the posting under test out of the page."""
    with create_database_engine(os.environ["DATABASE_URL"]).begin() as connection:
        connection.execute(text("TRUNCATE opportunities.opportunity CASCADE"))
