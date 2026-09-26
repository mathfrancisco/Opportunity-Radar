"""Cost, failures and backlog of the semantic analysis, per window and per model."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.analysis_metrics import analysis_metrics
from opportunity_radar.matching.repository import (
    AnalysisRecord,
    AssessmentRecord,
    SqlAlchemyMatchingRepository,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _session() -> Session:
    return Session(create_database_engine(os.environ["DATABASE_URL"]))


def _assessment(session: Session) -> UUID:
    profile = session.scalar(select(CareerProfileModel).limit(1))
    if profile is None:
        profile = CareerProfileModel(version=1)
        session.add(profile)
        session.flush()
    number = (
        session.scalar(
            select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                ProfileVersionModel.career_profile_id == profile.id
            )
        )
        or 0
    ) + 1
    version = ProfileVersionModel(career_profile_id=profile.id, number=number, status="DRAFT")
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
    session.add_all([version, opportunity])
    session.flush()
    assessment = SqlAlchemyMatchingRepository(session).add(
        AssessmentRecord(
            opportunity_id=opportunity.id,
            opportunity_version=1,
            profile_version_id=version.id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version="matching-v1",
            taxonomy_version="skills-v1",
            opportunity_snapshot={},
            profile_snapshot={},
            eligibility="ELIGIBLE",
            eligibility_details=(),
            verdict="RECOMMENDED",
            score=Decimal("80.0000"),
            confidence=Decimal("0.900"),
            assessed_at=NOW,
        ),
        [],
    )
    session.flush()
    return assessment.id


def _analysis(
    session: Session,
    model_id: str,
    *,
    total_ms: int | None,
    status: str = "AI_COMPLETED",
    failure_code: str | None = None,
    analyzed_at: datetime | None = None,
) -> None:
    completed = status == "AI_COMPLETED"
    SqlAlchemyMatchingRepository(session).add_analysis(
        AnalysisRecord(
            assessment_id=_assessment(session),
            cache_key=uuid4().hex + uuid4().hex,
            status=status,
            schema_version="analysis-v1",
            analyzed_at=analyzed_at or NOW - timedelta(minutes=5),
            failure_code=failure_code,
            summary="Resumo." if completed else None,
            recommended_review=False if completed else None,
            model_id=model_id,
            prompt_version="opportunity_analysis/v1",
            total_ms=total_ms,
            load_ms=None if total_ms is None else 10,
            prompt_tokens=None if total_ms is None else 900,
            output_tokens=None if total_ms is None else 100,
        )
    )


def _model() -> str:
    return f"ci-model-{uuid4().hex[:8]}"


def test_percentiles_averages_and_rates_are_computed_per_model() -> None:
    model = _model()
    with _session() as session:
        for total_ms in (1000, 2000, 3000, 4000, 5000):
            _analysis(session, model, total_ms=total_ms)
        _analysis(session, model, total_ms=None)  # served from the cache
        _analysis(
            session, model, total_ms=None, status="AI_FAILED", failure_code="TIMEOUT"
        )
        _analysis(
            session,
            model,
            total_ms=6000,
            status="AI_FAILED",
            failure_code="SCHEMA_MISMATCH",
        )
        session.commit()

        report = analysis_metrics(session, current_model=model, pending=7, now=NOW)

    assert [window.window for window in report.windows] == ["24h", "7d"]
    metrics = report.windows[0].for_model(model)
    assert metrics is not None
    assert (metrics.analyses, metrics.completed, metrics.failed) == (8, 6, 2)
    assert metrics.total_ms_p50 == 3500.0
    assert metrics.total_ms_p95 == pytest.approx(5750.0)
    assert metrics.total_ms_p99 == pytest.approx(5950.0)
    assert metrics.prompt_tokens_avg == 900.0
    assert metrics.output_tokens_avg == 100.0
    assert metrics.load_ms_avg == 10.0
    assert metrics.failure_rate == 0.25
    assert metrics.failure_rates == {"TIMEOUT": 0.125, "SCHEMA_MISMATCH": 0.125}
    assert metrics.reuse_rate == pytest.approx(1 / 6)
    assert report.pending == 7


def test_a_model_without_recorded_costs_has_no_percentile() -> None:
    model = _model()
    with _session() as session:
        _analysis(session, model, total_ms=None, status="AI_FAILED", failure_code="TIMEOUT")
        session.commit()

        metrics = analysis_metrics(
            session, current_model=model, pending=0, now=NOW
        ).windows[0].for_model(model)

    assert metrics is not None
    assert metrics.total_ms_p50 is None
    assert metrics.total_ms_p95 is None
    assert metrics.prompt_tokens_avg is None
    assert metrics.reuse_rate is None
    assert metrics.failure_rate == 1.0


def test_the_short_window_excludes_older_analyses() -> None:
    model = _model()
    with _session() as session:
        _analysis(session, model, total_ms=1000, analyzed_at=NOW - timedelta(days=3))
        session.commit()

        report = analysis_metrics(session, current_model=model, pending=0, now=NOW)

    assert report.windows[0].for_model(model) is None
    week = report.windows[1].for_model(model)
    assert week is not None and week.analyses == 1


def test_an_empty_window_answers_no_model_rather_than_zeros() -> None:
    with _session() as session:
        report = analysis_metrics(
            session, current_model="any", pending=0, now=datetime(2000, 1, 1, tzinfo=UTC)
        )

    assert all(window.models == () for window in report.windows)


def test_the_endpoint_answers_both_windows_and_rejects_an_unknown_one() -> None:
    model = _model()
    with _session() as session:
        _analysis(session, model, total_ms=1500)
        session.commit()
    client = TestClient(
        create_app(
            Settings(database_url=os.environ["DATABASE_URL"], groq_reasoning_model=model)
        )
    )

    response = client.get("/analysis-metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["current_model"] == model
    assert isinstance(body["pending"], int) and body["pending"] >= 0
    assert [window["window"] for window in body["windows"]] == ["24h", "7d"]
    day = next(item for item in body["windows"][0]["models"] if item["model_id"] == model)
    assert day["total_ms_p50"] == 1500.0
    assert day["failure_rate"] == 0.0

    week = client.get("/analysis-metrics?window=7d").json()
    assert [window["window"] for window in week["windows"]] == ["7d"]
    assert client.get("/analysis-metrics?window=90d").status_code == 422


def test_the_endpoint_answers_carries_an_ai_block() -> None:
    """Card F20-20: the response gets a new `ai` block, none of the old fields move."""
    client = TestClient(
        create_app(Settings(database_url=os.environ["DATABASE_URL"]))
    )

    body = client.get("/analysis-metrics").json()

    assert "ai" in body
    ai = body["ai"]
    assert ai["state"] in {"enabled", "disabled", "blocked_by_configuration"}
    assert ai["window_hours"] == 24
    assert isinstance(ai["by_model"], list)
    assert "cache_hit_rate" in ai
    # Old fields are still there, untouched.
    assert "current_model" in body and "pending" in body and "windows" in body
