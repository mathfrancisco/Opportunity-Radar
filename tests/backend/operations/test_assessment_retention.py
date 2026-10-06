"""Pruning keeps what is current or worked on, and deletes only what a newer one replaced.

The prune runs on its own sessions and commits, so these tests commit their fixture and
clean it up by hand. Assertions are made on the fixture's own rows, never on table totals,
because the test database is shared.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, Engine, delete, func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.companies import models as _companies_models  # noqa: F401
from opportunity_radar.matching.models import (
    CurrentAssessmentModel,
    MatchAnalysisClaimModel,
    MatchAnalysisModel,
    MatchAssessmentModel,
    MatchFactorModel,
)
from opportunity_radar.operations.assessment_retention import prune_superseded_assessments
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.platform.backup import with_database
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)
from scripts import prune_assessments as script
from scripts.restore_check import create_database, drop_database

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)
DAYS = 7


class _Fixture:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session = Session(engine)
        profile = self.session.scalar(select(CareerProfileModel).limit(1))
        self.created_profile: UUID | None = None
        if profile is None:
            profile = CareerProfileModel(version=1)
            self.session.add(profile)
            self.session.flush()
            self.created_profile = profile.id
        number = self.session.scalar(
            select(func.coalesce(func.max(ProfileVersionModel.number), 0)).where(
                ProfileVersionModel.career_profile_id == profile.id
            )
        )
        self.profile_ids = [self._profile_version(profile.id, (number or 0) + 1)]
        self.opportunity_ids: list[UUID] = []
        self.assessment_ids: list[UUID] = []
        self.session.commit()

    def _profile_version(self, career_profile_id: UUID, number: int) -> UUID:
        version = ProfileVersionModel(
            career_profile_id=career_profile_id, number=number, status="DRAFT"
        )
        self.session.add(version)
        self.session.flush()
        # Other suites read every profile version and expect it to carry a preference.
        self.session.add(EmploymentPreferenceModel(profile_version_id=version.id))
        self.session.flush()
        return version.id

    @property
    def profile_id(self) -> UUID:
        return self.profile_ids[0]

    def second_profile(self) -> UUID:
        profile = self.session.scalar(select(CareerProfileModel).limit(1))
        assert profile is not None
        number = self.session.scalar(
            select(func.max(ProfileVersionModel.number)).where(
                ProfileVersionModel.career_profile_id == profile.id
            )
        )
        self.profile_ids.append(self._profile_version(profile.id, (number or 0) + 1))
        self.session.commit()
        return self.profile_ids[-1]

    def posting(self, *, lifecycle: str = "ACTIVE") -> UUID:
        marker = uuid4().hex[:8]
        opportunity = OpportunityModel(
            fingerprint=uuid4().hex,
            fingerprint_version="v1",
            canonical_title="Prune probe",
            normalized_title="prune probe",
            company_name=f"Probe {marker}",
            normalized_company_name=f"probe-{marker}",
            work_mode="REMOTE",
            seniority="UNKNOWN",
            contract_type="FULL_TIME",
            lifecycle_status=lifecycle,
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
        profile_id: UUID | None = None,
        version: int = 1,
    ) -> UUID:
        assessment = MatchAssessmentModel(
            opportunity_id=opportunity_id,
            opportunity_version=version,
            profile_version_id=profile_id or self.profile_id,
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
            # Same instant as `created_at`, so the current pointer's ordering and the prune's
            # agree unless a test makes them differ with `version`.
            assessed_at=NOW - timedelta(days=age_days),
            created_at=NOW - timedelta(days=age_days),
        )
        assessment.factors.append(
            MatchFactorModel(
                factor_code="SKILLS",
                weight=Decimal("0.5"),
                contribution=Decimal("10"),
                status="KNOWN",
                confidence=Decimal("0.9"),
                missing_policy="NEUTRAL",
                explanation="probe",
            )
        )
        self.session.add(assessment)
        self.session.commit()
        self.assessment_ids.append(assessment.id)
        return assessment.id

    def analysis(self, assessment_id: UUID) -> None:
        self.session.add(
            MatchAnalysisModel(
                assessment_id=assessment_id,
                cache_key="a" * 64,
                status="AI_SKIPPED",
                schema_version="v1",
                analyzed_at=NOW,
            )
        )
        self.session.commit()

    def claim(self, assessment_id: UUID) -> None:
        self.session.add(
            MatchAnalysisClaimModel(
                assessment_id=assessment_id,
                owner="probe",
                claimed_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        self.session.commit()

    def application(self, opportunity_id: UUID, profile_id: UUID | None = None) -> None:
        self.session.add(
            ApplicationProcessModel(
                opportunity_id=opportunity_id,
                profile_version_id=profile_id or self.profile_id,
                current_stage="INTERESTED",
                started_at=NOW,
            )
        )
        self.session.commit()

    def surviving(self) -> set[UUID]:
        self.session.expire_all()
        return set(
            self.session.scalars(
                select(MatchAssessmentModel.id).where(
                    MatchAssessmentModel.id.in_(self.assessment_ids)
                )
            )
        )

    def factor_count(self) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(MatchFactorModel)
                .where(MatchFactorModel.assessment_id.in_(self.assessment_ids))
            )
            or 0
        )

    def cleanup(self) -> None:
        s = self.session
        s.rollback()
        # The immutability triggers refuse deletes unless the prune setting is on.
        s.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
        mine = select(MatchAssessmentModel.id).where(
            MatchAssessmentModel.opportunity_id.in_(self.opportunity_ids)
        )
        s.execute(
            delete(CurrentAssessmentModel).where(
                CurrentAssessmentModel.opportunity_id.in_(self.opportunity_ids)
            )
        )
        for model in (MatchAnalysisClaimModel, MatchAnalysisModel, MatchFactorModel):
            s.execute(delete(model).where(model.assessment_id.in_(mine)))
        s.execute(
            delete(ApplicationProcessModel).where(
                ApplicationProcessModel.opportunity_id.in_(self.opportunity_ids)
            )
        )
        s.execute(
            delete(MatchAssessmentModel).where(
                MatchAssessmentModel.opportunity_id.in_(self.opportunity_ids)
            )
        )
        s.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(self.opportunity_ids)))
        s.execute(
            delete(EmploymentPreferenceModel).where(
                EmploymentPreferenceModel.profile_version_id.in_(self.profile_ids)
            )
        )
        s.execute(
            delete(ProfileVersionModel).where(ProfileVersionModel.id.in_(self.profile_ids))
        )
        if self.created_profile is not None:
            s.execute(
                delete(CareerProfileModel).where(CareerProfileModel.id == self.created_profile)
            )
        s.commit()
        s.close()


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


def _prune(engine: Engine, **kwargs: object) -> None:
    prune_superseded_assessments(engine, retention_days=DAYS, dry_run=False, **kwargs)  # type: ignore[arg-type]


def test_superseded_assessments_go_with_their_factors_and_the_rest_stays(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    old = fx.assessment(posting, 30)
    superseded_recently = fx.assessment(posting, 12)
    # Superseded only by a row that is itself younger than the window: kept.
    recent_old = fx.assessment(posting, 5)
    latest = fx.assessment(posting, 1)
    assert fx.factor_count() == 4

    _prune(engine)

    # `old` is superseded by the 12-day row; the 12-day one by the 5-day row, which is
    # inside the window, so it stays; so do the two newest.
    assert fx.surviving() == {superseded_recently, recent_old, latest}
    assert old not in fx.surviving()
    assert fx.factor_count() == 3


def test_the_latest_assessment_is_kept_however_old(engine: Engine, fx: _Fixture) -> None:
    posting = fx.posting()
    latest = fx.assessment(posting, 90)

    _prune(engine)

    assert fx.surviving() == {latest}


def test_an_assessment_superseded_inside_the_window_is_kept(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    older = fx.assessment(posting, 30)
    newer = fx.assessment(posting, 2)

    _prune(engine)

    assert fx.surviving() == {older, newer}


def test_an_assessment_with_an_ai_analysis_is_kept(engine: Engine, fx: _Fixture) -> None:
    posting = fx.posting()
    analysed = fx.assessment(posting, 30)
    plain = fx.assessment(posting, 20)
    latest = fx.assessment(posting, 10)
    fx.analysis(analysed)

    _prune(engine)

    assert fx.surviving() == {analysed, latest}
    assert plain not in fx.surviving()


def test_an_assessment_with_an_application_is_kept(engine: Engine, fx: _Fixture) -> None:
    posting = fx.posting()
    other = fx.posting()
    applied_old = fx.assessment(posting, 30)
    applied_latest = fx.assessment(posting, 10)
    unrelated_old = fx.assessment(other, 30)
    unrelated_latest = fx.assessment(other, 10)
    fx.application(posting)

    _prune(engine)

    assert fx.surviving() == {applied_old, applied_latest, unrelated_latest}
    assert unrelated_old not in fx.surviving()


def test_an_application_for_another_profile_version_does_not_protect(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    second = fx.second_profile()
    old = fx.assessment(posting, 30)
    latest = fx.assessment(posting, 10)
    fx.application(posting, second)

    _prune(engine)

    assert fx.surviving() == {latest}
    assert old not in fx.surviving()


def test_an_assessment_with_a_live_analysis_lease_is_kept(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    leased = fx.assessment(posting, 30)
    latest = fx.assessment(posting, 10)
    fx.claim(leased)

    _prune(engine)

    assert fx.surviving() == {leased, latest}


def test_each_profile_version_keeps_its_own_latest(engine: Engine, fx: _Fixture) -> None:
    posting = fx.posting()
    second = fx.second_profile()
    first_old = fx.assessment(posting, 40)
    first_latest = fx.assessment(posting, 30)
    second_old = fx.assessment(posting, 35, profile_id=second)
    second_latest = fx.assessment(posting, 20, profile_id=second)

    _prune(engine)

    assert fx.surviving() == {first_latest, second_latest}
    assert {first_old, second_old}.isdisjoint(fx.surviving())


def test_a_dry_run_deletes_nothing_and_reports_what_a_real_run_deletes(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    for age in (40, 30, 20, 10):
        fx.assessment(posting, age)
    before = fx.surviving()

    dry = prune_superseded_assessments(engine, retention_days=DAYS, now=NOW)
    assert fx.surviving() == before
    assert fx.factor_count() == 4

    real = prune_superseded_assessments(
        engine, retention_days=DAYS, dry_run=False, now=NOW
    )
    assert dry.dry_run is True and real.dry_run is False
    assert dry.deleted == real.deleted
    assert dry.deletable == real.deletable
    assert len(before) - len(fx.surviving()) == 3 <= real.deleted
    assert real.rows_remaining == real.rows_before - real.deleted


def test_the_average_per_open_posting_drops_to_at_most_three(
    engine: Engine, fx: _Fixture
) -> None:
    postings = [fx.posting() for _ in range(4)]
    for posting in postings:
        for age in range(60, 0, -3):
            fx.assessment(posting, age)
    closed = fx.posting(lifecycle="CLOSED")
    fx.assessment(closed, 50)
    fx.assessment(closed, 40)

    _prune(engine)

    fx.session.expire_all()
    counts = [
        fx.session.scalar(
            select(func.count())
            .select_from(MatchAssessmentModel)
            .where(MatchAssessmentModel.opportunity_id == posting)
        )
        for posting in postings
    ]
    assert all(count is not None and count <= 3 for count in counts)
    assert sum(c or 0 for c in counts) / len(counts) <= 3


def test_the_batch_bound_is_respected(engine: Engine, fx: _Fixture) -> None:
    posting = fx.posting()
    for age in (50, 40, 30, 20, 10):
        fx.assessment(posting, age)

    report = prune_superseded_assessments(
        engine, retention_days=DAYS, batch_size=2, max_batches=1, dry_run=False, now=NOW
    )

    assert report.deleted == 2
    assert len(fx.surviving()) == 3
    assert report.deletable >= 3


def test_the_script_deletes_nothing_without_apply(
    engine: Engine, fx: _Fixture, capsys: pytest.CaptureFixture[str]
) -> None:
    posting = fx.posting()
    for age in (40, 30, 20):
        fx.assessment(posting, age)
    before = fx.surviving()

    script.main(["--days", str(DAYS)])
    report = json.loads(capsys.readouterr().out)

    assert report["dry_run"] is True
    assert report["deletable"] >= 2
    assert report["deleted"] >= 2
    assert fx.surviving() == before

    script.main(["--days", str(DAYS), "--apply", "--batch-size", "2", "--max-batches", "1"])
    applied = json.loads(capsys.readouterr().out)

    assert applied["dry_run"] is False
    assert applied["deleted"] <= 2


REPO_ROOT = Path(__file__).resolve().parents[3]
_ALLOW = "SELECT set_config('matching.allow_prune', 'on', true)"
_DELETE_ASSESSMENT = "DELETE FROM matching.match_assessment WHERE id = :id"
_DELETE_FACTORS = "DELETE FROM matching.match_factor WHERE assessment_id = :id"
_UPDATE_ASSESSMENT = "UPDATE matching.match_assessment SET score = 1 WHERE id = :id"
_UPDATE_FACTOR = "UPDATE matching.match_factor SET explanation = 'x' WHERE assessment_id = :id"


def _alembic(url: str, *args: str) -> None:
    result = subprocess.run(
        ["alembic", *args],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _refusal(connection: Connection, *statements: str, params: dict[str, object]) -> str | None:
    """Run the statements in one transaction; the error text if it was refused, else None."""
    try:
        with connection.begin():
            for statement in statements:
                connection.execute(text(statement), params)
    except Exception as error:  # noqa: BLE001 - the trigger's message is what is asserted
        return str(error)
    return None


def test_updates_are_refused_with_and_without_the_setting(
    engine: Engine, fx: _Fixture
) -> None:
    assessment = {"id": fx.assessment(fx.posting(), 5)}
    with engine.connect() as connection:
        for update, message in (
            (_UPDATE_ASSESSMENT, "match assessments are immutable"),
            (_UPDATE_FACTOR, "match factors are immutable"),
        ):
            assert message in (_refusal(connection, update, params=assessment) or "")
            assert message in (_refusal(connection, _ALLOW, update, params=assessment) or "")


def test_deletes_are_refused_without_the_setting(engine: Engine, fx: _Fixture) -> None:
    assessment = {"id": fx.assessment(fx.posting(), 5)}
    with engine.connect() as connection:
        factor = _refusal(connection, _DELETE_FACTORS, params=assessment)
        parent = _refusal(connection, _DELETE_ASSESSMENT, params=assessment)

    assert "match factors are immutable" in (factor or "")
    assert "match assessments are immutable" in (parent or "")
    assert len(fx.surviving()) == 1


def test_the_setting_does_not_leak_to_the_next_transaction(
    engine: Engine, fx: _Fixture
) -> None:
    posting = fx.posting()
    first = fx.assessment(posting, 5)
    second = fx.assessment(posting, 4)
    with engine.connect() as connection:
        # `first` is not pointed at (the pointer follows `second`), so it may go.
        allowed = _refusal(
            connection, _ALLOW, _DELETE_FACTORS, _DELETE_ASSESSMENT, params={"id": first}
        )
        # Same pooled connection, next transaction: the guard is back.
        refused = _refusal(connection, _DELETE_FACTORS, params={"id": second})

    assert allowed is None
    assert "match factors are immutable" in (refused or "")
    assert fx.surviving() == {second}


def test_the_migration_round_trips() -> None:
    url = os.environ["DATABASE_URL"]
    name = f"f5008_mig_{uuid4().hex[:12]}"
    create_database(url, name)
    try:
        scratch = with_database(url, name)
        _alembic(scratch, "upgrade", "head")
        scratch_engine = create_database_engine(scratch)
        fixture = _Fixture(scratch_engine)
        try:
            posting = fixture.posting()
            ids = [fixture.assessment(posting, age) for age in (30, 20, 10)]
            fixture.session.close()

            def prune_one(assessment_id: UUID) -> str | None:
                with scratch_engine.connect() as connection:
                    return _refusal(
                        connection,
                        _ALLOW,
                        _DELETE_FACTORS,
                        _DELETE_ASSESSMENT,
                        params={"id": assessment_id},
                    )

            _alembic(scratch, "downgrade", "20261005_0063")
            assert "immutable" in (prune_one(ids[0]) or "")
            _alembic(scratch, "upgrade", "head")
            assert prune_one(ids[0]) is None
        finally:
            fixture.session.close()
            scratch_engine.dispose()
    finally:
        drop_database(url, name)


def _pointers(fx: _Fixture) -> dict[tuple[UUID, UUID], UUID]:
    fx.session.expire_all()
    rows = fx.session.execute(
        select(
            CurrentAssessmentModel.opportunity_id,
            CurrentAssessmentModel.profile_version_id,
            CurrentAssessmentModel.assessment_id,
        ).where(CurrentAssessmentModel.opportunity_id.in_(fx.opportunity_ids))
    )
    return {(row[0], row[1]): row[2] for row in rows}


def test_pruning_never_removes_or_orphans_a_current_pointer(
    engine: Engine, fx: _Fixture
) -> None:
    plain = fx.posting()
    for age in (40, 30, 20, 10):
        fx.assessment(plain, age)
    # The pointed row is the newest by (version, assessed_at) but the OLDEST by created_at:
    # a rewritten posting assessed late. It must be kept and the batch must not fail.
    rewritten = fx.posting()
    for age in (30, 20, 10):
        fx.assessment(rewritten, age)
    pointed = fx.assessment(rewritten, 50, version=2)
    pointers_before = _pointers(fx)
    assert len(pointers_before) == 2
    assert pointed in pointers_before.values()

    report = prune_superseded_assessments(
        engine, retention_days=DAYS, batch_size=2, dry_run=False, now=NOW
    )

    assert report.kept_as_current >= 1
    assert _pointers(fx) == pointers_before
    assert set(pointers_before.values()) <= fx.surviving()
