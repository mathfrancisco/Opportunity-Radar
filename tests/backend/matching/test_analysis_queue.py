"""Selection, retry budget and claim of the automatic semantic-analysis pass.

The rules layer must keep working whatever the model does, so every scenario here asserts
on what gets queued and what gets persisted — never on the content of an analysis.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.matching.analysis import (
    AnalysisFailureCode,
    AnalysisMetrics,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisStatus,
    PreparedAnalysis,
    SemanticAnalysis,
    analysis_key,
)
from opportunity_radar.matching.models import (
    MatchAnalysisClaimModel,
    MatchAnalysisModel,
    MatchAssessmentModel,
)
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
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits, ai_quota_usage
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import EmploymentPreference, ProfileSnapshot, Skill
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService
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


@pytest.fixture(autouse=True)
def _retire_pending_assessments_left_by_this_test() -> Iterator[None]:
    """Every test in this file that proves a *value ranking* — verdict, company
    priority, freshness — seeds real, committed `MatchAssessmentModel` rows in this
    shared, never-truncated integration database, and several never analyze them (that
    is the point: they assert the row is skipped, deferred or merely enumerable). Left
    pending, a `score=100.0000`/`HIGH_PRIORITY` default is the highest a later test's own
    seed can ever tie, and stealing a batch slot from it is exactly the F20-24 note's
    "value-ordered queue leftovers" (F20 sanity pass: reproduced under randomized order,
    e.g. by `test_the_queue_serves_the_most_valuable_verdict_first_then_the_newest_posting`
    against `test_the_job_analyzes_a_bounded_batch_and_commits_each_result`).

    Retiring here, once, after every test — rather than patching each test's seeding
    helper — is what keeps this fixed regardless of which new test starts seeding
    assessments next.
    """
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        before_ids = set(session.scalars(select(MatchAssessmentModel.id)))
    yield
    with Session(engine) as session:
        pending_now = set(
            MatchingService(session).pending_analysis_ids(limit=1_000_000)
        )
        leaked = pending_now - before_ids
        if not leaked:
            return
        repository = SqlAlchemyMatchingRepository(session)
        for assessment_id in leaked:
            repository.add_analysis(
                AnalysisRecord(
                    assessment_id=assessment_id,
                    cache_key=uuid4().hex + uuid4().hex,
                    status=AnalysisStatus.AI_COMPLETED.value,
                    schema_version="analysis-v1",
                    analyzed_at=datetime.now(UTC),
                    summary="retired for test isolation",
                    model_id=_MODEL,
                    recommended_review=False,
                )
            )
        session.commit()


class _FakeQuotaGuard:
    """Stands in for `QuotaGuard`: `allow` decides every `reserve` outright.

    Counts `reserve`/`release` calls so a test can prove the worker's admission probe
    nets to zero (card F20-24: "o worker nunca consome" the interactive reserve).
    """

    def __init__(self, *, allow: bool) -> None:
        self.allow = allow
        self.reserved = 0
        self.released = 0

    def reserve(
        self, model: str, estimated_tokens: int, *, ceiling_requests: int | None = None
    ) -> object | None:
        del model, estimated_tokens, ceiling_requests
        if not self.allow:
            return None
        self.reserved += 1
        return object()

    def release(self, reservation: object) -> None:
        del reservation
        self.released += 1


class _StubAdapter:
    """Stands in for the analysis provider. Counts calls, because the cap per pass is the point."""

    def __init__(
        self, outcome: AnalysisOutcome, *, quota_guard: _FakeQuotaGuard | None = None
    ) -> None:
        self._outcome = outcome
        self.calls = 0
        self.warm_ups = 0
        self._quota_guard = quota_guard

    @property
    def model(self) -> str:
        return _MODEL

    @property
    def quota_guard(self) -> _FakeQuotaGuard | None:
        return self._quota_guard

    @property
    def prompt_version(self) -> str:
        return _PROMPT_VERSION

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    def prepare(self, request: AnalysisRequest) -> PreparedAnalysis:
        payload_hash = hashlib.sha256(
            f"{request.opportunity_id}:{request.profile_version_id}:"
            f"{request.opportunity_content_version}".encode()
        ).hexdigest()
        return PreparedAnalysis(
            cache_key=analysis_key(
                request,
                model_id=self.model,
                prompt_version=self.prompt_version,
                schema_version="stub-v1",
                prompt_digest="stub",
                payload_hash=payload_hash,
                options={},
            ),
            payload_hash=payload_hash,
            payload={},
            inference={"model": self.model},
            size=AnalysisMetrics(),
        )

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        prepared: PreparedAnalysis | None = None,
        use_cache: bool = True,
    ) -> AnalysisOutcome:
        del request, prepared, use_cache
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
        detail="could not connect to provider",
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
    # The maximum the `score` column allows: this suite's integration database is never
    # truncated between test files, so a lower default risks losing the value ranking
    # (card F20-24) to an older, unrelated pending assessment left by another file (e.g.
    # `tests/backend/dashboard/test_queries.py` seeds one at 91.0000) and picking the
    # wrong id for a batch this test never queued.
    score: Decimal = Decimal("100.0000"),
    assessed_at: datetime | None = None,
    published_at: datetime | None = None,
    opportunity: OpportunityModel | None = None,
    profile_version: ProfileVersionModel | None = None,
    company: Company | None = None,
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
            canonical_company_id=company.id if company is not None else None,
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
            score=score,
            confidence=Decimal("0.900"),
            assessed_at=assessed_at or datetime.now(UTC),
        ),
        [],
    )
    session.commit()
    return assessment.id


def _profile_version_with_preference(session: Session) -> ProfileVersionModel:
    """A version `evaluate()` can use directly: it needs a persisted preference row."""
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
    stored = session.get(ProfileVersionModel, version.id)
    assert stored is not None
    return stored


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


def _opportunity(session: Session, *, role_family: str) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Analyst",
        normalized_title="analyst",
        work_mode="REMOTE",
        seniority="MID",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
        published_at=datetime.now(UTC),
        role_family=role_family,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def test_the_queue_keeps_to_the_requested_role_families() -> None:
    with _session() as session:
        inside = _seed_assessment(
            session, opportunity=_opportunity(session, role_family="DATA")
        )
        outside = _seed_assessment(
            session, opportunity=_opportunity(session, role_family="SALES")
        )
        repository = SqlAlchemyMatchingRepository(session)
        now = datetime.now(UTC)

        def queued(role_families: tuple[str, ...]) -> set[UUID]:
            return set(
                repository.pending_analysis_ids(
                    eligible_verdicts=DEFAULT_ANALYSIS_VERDICTS,
                    limit=1_000_000,
                    now=now,
                    cooldown=timedelta(hours=1),
                    attempt_window=timedelta(hours=24),
                    max_attempts=3,
                    role_families=role_families,
                )
            )

        targeted = queued(("DATA",))

        assert inside in targeted
        assert outside not in targeted
        assert {inside, outside} <= queued(())
        assert repository.count_pending_analysis(
            eligible_verdicts=DEFAULT_ANALYSIS_VERDICTS,
            now=now,
            cooldown=timedelta(hours=1),
            attempt_window=timedelta(hours=24),
            max_attempts=3,
            role_families=("DATA",),
        ) == len(targeted)


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


def _company(session: Session, *, priority: str) -> Company:
    company = Company(
        canonical_name=f"Company {priority} {uuid4().hex[:8]}",
        normalized_name=f"company-{priority}-{uuid4().hex}",
        priority=priority,
    )
    session.add(company)
    session.flush()
    return company


def test_pending_analysis_orders_by_value() -> None:
    """Card F20-24: company priority (F16-04) outranks score, which outranks freshness."""
    with _session() as session:
        high = _company(session, priority="high")
        low = _company(session, priority="low")

        # Same verdict throughout, so verdict_rank never breaks any of these ties.
        high_priority_low_score = _seed_assessment(
            session, verdict="RECOMMENDED", score=Decimal("50.0000"), company=high
        )
        normal_high_score = _seed_assessment(
            session, verdict="RECOMMENDED", score=Decimal("90.0000")
        )
        normal_low_score = _seed_assessment(
            session, verdict="RECOMMENDED", score=Decimal("40.0000")
        )
        low_priority_top_score = _seed_assessment(
            session, verdict="RECOMMENDED", score=Decimal("99.0000"), company=low
        )
        ours_ids = {
            high_priority_low_score,
            normal_high_score,
            normal_low_score,
            low_priority_top_score,
        }

        queued = MatchingService(session).pending_analysis_ids(limit=100)

        ours = [item for item in queued if item in ours_ids]
        assert ours == [
            high_priority_low_score,  # company priority beats every score below it
            normal_high_score,  # no company (normal tier) beats a low-priority company
            normal_low_score,  # ties within the same priority tier break by score
            low_priority_top_score,  # the highest score still loses to a low priority
        ]


def test_pending_analysis_skips_without_material_change() -> None:
    """Card F20-24 / F20-39: re-evaluating an unchanged opportunity must not re-queue it."""
    with _session() as session:
        version = _profile_version_with_preference(session)
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
        service = MatchingService(session)
        first = service.evaluate(opportunity.id, profile_version_id=version.id)
        session.commit()

        adapter = _StubAdapter(_completed())
        asyncio.run(service.analyze(first.id, adapter))
        assert first.id not in service.pending_analysis_ids(limit=100)

        # Nothing about the opportunity or the profile moved: the same input_hash reuses
        # the same assessment (F20-39) instead of creating a new pending item.
        second = service.evaluate(opportunity.id, profile_version_id=version.id)
        assert second.id == first.id
        assert first.id not in service.pending_analysis_ids(limit=100)

        # The persisted analysis is the cache (F20-16): revisiting must not call Groq again.
        asyncio.run(service.analyze(second.id, adapter))
        assert adapter.calls == 1


def test_pending_analysis_reserves_aging_sample() -> None:
    """Card F20-24 / SPEC 39 section 9: a fraction of the batch samples the tail.

    `HIGH_PRIORITY` verdict, `high` company priority and a score above 95 outrank every
    other test's leftover pending rows in this shared integration database (verdict,
    then priority, then score), so these 20 ids are guaranteed to occupy the top of the
    ranking regardless of run order.
    """
    with _session() as session:
        top_company = _company(session, priority="high")
        # Distinct descending scores make the "top of the ranking" unambiguous.
        seeded = [
            _seed_assessment(
                session,
                verdict="HIGH_PRIORITY",
                score=Decimal(f"{100 - i}.0000"),
                company=top_company,
            )
            for i in range(20)
        ]
        service = MatchingService(session)

        without_aging = service.pending_analysis_ids(limit=10, aging_sample_ratio=0.0)
        with_aging = service.pending_analysis_ids(limit=10, aging_sample_ratio=0.1)

        assert without_aging == seeded[:10]
        assert len(with_aging) == 10
        # The reserved slot is not from the top of the value ranking; the other nine are.
        assert with_aging[:9] == seeded[:9]
        assert with_aging[9] not in set(without_aging)

        # This integration database is never truncated between tests: leaving these 20
        # rows pending would let their inflated scores outrank every later test's own
        # HIGH_PRIORITY seed for the rest of the run. Completing them retires them from
        # the queue the same way a real analysis would.
        for assessment_id in seeded:
            SqlAlchemyMatchingRepository(session).add_analysis(
                AnalysisRecord(
                    assessment_id=assessment_id,
                    cache_key=uuid4().hex + uuid4().hex,
                    status=AnalysisStatus.AI_COMPLETED.value,
                    schema_version="analysis-v1",
                    analyzed_at=datetime.now(UTC),
                    summary="retired for test isolation",
                    model_id=_MODEL,
                    recommended_review=False,
                )
            )
        # `add_analysis` only stages the row (`session.add`); `with _session()` closes on
        # exit without committing, so without this the retirement above was silently
        # discarded and all 20 rows stayed pending — the highest-ranked in the whole
        # database — for the rest of the run (F20 sanity pass, seed 999 of the randomized
        # order reproduced it as a wrong id in
        # test_the_job_analyzes_a_bounded_batch_and_commits_each_result).
        session.commit()
        session.commit()


def test_the_backlog_count_matches_the_uncapped_queue() -> None:
    with _session() as session:
        for _ in range(3):
            _seed_assessment(session)
        service = MatchingService(session)

        assert service.count_pending_analysis() == len(
            service.pending_analysis_ids(limit=1_000_000)
        )


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


def test_the_job_defers_a_pending_id_when_the_worker_ceiling_is_exhausted() -> None:
    """Card F20-24: budget adia sem perder oportunidade nem bloquear o worker."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        assessment_id = _seed_assessment(session, verdict="HIGH_PRIORITY")
    guard = _FakeQuotaGuard(allow=False)
    adapter = _StubAdapter(_completed(), quota_guard=guard)

    analyze_pending(engine, adapter, batch_size=1, worker_requests_ceiling=1)

    assert adapter.calls == 0
    with Session(engine) as session:
        assert (
            session.scalar(
                select(MatchAnalysisModel.id).where(
                    MatchAnalysisModel.assessment_id == assessment_id
                )
            )
            is None
        )
        # Not discarded, not counted against the retry budget: still queued next pass.
        assert assessment_id in MatchingService(session).pending_analysis_ids(limit=100)

        # This assessment is deliberately left pending above (that's what the test
        # proves), but at the default `score=100.0000` it would then rank at the very
        # top of this shared, never-truncated database's queue for the rest of the run —
        # exactly what wrongly won a slot in
        # test_the_job_analyzes_a_bounded_batch_and_commits_each_result under a
        # randomized order (F20 sanity pass). Retire it now that the deferral itself has
        # been observed.
        SqlAlchemyMatchingRepository(session).add_analysis(
            AnalysisRecord(
                assessment_id=assessment_id,
                cache_key=uuid4().hex + uuid4().hex,
                status=AnalysisStatus.AI_COMPLETED.value,
                schema_version="analysis-v1",
                analyzed_at=datetime.now(UTC),
                summary="retired for test isolation",
                model_id=_MODEL,
                recommended_review=False,
            )
        )
        session.commit()


