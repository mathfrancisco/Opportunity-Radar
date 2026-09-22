"""The currency rule, component by component, in both of its implementations.

The worker asks "is this current" over ORM objects and the Inbox asks it in SQL over the
whole catalogue. Each case below is asserted against both, because the failure this guards
against is not either one being wrong on its own — it is the two drifting apart, which
shows up as an Inbox that disagrees with the worker about what it is looking at.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company  # noqa: F401  (metadata)
from opportunity_radar.matching.currency import (
    CURRENCY_COMPONENTS,
    EvaluationIdentity,
    assessment_reference_day,
    is_current_assessment,
    opportunity_taxonomy_version,
    reference_day,
)
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.repository import (
    AssessmentRecord,
    SqlAlchemyMatchingRepository,
)
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.models import OpportunityModel, OpportunitySkillModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_TAXONOMY = "skills-v1"


def _session() -> Session:
    return Session(create_database_engine(os.environ["DATABASE_URL"]))


def _profile_version(session: Session) -> ProfileVersionModel:
    profile = session.scalar(select(CareerProfileModel).limit(1))
    if profile is None:
        profile = CareerProfileModel(version=1)
        session.add(profile)
        session.flush()
    highest = session.scalar(
        select(ProfileVersionModel.number)
        .where(ProfileVersionModel.career_profile_id == profile.id)
        .order_by(ProfileVersionModel.number.desc())
        .limit(1)
    )
    version = ProfileVersionModel(
        career_profile_id=profile.id, number=(highest or 0) + 1, status="DRAFT"
    )
    session.add(version)
    session.flush()
    return version


def _opportunity(
    session: Session, *, version: int = 1, taxonomies: tuple[str, ...] = (_TAXONOMY,)
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
        version=version,
    )
    session.add(opportunity)
    session.flush()
    for index, taxonomy in enumerate(taxonomies):
        session.add(
            OpportunitySkillModel(
                opportunity_id=opportunity.id,
                canonical_name=f"skill-{index}",
                display_name=f"Skill {index}",
                requirement="REQUIRED",
                taxonomy_version=taxonomy,
                normalizer_version="normalizer-v1",
                evidence=[],
            )
        )
    session.commit()
    return opportunity


def _assessment(
    session: Session,
    opportunity: OpportunityModel,
    profile_version_id: UUID,
    *,
    opportunity_version: int | None = None,
    rules_version: str = RULES_VERSION,
    taxonomy_version: str = _TAXONOMY,
    assessed_at: datetime | None = None,
) -> MatchAssessmentModel:
    repository = SqlAlchemyMatchingRepository(session)
    assessment = repository.add(
        AssessmentRecord(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity_version or opportunity.version,
            profile_version_id=profile_version_id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version=rules_version,
            taxonomy_version=taxonomy_version,
            opportunity_snapshot={},
            profile_snapshot={},
            eligibility="ELIGIBLE",
            eligibility_details=(),
            verdict="RECOMMENDED",
            score=Decimal("80.0000"),
            confidence=Decimal("0.900"),
            assessed_at=assessed_at or datetime.now(UTC),
        ),
        [],
    )
    session.commit()
    return assessment


def _identity(
    opportunity: OpportunityModel,
    profile_version_id: UUID,
    *,
    taxonomy_version: str = _TAXONOMY,
    assessed_at: datetime | None = None,
) -> EvaluationIdentity:
    return EvaluationIdentity.build(
        opportunity_id=opportunity.id,
        opportunity_version=opportunity.version,
        profile_version_id=profile_version_id,
        rules_version=RULES_VERSION,
        taxonomy_version=taxonomy_version,
        assessed_at=assessed_at or datetime.now(UTC),
    )


def _sql_says_current(
    session: Session,
    opportunity: OpportunityModel,
    assessment: MatchAssessmentModel,
    profile_version_id: UUID,
) -> bool:
    """Ask the read model's predicate about exactly one assessment."""
    scoped = (
        select(MatchAssessmentModel)
        .where(MatchAssessmentModel.id == assessment.id)
        .subquery("scoped_assessment")
    )
    statement = (
        select(
            is_current_assessment(
                scoped,
                rules_version=RULES_VERSION,
                profile_version_id=profile_version_id,
            )
        )
        .select_from(OpportunityModel)
        .join(scoped, scoped.c.opportunity_id == OpportunityModel.id)
        .where(OpportunityModel.id == opportunity.id)
    )
    return bool(session.scalar(statement))


