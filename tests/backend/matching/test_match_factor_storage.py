"""R55-E6: match_factor keeps every factor and drops only a redundant index.

The explanation shown to the person needs all factors (an UNKNOWN one says what the score
could not see), so storage is reduced by removing `ix_match_factor_assessment`, a strict
prefix of the unique constraint, and by the existing superseded-assessment prune.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from opportunity_radar.matching.models import MatchAssessmentModel, MatchFactorModel
from opportunity_radar.operations.assessment_retention import prune_superseded_assessments
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.matching import _assessment_response
from tests.backend.operations.test_assessment_retention import _Fixture

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_CODES = (
    ("GEOGRAPHY_CONTRACT_FIT", "KNOWN", "NEUTRAL"),
    ("TECHNOLOGY_FIT", "KNOWN", "NEUTRAL"),
    ("COMPANY_PRIORITY", "KNOWN", "NEUTRAL"),
    ("DOMAIN_EXPERIENCE", "UNKNOWN", "NEUTRAL"),
    ("SENIORITY_SCOPE", "KNOWN", "NEUTRAL"),
    ("COMPENSATION", "UNKNOWN", "PENALIZE"),
    ("TIMEZONE", "NOT_APPLICABLE", "EXCLUDE_AND_RENORMALIZE"),
    ("RECENCY", "KNOWN", "NEUTRAL"),
)


@pytest.fixture
def engine() -> Engine:
    return create_database_engine(os.environ["DATABASE_URL"])


@pytest.fixture
def fx(engine: Engine) -> Iterator[_Fixture]:
    fixture = _Fixture(engine)
    try:
        yield fixture
    finally:
        fixture.cleanup()


def _add_full_factor_set(fx: _Fixture, assessment_id: UUID) -> None:
    for code, status, policy in _CODES:
        fx.session.add(
            MatchFactorModel(
                assessment_id=assessment_id,
                factor_code=code,
                weight=Decimal("0.1"),
                raw_score=None if status == "NOT_APPLICABLE" else Decimal("0.5"),
                contribution=Decimal("0") if status == "NOT_APPLICABLE" else Decimal("5"),
                status=status,
                confidence=Decimal("1") if status == "KNOWN" else Decimal("0"),
                missing_policy=policy,
                explanation=f"{code} explanation",
            )
        )
    fx.session.commit()


def test_redundant_factor_index_is_gone_and_the_unique_index_serves_the_lookup(
    engine: Engine, fx: _Fixture
) -> None:
    assessment_id = fx.assessment(fx.posting(), 1)
    with engine.connect() as connection:
        names = set(
            connection.scalars(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'match_factor'")
            )
        )
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            connection.scalars(
                text("EXPLAIN SELECT * FROM matching.match_factor WHERE assessment_id = :id"),
                {"id": assessment_id},
            )
        )
    assert "ix_match_factor_assessment" not in names
    assert "uq_match_factor_assessment_code" in names
    assert "uq_match_factor_assessment_code" in plan


def test_explanation_keeps_every_factor_including_unknown_and_not_applicable(
    engine: Engine, fx: _Fixture
) -> None:
    assessment_id = fx.assessment(fx.posting(), 1)
    _add_full_factor_set(fx, assessment_id)
    with Session(engine) as session:
        assessment = session.scalars(
            select(MatchAssessmentModel).where(MatchAssessmentModel.id == assessment_id)
        ).one()
        response = _assessment_response(assessment)
    codes = [item.factor_code for item in response.factors]
    assert codes == sorted(codes)
    assert {code for code, _, _ in _CODES} <= set(codes)
    by_code = {item.factor_code: item for item in response.factors}
    assert by_code["DOMAIN_EXPERIENCE"].status == "UNKNOWN"
    assert by_code["DOMAIN_EXPERIENCE"].missing_policy == "NEUTRAL"
    assert by_code["TIMEZONE"].raw_score is None
    assert by_code["TECHNOLOGY_FIT"].explanation == "TECHNOLOGY_FIT explanation"


def test_pruned_assessment_takes_all_its_factors_and_current_keeps_its_own(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    old = fx.assessment(posting, 30)
    middle = fx.assessment(posting, 12)
    current = fx.assessment(posting, 1)
    for assessment_id in (old, middle, current):
        _add_full_factor_set(fx, assessment_id)
    before = fx.factor_count()

    prune_superseded_assessments(engine, retention_days=7, dry_run=False)

    assert fx.surviving() == {middle, current}
    assert fx.factor_count() == before - (len(_CODES) + 1)
    with Session(engine) as session:
        kept = session.scalar(
            text("SELECT count(*) FROM matching.match_factor WHERE assessment_id = :id"),
            {"id": current},
        )
    assert kept == len(_CODES) + 1
