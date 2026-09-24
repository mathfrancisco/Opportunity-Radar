"""The semantic layer must persist, degrade and reuse without touching the rules result."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.matching.analysis import (
    AnalysisMetrics,
    AnalysisFailureCode,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisStatus,
    NullAnalysisAdapter,
    SemanticAnalysis,
)
from opportunity_radar.matching.models import MatchAnalysisModel
from opportunity_radar.matching.repository import (
    AssessmentRecord,
    FactorRecord,
    SqlAlchemyMatchingRepository,
)
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel

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
    """Stands in for Ollama: the service must not care which outcome it receives."""

    def __init__(self, outcome: AnalysisOutcome) -> None:
        self._outcome = outcome
        self.calls = 0
        self.requests: list[AnalysisRequest] = []

    @property
    def model(self) -> str:
        return _MODEL

    @property
    def prompt_version(self) -> str:
        return _PROMPT_VERSION

    async def analyze(self, request: AnalysisRequest) -> AnalysisOutcome:
        self.calls += 1
        self.requests.append(request)
        return self._outcome


def _completed() -> AnalysisOutcome:
    return AnalysisOutcome(
        status=AnalysisStatus.AI_COMPLETED,
        analysis=SemanticAnalysis(
            summary="Strong Python match with unclear compensation.",
            strengths=("Python depth",),
            risks=("Compensation not disclosed",),
            inferences=(),
            unknowns=("Timezone overlap",),
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


def _seed_assessment(session: Session) -> tuple[SqlAlchemyMatchingRepository, AssessmentRecord]:
    profile = session.scalar(select(CareerProfileModel).limit(1))
    if profile is None:
        profile = CareerProfileModel(version=1)
        session.add(profile)
        session.flush()
    profile_version = ProfileVersionModel(
        career_profile_id=profile.id,
        number=(
            session.scalar(
                select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                    ProfileVersionModel.career_profile_id == profile.id
                )
            )
            or 0
        )
        + 1,
        status="DRAFT",
    )
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Backend Engineer",
        normalized_title="backend engineer",
        work_mode="REMOTE",
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=2,
    )
    session.add_all([profile_version, opportunity])
    session.flush()

    record = AssessmentRecord(
        opportunity_id=opportunity.id,
        opportunity_version=opportunity.version,
        profile_version_id=profile_version.id,
        input_hash=uuid4().hex + uuid4().hex,
        rules_version="matching-v1",
        taxonomy_version="skills-v1",
        opportunity_snapshot={"work_mode": "REMOTE", "content_version": 2},
        profile_snapshot={"skills": ["python"]},
        eligibility="ELIGIBLE",
        eligibility_details=(),
        verdict="RECOMMENDED",
        score=Decimal("80.0000"),
        confidence=Decimal("0.900"),
        assessed_at=datetime.now(UTC),
    )
    repository = SqlAlchemyMatchingRepository(session)
    factor = FactorRecord(
        factor_code="TECHNOLOGY_FIT",
        weight=Decimal("0.2500"),
        raw_score=Decimal("0.8000"),
        contribution=Decimal("20.0000"),
        status="KNOWN",
        confidence=Decimal("0.900"),
        missing_policy="NEUTRAL",
        explanation="The profile includes the required technology.",
    )
    repository.add(record, [factor])
    session.commit()
    return repository, record


def test_completed_analysis_persists_and_is_reused_without_a_second_call() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        assessment = repository.get_existing(input_hash=record.input_hash)
        assert assessment is not None
        score_before, verdict_before = assessment.score, assessment.verdict

        adapter = _StubAdapter(_completed())
        service = MatchingService(session)
        first = asyncio.run(service.analyze(assessment.id, adapter))
        second = asyncio.run(service.analyze(assessment.id, adapter))

        assert adapter.calls == 1
        assert first.id == second.id
        assert first.status == AnalysisStatus.AI_COMPLETED.value
        assert first.summary == "Strong Python match with unclear compensation."
        assert first.strengths == ["Python depth"]
        assert first.model_id == _MODEL
        assert first.prompt_version == _PROMPT_VERSION
        assert len(first.cache_key) == 64

        # The request is built from persisted state only.
        assert adapter.requests[0].rules_version == "matching-v1"
        assert adapter.requests[0].score == Decimal("80.0000")

        refreshed = repository.get(assessment.id)
        assert refreshed is not None
        assert refreshed.score == score_before
        assert refreshed.verdict == verdict_before
        assert len(refreshed.analyses) == 1


def test_failed_analysis_is_recorded_and_does_not_block_a_retry() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        assessment = repository.get_existing(input_hash=record.input_hash)
        assert assessment is not None

        failing = _StubAdapter(_failed())
        service = MatchingService(session)
        degraded = asyncio.run(service.analyze(assessment.id, failing))

        assert degraded.status == AnalysisStatus.AI_FAILED.value
        assert degraded.failure_code == AnalysisFailureCode.TRANSPORT_ERROR.value
        assert degraded.summary is None

        recovered = asyncio.run(service.analyze(assessment.id, _StubAdapter(_completed())))
        assert recovered.status == AnalysisStatus.AI_COMPLETED.value

        stored = session.scalars(
            select(MatchAnalysisModel)
            .where(MatchAnalysisModel.assessment_id == assessment.id)
            .order_by(MatchAnalysisModel.analyzed_at)
        ).all()
        assert [item.status for item in stored] == [
            AnalysisStatus.AI_FAILED.value,
            AnalysisStatus.AI_COMPLETED.value,
        ]


def test_disabled_semantic_layer_skips_without_failing() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        assessment = repository.get_existing(input_hash=record.input_hash)
        assert assessment is not None

        analysis = asyncio.run(
            MatchingService(session).analyze(assessment.id, NullAnalysisAdapter())
        )

        assert analysis.status == AnalysisStatus.AI_SKIPPED.value
        assert analysis.failure_code is None
        assert analysis.detail == "semantic analysis is disabled"


def test_refresh_appends_a_new_analysis_instead_of_editing_the_previous_one() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        assessment = repository.get_existing(input_hash=record.input_hash)
        assert assessment is not None

        adapter = _StubAdapter(_completed())
        service = MatchingService(session)
        first = asyncio.run(service.analyze(assessment.id, adapter))
        second = asyncio.run(service.analyze(assessment.id, adapter, refresh=True))

        assert adapter.calls == 2
        assert first.id != second.id
        assert first.cache_key == second.cache_key
        assert (
            session.scalar(
                select(func.count(MatchAnalysisModel.id)).where(
                    MatchAnalysisModel.assessment_id == assessment.id
                )
            )
            == 2
        )


def test_the_cost_of_a_call_is_recorded_with_the_analysis() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        assessment = repository.get_existing(input_hash=record.input_hash)
        assert assessment is not None
        completed = _completed()
        costed = AnalysisOutcome(
            status=completed.status,
            analysis=completed.analysis,
            metrics=AnalysisMetrics(
                total_ms=4200,
                load_ms=150,
                prompt_tokens=1830,
                prompt_eval_ms=900,
                output_tokens=212,
                eval_ms=3100,
            ),
        )

        analysis = asyncio.run(
            MatchingService(session).analyze(assessment.id, _StubAdapter(costed), refresh=True)
        )

        assert (analysis.total_ms, analysis.load_ms, analysis.prompt_tokens) == (4200, 150, 1830)
        assert (analysis.prompt_eval_ms, analysis.output_tokens, analysis.eval_ms) == (
            900,
            212,
            3100,
        )


def test_a_failure_before_the_model_answered_records_no_cost() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        assessment = repository.get_existing(input_hash=record.input_hash)
        assert assessment is not None

        analysis = asyncio.run(
            MatchingService(session).analyze(assessment.id, _StubAdapter(_failed()), refresh=True)
        )

        assert analysis.total_ms is None
        assert analysis.output_tokens is None
