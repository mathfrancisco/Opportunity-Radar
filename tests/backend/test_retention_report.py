from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.companies import models as _companies_models  # noqa: F401
from opportunity_radar.matching.models import (
    CurrentAssessmentModel,
    MatchAnalysisClaimModel,
    MatchAnalysisModel,
    MatchAssessmentModel,
    MatchFactorModel,
)
from opportunity_radar.operations.assessment_retention import AssessmentPruneReport
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)
from scripts import retention_report

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.read_only = False

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)
        if statement == "SET TRANSACTION READ ONLY":
            self.read_only = True

    def execute(self, statement: str, parameters: Any = None) -> _Connection:
        self.statements.append(str(statement))
        return self

    def fetchall(self) -> list[tuple[str, str, int]]:
        return [("matching", "match_assessment", 1234)]

    def fetchone(self) -> tuple[int]:
        return (4,)

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _Connection:
        return self.connection


class _RetentionFixture:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.session = Session(engine)
        self.owner_sub = f"test-retention-report-{uuid4().hex}"
        profile = CareerProfileModel(version=1, owner_sub=self.owner_sub)
        self.session.add(profile)
        self.session.flush()
        version = ProfileVersionModel(
            career_profile_id=profile.id, number=1, status="DRAFT"
        )
        self.session.add(version)
        self.session.flush()
        self.session.add(EmploymentPreferenceModel(profile_version_id=version.id))
        self.profile_id = version.id
        self.opportunity_ids: list[UUID] = []
        self.assessment_ids: list[UUID] = []
        self.analysis_ids: list[UUID] = []
        self.claim_ids: list[UUID] = []
        self.application_ids: list[UUID] = []
        self.session.commit()

    def posting(self) -> UUID:
        marker = uuid4().hex[:8]
        opportunity = OpportunityModel(
            fingerprint=uuid4().hex,
            fingerprint_version="v1",
            canonical_title="Retention report probe",
            normalized_title="retention report probe",
            company_name=f"Probe {marker}",
            normalized_company_name=f"probe-{marker}",
            work_mode="REMOTE",
            seniority="UNKNOWN",
            contract_type="FULL_TIME",
            lifecycle_status="ACTIVE",
            first_seen_at=NOW,
            version=1,
        )
        self.session.add(opportunity)
        self.session.commit()
        self.opportunity_ids.append(opportunity.id)
        return opportunity.id

    def assessment(
        self,
        opportunity_id: UUID,
        age_days: float,
        *,
        version: int = 1,
    ) -> UUID:
        at = NOW - timedelta(days=age_days)
        assessment = MatchAssessmentModel(
            owner_sub=self.owner_sub,
            opportunity_id=opportunity_id,
            opportunity_version=version,
            profile_version_id=self.profile_id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version="matching-v1",
            taxonomy_version=SKILL_TAXONOMY_VERSION,
            opportunity_snapshot={},
            profile_snapshot={},
            eligibility="ELIGIBLE",
            eligibility_details=[],
            verdict="RECOMMENDED",
            score=Decimal("50"),
            confidence=Decimal("0.900"),
            assessed_at=at,
            created_at=at,
        )
        assessment.factors.append(
            MatchFactorModel(
                factor_code="SKILLS",
                weight=Decimal("0.5"),
                contribution=Decimal("10"),
                status="KNOWN",
                confidence=Decimal("0.9"),
                missing_policy="NEUTRAL",
                explanation="report probe",
            )
        )
        self.session.add(assessment)
        self.session.commit()
        self.assessment_ids.append(assessment.id)
        return assessment.id

    def analysis(self, assessment_id: UUID) -> None:
        analysis = MatchAnalysisModel(
            assessment_id=assessment_id,
            cache_key=uuid4().hex + uuid4().hex,
            status="AI_SKIPPED",
            schema_version="v1",
            analyzed_at=NOW,
        )
        self.session.add(analysis)
        self.session.commit()
        self.analysis_ids.append(analysis.id)

    def claim(self, assessment_id: UUID) -> None:
        self.session.add(
            MatchAnalysisClaimModel(
                assessment_id=assessment_id,
                owner="report-probe",
                claimed_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        self.session.commit()
        self.claim_ids.append(assessment_id)

    def application(self, opportunity_id: UUID) -> None:
        application = ApplicationProcessModel(
            owner_sub=self.owner_sub,
            opportunity_id=opportunity_id,
            profile_version_id=self.profile_id,
            current_stage="INTERESTED",
            started_at=NOW,
        )
        self.session.add(application)
        self.session.commit()
        self.application_ids.append(application.id)

    def row_counts(self) -> dict[str, int]:
        self.session.expire_all()
        assessment_ids = self.assessment_ids
        opportunity_ids = self.opportunity_ids
        return {
            "assessments": self._count(
                MatchAssessmentModel,
                MatchAssessmentModel.id.in_(assessment_ids),
            ),
            "factors": self._count(
                MatchFactorModel,
                MatchFactorModel.assessment_id.in_(assessment_ids),
            ),
            "analyses": self._count(
                MatchAnalysisModel,
                MatchAnalysisModel.id.in_(self.analysis_ids),
            ),
            "claims": self._count(
                MatchAnalysisClaimModel,
                MatchAnalysisClaimModel.assessment_id.in_(self.claim_ids),
            ),
            "applications": self._count(
                ApplicationProcessModel,
                ApplicationProcessModel.id.in_(self.application_ids),
            ),
            "all_assessments": self._count(MatchAssessmentModel, True),
            "all_factors": self._count(MatchFactorModel, True),
            "current_pointers": self._count(
                CurrentAssessmentModel,
                CurrentAssessmentModel.opportunity_id.in_(opportunity_ids),
            ),
        }

    def _count(self, model: Any, predicate: Any) -> int:
        return int(
            self.session.scalar(
                select(func.count()).select_from(model).where(predicate)
            )
            or 0
        )

    def cleanup(self) -> None:
        self.session.rollback()
        self.session.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
        mine = select(MatchAssessmentModel.id).where(
            MatchAssessmentModel.opportunity_id.in_(self.opportunity_ids)
        )
        self.session.execute(
            delete(CurrentAssessmentModel).where(
                CurrentAssessmentModel.opportunity_id.in_(self.opportunity_ids)
            )
        )
        for model in (MatchAnalysisClaimModel, MatchAnalysisModel, MatchFactorModel):
            self.session.execute(delete(model).where(model.assessment_id.in_(mine)))
        self.session.execute(
            delete(ApplicationProcessModel).where(
                ApplicationProcessModel.opportunity_id.in_(self.opportunity_ids)
            )
        )
        self.session.execute(
            delete(MatchAssessmentModel).where(
                MatchAssessmentModel.opportunity_id.in_(self.opportunity_ids)
            )
        )
        self.session.execute(
            delete(OpportunityModel).where(OpportunityModel.id.in_(self.opportunity_ids))
        )
        self.session.execute(
            delete(EmploymentPreferenceModel).where(
                EmploymentPreferenceModel.profile_version_id == self.profile_id
            )
        )
        version = self.session.get(ProfileVersionModel, self.profile_id)
        if version is not None:
            profile_id = version.career_profile_id
            self.session.execute(
                delete(ProfileVersionModel).where(ProfileVersionModel.id == self.profile_id)
            )
            self.session.execute(
                delete(CareerProfileModel).where(CareerProfileModel.id == profile_id)
            )
        self.session.commit()
        self.session.close()


def test_report_is_read_only_aggregate_and_counts_protected_references(monkeypatch: Any) -> None:
    connection = _Connection()
    retention = AssessmentPruneReport(
        dry_run=True,
        retention_days=7,
        cutoff=datetime(2026, 1, 1, tzinfo=UTC),
        candidates=5,
        kept_with_analysis=1,
        kept_with_claim=1,
        kept_with_application=1,
        kept_as_current=1,
        deletable=1,
        deleted=1,
        rows_before=10,
        rows_remaining=10,
        avg_per_open_posting_before=2.0,
        avg_per_open_posting_after=None,
    )
    monkeypatch.setattr(
        retention_report,
        "prune_superseded_assessments",
        lambda *_args, **_kwargs: retention,
    )

    report = retention_report.build_report(_Engine(connection), retention_days=7)

    assert connection.read_only is True
    assert report["candidates"] == 5
    assert report["protected_references"] == {
        "analysis": 1,
        "claim": 1,
        "application": 1,
        "current": 1,
    }
    assert report["relation_sizes"] == [
        {"schema": "matching", "relation": "match_assessment", "bytes": 1234}
    ]
    assert all("DELETE" not in statement.upper() for statement in connection.statements)
    assert all("UPDATE" not in statement.upper() for statement in connection.statements)
    assert all("INSERT" not in statement.upper() for statement in connection.statements)

    serialized = json.dumps(report)
    assert "query" not in serialized.lower()
    assert "personal" not in serialized.lower()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1"
    or os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1",
    reason="database integration is enabled only in the isolated PostgreSQL database",
)
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").split("?")[0].rstrip("/").endswith("_test"),
    reason="database integration requires a database name ending in _test",
)
def test_report_reads_the_isolated_database() -> None:
    report = retention_report.build_report(
        create_database_engine(os.environ["DATABASE_URL"]), retention_days=7
    )

    assert report["dry_run"] is True
    assert report["retention"]["dry_run"] is True