def test_the_worker_budget_probe_never_consumes_quota() -> None:
    """The admission check nets to zero: one `reserve` is always paired with a `release`."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        _seed_assessment(session, verdict="HIGH_PRIORITY")
    guard = _FakeQuotaGuard(allow=True)
    adapter = _StubAdapter(_completed(), quota_guard=guard)

    analyze_pending(engine, adapter, batch_size=1, worker_requests_ceiling=100)

    assert adapter.calls == 1
    assert guard.reserved == 1
    assert guard.released == 1


class _TokenAwareAdapter(_StubAdapter):
    """A `_StubAdapter` on its own quota model, advertising its per-call token estimate."""

    def __init__(self, outcome: AnalysisOutcome, *, model: str, quota_guard: QuotaGuard) -> None:
        super().__init__(outcome)
        self._own_model = model
        self._real_guard = quota_guard

    @property
    def model(self) -> str:
        return self._own_model

    @property
    def quota_guard(self) -> QuotaGuard:  # type: ignore[override]
        return self._real_guard

    @property
    def probe_tokens(self) -> int:
        return 5_900


def _day_quota(model: str, *, tokens_used: int) -> QuotaGuard:
    guard = QuotaGuard(
        create_database_engine(os.environ["DATABASE_URL"]),
        QuotaLimits(
            minute_requests=1_000_000,
            minute_tokens=1_000_000,
            day_requests=1_000_000,
            day_tokens=170_000,
        ),
    )
    if tokens_used:
        assert guard.reserve(model, tokens_used) is not None
    return guard


def _forget_quota(model: str) -> None:
    with create_database_engine(os.environ["DATABASE_URL"]).begin() as connection:
        connection.execute(delete(ai_quota_usage).where(ai_quota_usage.c.model == model))


def test_the_probe_reserves_the_model_estimate_and_defers_without_ai_failed_rows() -> None:
    """Card F48-02: 169,900 of 170,000 tokens used -> no provider call, no `AI_FAILED`."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    model = f"f48-02-{uuid4().hex[:8]}"
    guard = _day_quota(model, tokens_used=169_900)
    try:
        with Session(engine) as session:
            assessment_id = _seed_assessment(session, verdict="HIGH_PRIORITY")
            analyses_before = session.scalar(select(func.count(MatchAnalysisModel.id)))
        adapter = _TokenAwareAdapter(_completed(), model=model, quota_guard=guard)

        analyze_pending(engine, adapter, batch_size=1, worker_requests_ceiling=1_000_000)

        assert adapter.calls == 0
        with Session(engine) as session:
            assert session.scalar(select(func.count(MatchAnalysisModel.id))) == analyses_before
            assert (
                session.scalar(
                    select(MatchAnalysisModel.id).where(
                        MatchAnalysisModel.assessment_id == assessment_id
                    )
                )
                is None
            )
            assert assessment_id in MatchingService(session).pending_analysis_ids(limit=100)
    finally:
        _forget_quota(model)


def test_the_probe_lets_a_batch_through_when_the_estimate_fits() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    model = f"f48-02-{uuid4().hex[:8]}"
    guard = _day_quota(model, tokens_used=100_000)
    try:
        with Session(engine) as session:
            _seed_assessment(session, verdict="HIGH_PRIORITY")
        adapter = _TokenAwareAdapter(_completed(), model=model, quota_guard=guard)

        analyze_pending(engine, adapter, batch_size=1, worker_requests_ceiling=1_000_000)

        assert adapter.calls == 1
    finally:
        _forget_quota(model)

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