def test_the_currency_components_are_the_four_versions() -> None:
    # The reference day is deliberately absent: a new day does not invalidate a score.
    assert CURRENCY_COMPONENTS == (
        "opportunity_version",
        "profile_version_id",
        "rules_version",
        "taxonomy_version",
    )


def test_an_untouched_assessment_is_current_in_both_implementations() -> None:
    with _session() as session:
        profile = _profile_version(session)
        opportunity = _opportunity(session)
        assessment = _assessment(session, opportunity, profile.id)

        assert _identity(opportunity, profile.id).describes(assessment)
        assert _sql_says_current(session, opportunity, assessment, profile.id)


@pytest.mark.parametrize(
    "component",
    ["opportunity_version", "profile_version_id", "rules_version", "taxonomy_version"],
)
def test_moving_any_single_component_makes_the_assessment_stale(component: str) -> None:
    with _session() as session:
        profile = _profile_version(session)
        opportunity = _opportunity(session)
        overrides: dict[str, object] = {}
        compared_profile = profile.id
        if component == "opportunity_version":
            # The assessment describes the posting as it was one version ago.
            overrides["opportunity_version"] = opportunity.version + 1
            opportunity.version += 2
            session.commit()
        elif component == "profile_version_id":
            compared_profile = _profile_version(session).id
            session.commit()
        elif component == "rules_version":
            overrides["rules_version"] = "matching-v0"
        else:
            overrides["taxonomy_version"] = "skills-v0"
        assessment = _assessment(session, opportunity, profile.id, **overrides)  # type: ignore[arg-type]

        identity = _identity(opportunity, compared_profile)

        assert identity.is_stale(assessment)
        assert not _sql_says_current(session, opportunity, assessment, compared_profile)


def test_a_multi_taxonomy_opportunity_agrees_between_sql_and_the_service() -> None:
    with _session() as session:
        profile = _profile_version(session)
        opportunity = _opportunity(session, taxonomies=("skills-v2", "skills-v1"))
        combined = session.scalar(
            select(opportunity_taxonomy_version()).where(
                OpportunityModel.id == opportunity.id
            )
        )
        assert combined == "skills-v1+skills-v2"
        assessment = _assessment(
            session, opportunity, profile.id, taxonomy_version=combined
        )

        assert _identity(opportunity, profile.id, taxonomy_version=combined).describes(
            assessment
        )
        assert _sql_says_current(session, opportunity, assessment, profile.id)


def test_an_opportunity_without_skills_falls_back_to_the_current_taxonomy() -> None:
    with _session() as session:
        opportunity = _opportunity(session, taxonomies=())

        combined = session.scalar(
            select(opportunity_taxonomy_version()).where(
                OpportunityModel.id == opportunity.id
            )
        )

        assert combined == _TAXONOMY


def test_a_new_day_does_not_make_a_matching_assessment_stale() -> None:
    with _session() as session:
        profile = _profile_version(session)
        opportunity = _opportunity(session)
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assessment = _assessment(session, opportunity, profile.id, assessed_at=yesterday)

        identity = _identity(opportunity, profile.id)

        # Still describes the same inputs, so the Inbox must not flag it.
        assert identity.describes(assessment)
        assert _sql_says_current(session, opportunity, assessment, profile.id)
        # But the daily cap has lifted, so the worker may evaluate it again.
        assert not identity.evaluated_on_reference_day(assessment)


def test_the_same_inputs_on_the_same_day_stay_idempotent() -> None:
    with _session() as session:
        profile = _profile_version(session)
        opportunity = _opportunity(session)
        assessment = _assessment(session, opportunity, profile.id)

        assert _identity(opportunity, profile.id).evaluated_on_reference_day(assessment)


def test_the_reference_day_is_utc_on_both_sides() -> None:
    # 23:30 in Sao Paulo is already the next UTC day. Taking the server's local date
    # instead would move the daily cap by a day for half the evening.
    late = datetime(2026, 9, 21, 23, 30, tzinfo=UTC).astimezone(
        ZoneInfo("America/Sao_Paulo")
    )
    assert reference_day(late) == datetime(2026, 9, 21, 23, 30, tzinfo=UTC).date()

    with _session() as session:
        profile = _profile_version(session)
        opportunity = _opportunity(session)
        assessment = _assessment(session, opportunity, profile.id, assessed_at=late)
        stored_day = session.scalar(
            select(assessment_reference_day(MatchAssessmentModel.assessed_at)).where(
                MatchAssessmentModel.id == assessment.id
            )
        )

        assert stored_day == reference_day(late)