@pytest.fixture
def retention_fixture() -> Iterator[_RetentionFixture]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    fixture = _RetentionFixture(engine)
    try:
        yield fixture
    finally:
        fixture.cleanup()
        engine.dispose()


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1"
    or os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1",
    reason="database integration is enabled only in the isolated PostgreSQL database",
)
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL", "").split("?")[0].rstrip("/").endswith("_test"),
    reason="database integration requires a database name ending in _test",
)
def test_report_counts_seeded_protections_without_writing(
    retention_fixture: _RetentionFixture,
) -> None:
    fx = retention_fixture
    baseline = retention_report.build_report(
        fx.engine, retention_days=7, now=NOW
    )

    analysis_posting = fx.posting()
    analysis = fx.assessment(analysis_posting, 30)
    fx.assessment(analysis_posting, 20)
    fx.analysis(analysis)

    claim_posting = fx.posting()
    claim = fx.assessment(claim_posting, 30)
    fx.assessment(claim_posting, 20)
    fx.claim(claim)

    application_posting = fx.posting()
    fx.assessment(application_posting, 30)
    fx.assessment(application_posting, 20)
    fx.application(application_posting)

    current_posting = fx.posting()
    fx.assessment(current_posting, 30, version=2)
    fx.assessment(current_posting, 20, version=1)

    overlap_posting = fx.posting()
    overlap = fx.assessment(overlap_posting, 30)
    fx.assessment(overlap_posting, 20)
    fx.analysis(overlap)
    fx.claim(overlap)
    fx.application(overlap_posting)

    unprotected_posting = fx.posting()
    fx.assessment(unprotected_posting, 30)
    fx.assessment(unprotected_posting, 20)

    latest_posting = fx.posting()
    fx.assessment(latest_posting, 90)

    boundary_posting = fx.posting()
    fx.assessment(boundary_posting, 30)
    fx.assessment(boundary_posting, 7)

    before = fx.row_counts()
    report = retention_report.build_report(fx.engine, retention_days=7, now=NOW)
    after = fx.row_counts()

    assert report["dry_run"] is True
    assert report["retention"]["dry_run"] is True
    assert report["retention"]["candidates"] - baseline["retention"]["candidates"] == 6
    assert report["retention"]["deletable"] - baseline["retention"]["deletable"] == 1
    assert report["retention"]["deleted"] - baseline["retention"]["deleted"] == 1
    assert {
        key: report["protected_references"][key] - baseline["protected_references"][key]
        for key in ("analysis", "claim", "application", "current")
    } == {"analysis": 2, "claim": 2, "application": 2, "current": 1}
    assert sum(
        report["protected_references"][key] - baseline["protected_references"][key]
        for key in ("analysis", "claim", "application", "current")
    ) == 7
    assert report["retention"]["rows_before"] == report["retention"]["rows_remaining"]
    assert before == after
