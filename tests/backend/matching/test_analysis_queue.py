"""Selection, retry budget and claim of the automatic semantic-analysis pass.

The rules layer must keep working whatever the model does, so every scenario here asserts
on what gets queued and what gets persisted — never on the content of an analysis.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.matching.analysis import (
    AnalysisFailureCode,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisStatus,
    SemanticAnalysis,
)
from opportunity_radar.matching.models import MatchAnalysisClaimModel, MatchAnalysisModel
from opportunity_radar.matching.repository import (
    AnalysisRecord,
    AssessmentRecord,
    SqlAlchemyMatchingRepository,
)
from opportunity_radar.matching.service import (
    DEFAULT_ANALYSIS_VERDICTS,
    AnalysisInProgressError,
    MatchingService,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.worker import analyze_pending

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_MODEL = "llama3.2:3b"
_PROMPT_VERSION = "opportunity_analysis/v1"


class _StubAdapter:
    """Stands in for Ollama. Counts calls, because the cap per pass is the point."""

    def __init__(self, outcome: AnalysisOutcome) -> None:
        self._outcome = outcome
        self.calls = 0
        self.warm_ups = 0

    @property
    def model(self) -> str:
        return _MODEL

    @property
    def prompt_version(self) -> str:
        return _PROMPT_VERSION

    async def analyze(self, request: AnalysisRequest) -> AnalysisOutcome:
        del request
        self.calls += 1
        return self._outcome

    async def warm_up(self, *, only_if_idle: bool = False) -> None:
        del only_if_idle
        self.warm_ups += 1


def _completed() -> AnalysisOutcome:
    return AnalysisOutcome(
        status=AnalysisStatus.AI_COMPLETED,
        analysis=SemanticAnalysis(
            summary="Strong match.",
            strengths=(),
            risks=(),
            inferences=(),
            unknowns=(),
            recommended_review=False,
            model_id=_MODEL,
            prompt_version=_PROMPT_VERSION,
        ),
    )


def _failed() -> AnalysisOutcome:
    return AnalysisOutcome(
        status=AnalysisStatus.AI_FAILED,
        failure_code=AnalysisFailureCode.TRANSPORT_ERROR,
        detail="could not connect to ollama",
    )


def _profile_version(session: Session) -> ProfileVersionModel:
    """The career profile is a singleton, so each test appends a version to the same row."""
    profile = session.scalar(select(CareerProfileModel).limit(1))
    if profile is None:
        profile = CareerProfileModel(version=1)
        session.add(profile)
        session.flush()
    next_number = (
        session.scalar(
            select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                ProfileVersionModel.career_profile_id == profile.id
            )
        )
        or 0
    ) + 1
    version = ProfileVersionModel(
        career_profile_id=profile.id, number=next_number, status="DRAFT"
    )
    session.add(version)
    session.flush()
    return version


def _seed_assessment(
    session: Session,
    *,
    verdict: str = "RECOMMENDED",
    assessed_at: datetime | None = None,
    published_at: datetime | None = None,
    opportunity: OpportunityModel | None = None,
    profile_version: ProfileVersionModel | None = None,
) -> UUID:
    """Persist one assessment, returning its id. Snapshots are minimal on purpose."""
    version = profile_version or _profile_version(session)
    if opportunity is None:
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
            published_at=published_at or datetime.now(UTC),
        )
        session.add(opportunity)
        session.flush()
    repository = SqlAlchemyMatchingRepository(session)
    assessment = repository.add(
        AssessmentRecord(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            profile_version_id=version.id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version="matching-v1",
            taxonomy_version="skills-v1",
            opportunity_snapshot={"content_version": opportunity.version},
            profile_snapshot={"skills": ["python"]},
            eligibility="ELIGIBLE",
            eligibility_details=(),
            verdict=verdict,
            score=Decimal("80.0000"),
            confidence=Decimal("0.900"),
            assessed_at=assessed_at or datetime.now(UTC),
        ),
        [],
    )
    session.commit()
    return assessment.id


def _record_attempt(
    session: Session,
    assessment_id: UUID,
    *,
    status: str,
    analyzed_at: datetime,
) -> None:
    SqlAlchemyMatchingRepository(session).add_analysis(
        AnalysisRecord(
            assessment_id=assessment_id,
            cache_key=uuid4().hex + uuid4().hex,
            status=status,
            schema_version="analysis-v1",
            analyzed_at=analyzed_at,
            failure_code=(
                AnalysisFailureCode.TRANSPORT_ERROR.value
                if status == AnalysisStatus.AI_FAILED.value
                else None
            ),
        )
    )
    session.commit()


def _session() -> Session:
    return Session(create_database_engine(os.environ["DATABASE_URL"]))


def test_only_configured_verdicts_are_queued() -> None:
    with _session() as session:
        eligible = {
            verdict: _seed_assessment(session, verdict=verdict)
            for verdict in DEFAULT_ANALYSIS_VERDICTS
        }
        ignored = {
            verdict: _seed_assessment(session, verdict=verdict)
            for verdict in ("LOW_MATCH", "INELIGIBLE")
        }

        queued = set(MatchingService(session).pending_analysis_ids(limit=100))

        assert set(eligible.values()) <= queued
        assert queued.isdisjoint(ignored.values())


def test_the_queue_serves_the_most_valuable_verdict_first_then_the_newest_posting() -> None:
    now = datetime.now(UTC)
    with _session() as session:
        seeded = {
            (verdict, age): _seed_assessment(
                session, verdict=verdict, published_at=now - timedelta(days=age)
            )
            for verdict in ("WATCHLIST", "REVIEW_REQUIRED", "RECOMMENDED", "HIGH_PRIORITY")
            for age in (5, 1)
        }

        queued = MatchingService(session).pending_analysis_ids(limit=10_000)

        ours = [item for item in queued if item in set(seeded.values())]
        assert ours == [
            seeded[(verdict, age)]
            for verdict in ("HIGH_PRIORITY", "RECOMMENDED", "REVIEW_REQUIRED", "WATCHLIST")
            for age in (1, 5)
        ]


def test_a_batch_warms_the_model_before_analyzing() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        _seed_assessment(session, verdict="HIGH_PRIORITY")
    adapter = _StubAdapter(_completed())

    analyze_pending(engine, adapter, batch_size=1)

    assert adapter.warm_ups == 1
    assert adapter.calls == 1


def test_a_completed_analysis_leaves_the_queue_and_is_not_re_prompted() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        adapter = _StubAdapter(_completed())

        assert assessment_id in service.pending_analysis_ids(limit=100)
        asyncio.run(service.analyze(assessment_id, adapter))

        assert assessment_id not in service.pending_analysis_ids(limit=100)
        # The persisted analysis is the cache: a second call must not reach the model.
        asyncio.run(service.analyze(assessment_id, adapter))
        assert adapter.calls == 1


def test_a_completed_analysis_is_repeated_only_with_refresh() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        adapter = _StubAdapter(_completed())

        asyncio.run(service.analyze(assessment_id, adapter))
        asyncio.run(service.analyze(assessment_id, adapter, refresh=True))

        assert adapter.calls == 2
        stored = session.scalars(
            select(MatchAnalysisModel).where(
                MatchAnalysisModel.assessment_id == assessment_id
            )
        ).all()
        assert len(stored) == 2


def test_a_failure_holds_the_assessment_until_the_cooldown_elapses() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        now = datetime.now(UTC)
        _record_attempt(
            session,
            assessment_id,
            status=AnalysisStatus.AI_FAILED.value,
            analyzed_at=now - timedelta(minutes=30),
        )

        cooling = service.pending_analysis_ids(limit=100, cooldown=timedelta(hours=1))
        assert assessment_id not in cooling

        elapsed = service.pending_analysis_ids(limit=100, cooldown=timedelta(minutes=15))
        assert assessment_id in elapsed


def test_the_attempt_ceiling_applies_only_inside_its_window() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        now = datetime.now(UTC)
        for hours in (2, 4, 6):
            _record_attempt(
                session,
                assessment_id,
                status=AnalysisStatus.AI_FAILED.value,
                analyzed_at=now - timedelta(hours=hours),
            )

        # Three attempts in the last 24 hours exhaust the default budget.
        assert assessment_id not in service.pending_analysis_ids(limit=100)
        # The same history is no longer in budget once the window slides past it.
        assert assessment_id in service.pending_analysis_ids(
            limit=100, attempt_window=timedelta(hours=1)
        )


def test_a_success_clears_the_retry_state_left_by_earlier_failures() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        now = datetime.now(UTC)
        for hours in (2, 4):
            _record_attempt(
                session,
                assessment_id,
                status=AnalysisStatus.AI_FAILED.value,
                analyzed_at=now - timedelta(hours=hours),
            )

        asyncio.run(service.analyze(assessment_id, _StubAdapter(_completed())))

        # Two failures would still be within budget, but a completed analysis ends the
        # queue membership outright rather than leaving a countdown behind.
        assert assessment_id not in service.pending_analysis_ids(limit=100)
        assert assessment_id not in service.pending_analysis_ids(
            limit=100, max_attempts=1
        )


def test_a_superseded_assessment_is_not_analyzed() -> None:
    with _session() as session:
        version = _profile_version(session)
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
        )
        session.add(opportunity)
        session.flush()
        now = datetime.now(UTC)
        older = _seed_assessment(
            session,
            assessed_at=now - timedelta(hours=1),
            opportunity=opportunity,
            profile_version=version,
        )
        newer = _seed_assessment(
            session,
            assessed_at=now,
            opportunity=opportunity,
            profile_version=version,
        )

        queued = MatchingService(session).pending_analysis_ids(limit=100)

        assert newer in queued
        assert older not in queued


def test_the_pass_limit_caps_how_many_assessments_are_queued() -> None:
    with _session() as session:
        for _ in range(4):
            _seed_assessment(session)

        assert len(MatchingService(session).pending_analysis_ids(limit=2)) == 2


def test_a_live_claim_blocks_a_concurrent_analysis_of_the_same_assessment() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        now = datetime.now(UTC)
        assert service.repository.acquire_analysis_claim(
            assessment_id, owner="worker", now=now, lease=timedelta(minutes=15)
        )
        session.commit()

        adapter = _StubAdapter(_completed())
        with pytest.raises(AnalysisInProgressError):
            asyncio.run(service.analyze(assessment_id, adapter, owner="manual"))

        assert adapter.calls == 0
        assert (
            session.scalar(
                select(MatchAnalysisModel.id).where(
                    MatchAnalysisModel.assessment_id == assessment_id
                )
            )
            is None
        )


def test_an_expired_claim_is_taken_over_instead_of_blocking_forever() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)
        expired_at = datetime.now(UTC) - timedelta(hours=2)
        assert service.repository.acquire_analysis_claim(
            assessment_id, owner="crashed", now=expired_at, lease=timedelta(minutes=15)
        )
        session.commit()

        analysis = asyncio.run(
            service.analyze(assessment_id, _StubAdapter(_completed()), owner="worker")
        )

        assert analysis.status == AnalysisStatus.AI_COMPLETED.value


def test_the_claim_is_released_after_the_analysis_completes() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)

        asyncio.run(service.analyze(assessment_id, _StubAdapter(_completed())))

        assert (
            session.scalar(
                select(MatchAnalysisClaimModel.assessment_id).where(
                    MatchAnalysisClaimModel.assessment_id == assessment_id
                )
            )
            is None
        )


def test_a_model_failure_records_history_and_releases_the_claim() -> None:
    with _session() as session:
        assessment_id = _seed_assessment(session)
        service = MatchingService(session)

        degraded = asyncio.run(service.analyze(assessment_id, _StubAdapter(_failed())))

        assert degraded.status == AnalysisStatus.AI_FAILED.value
        assert (
            session.scalar(
                select(MatchAnalysisClaimModel.assessment_id).where(
                    MatchAnalysisClaimModel.assessment_id == assessment_id
                )
            )
            is None
        )


def test_the_job_analyzes_a_bounded_batch_and_commits_each_result() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        seeded = [_seed_assessment(session, verdict="HIGH_PRIORITY") for _ in range(3)]
    adapter = _StubAdapter(_completed())

    analyze_pending(engine, adapter, batch_size=2)

    assert adapter.calls == 2
    with Session(engine) as session:
        analyzed = session.scalars(
            select(MatchAnalysisModel.assessment_id).where(
                MatchAnalysisModel.assessment_id.in_(seeded)
            )
        ).all()
    assert len(set(analyzed)) == 2


def test_the_job_skips_a_claimed_assessment_without_failing_the_pass() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        claimed = _seed_assessment(session, verdict="HIGH_PRIORITY")
        service = MatchingService(session)
        assert service.repository.acquire_analysis_claim(
            claimed, owner="other", now=datetime.now(UTC), lease=timedelta(minutes=15)
        )
        session.commit()
    adapter = _StubAdapter(_completed())

    analyze_pending(engine, adapter, batch_size=1)

    assert adapter.calls == 0
    with Session(engine) as session:
        assert (
            session.scalar(
                select(MatchAnalysisModel.id).where(
                    MatchAnalysisModel.assessment_id == claimed
                )
            )
            is None
        )


def test_an_unavailable_model_degrades_the_job_without_raising() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        assessment_id = _seed_assessment(session, verdict="HIGH_PRIORITY")

    analyze_pending(engine, _StubAdapter(_failed()), batch_size=1)

    with Session(engine) as session:
        statuses = session.scalars(
            select(MatchAnalysisModel.status).where(
                MatchAnalysisModel.assessment_id == assessment_id
            )
        ).all()
    assert list(statuses) == [AnalysisStatus.AI_FAILED.value]
