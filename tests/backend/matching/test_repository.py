"""Database-backed persistence proof for immutable matching assessments."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.matching.models import MatchAssessmentModel, MatchFactorModel
from opportunity_radar.matching.repository import (
    AssessmentRecord,
    FactorRecord,
    SqlAlchemyMatchingRepository,
)
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


def test_assessment_persistence_is_idempotent_and_keeps_factors() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
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
            input_hash="a" * 64,
            rules_version="matching-rules-v1",
            taxonomy_version="skills-v1",
            opportunity_snapshot={"id": str(opportunity.id), "work_mode": "REMOTE"},
            profile_snapshot={"id": str(profile_version.id), "countries": ["BR"]},
            eligibility="ELIGIBLE",
            eligibility_details=(),
            verdict="RECOMMENDED",
            score=Decimal("80.00"),
            confidence=Decimal("0.900"),
            assessed_at=datetime.now(UTC),
        )
        factor = FactorRecord(
            factor_code="TECHNOLOGY_FIT",
            weight=Decimal("0.2500"),
            raw_score=Decimal("0.8000"),
            contribution=Decimal("20.00"),
            status="KNOWN",
            confidence=Decimal("0.900"),
            missing_policy="NEUTRAL",
            explanation="The profile includes the required technology.",
            evidence_refs=("opportunity.skills:python",),
        )
        repository = SqlAlchemyMatchingRepository(session)
        first = repository.add(record, [factor])
        session.flush()
        repeated = repository.add(record, [factor])
        next_day = repository.add(
            replace(record, input_hash="b" * 64),
            [factor],
        )
        session.commit()

        assert first.id == repeated.id
        assert next_day.id != first.id
        loaded = repository.get(first.id)
        assert loaded is not None
        assert loaded.opportunity_snapshot == record.opportunity_snapshot
        assert loaded.profile_snapshot == record.profile_snapshot
        assert len(loaded.factors) == 1
        assert loaded.factors[0].factor_code == "TECHNOLOGY_FIT"
        assert loaded.factors[0].evidence_refs == list(factor.evidence_refs)
        assert session.scalar(select(func.count(MatchAssessmentModel.id))) >= 2
        assert session.scalar(select(func.count(MatchFactorModel.id))) >= 2
