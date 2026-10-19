"""R55-E2: old opportunities leave with their dependents, applications and relevant ones stay.

The retention commits on its own sessions, so the fixture commits and cleans up by hand.
Assertions are made on the fixture's own rows, never on table totals; the retention itself is
global by age, so only rows this fixture created are expected to change.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
    TavilyExtractCacheModel,
)
from opportunity_radar.companies import models as _companies_models  # noqa: F401
from opportunity_radar.matching.models import (
    CurrentAssessmentModel,
    MatchAnalysisClaimModel,
    MatchAnalysisModel,
    MatchAssessmentModel,
    MatchFactorModel,
)
from opportunity_radar.operations.opportunity_retention import (
    JOB_NAME,
    record_retention_attempt,
    retention_due,
    run_opportunity_retention,
    stale_by_source,
)
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import (
    DuplicateCandidateModel,
    NormalizationResultModel,
    OpportunityModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.pipeline.models import ApplicationProcessModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)
OWNER = "test-opportunity-retention-owner"


class _Fixture:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.session = Session(engine)
        s = self.session
        profile = CareerProfileModel(version=1, owner_sub=OWNER)
        s.add(profile)
        s.flush()
        self.profile_id = self._profile_version(profile.id)
        self.profile = profile.id
        self.source = SourceDefinitionModel(
            id=uuid4(),
            source_type="manual",
            name=f"opp retention probe {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        self.run = SourceRunModel(
            id=uuid4(),
            source_definition_id=self.source.id,
            execution_trigger="ON_DEMAND",
            status="SUCCEEDED",
            started_at=NOW,
            finished_at=NOW,
        )
        s.add_all([self.source, self.run])
        s.commit()
        self.opportunity_ids: list[UUID] = []
        self.raw_ids: list[UUID] = []

    def _profile_version(self, career_profile_id: UUID) -> UUID:
        version = ProfileVersionModel(career_profile_id=career_profile_id, number=1, status="DRAFT")
        self.session.add(version)
        self.session.flush()
        self.session.add(EmploymentPreferenceModel(profile_version_id=version.id))
        self.session.flush()
        return version.id

    def opportunity(
        self,
        age_days: float,
        *,
        published_days: float | None = None,
        updated_days: float | None = None,
        full: bool = False,
        role_family: str = "UNKNOWN",
        allowed_countries: list[str] | None = None,
        evidence: dict[str, str] | None = None,
    ) -> UUID:
        s = self.session
        opportunity = OpportunityModel(
            fingerprint=uuid4().hex,
            fingerprint_version="v1",
            canonical_title="Retention probe",
            normalized_title="retention probe",
            work_mode="REMOTE",
            seniority="UNKNOWN",
            contract_type="FULL_TIME",
            lifecycle_status="ACTIVE",
            first_seen_at=NOW - timedelta(days=age_days),
            published_at=None if published_days is None else NOW - timedelta(days=published_days),
            source_updated_at=None if updated_days is None else NOW - timedelta(days=updated_days),
            role_family=role_family,
            role_family_evidence=evidence,
            allowed_countries=allowed_countries,
            version=1,
        )
        s.add(opportunity)
        s.flush()
        self.opportunity_ids.append(opportunity.id)
        raw_id = self.raw_item(opportunity.id)
        if full:
            self._dependents(opportunity.id, raw_id)
        s.commit()
        return opportunity.id

    def raw_item(self, opportunity_id: UUID) -> UUID:
        s = self.session
        raw = RawItemModel(
            id=uuid4(),
            source_run_id=self.run.id,
            source_definition_id=self.source.id,
            external_id=f"probe-{uuid4().hex[:10]}",
            identity_key=f"external:probe-{uuid4().hex[:10]}",
            payload_hash=uuid4().hex + uuid4().hex,
            item_metadata={},
        )
        raw.payload_record = RawItemPayloadModel(payload={"title": "probe"})
        s.add(raw)
        s.flush()
        self.raw_ids.append(raw.id)
        occurrence = SourceOccurrenceModel(
            id=uuid4(),
            opportunity_id=opportunity_id,
            raw_item_id=raw.id,
            source_definition_id=self.source.id,
            external_id=raw.external_id,
            first_seen_at=NOW,
            last_seen_at=NOW,
            last_seen_run_id=self.run.id,
        )
        s.add(occurrence)
        s.flush()
        s.add(
            SourceOccurrenceObservationModel(
                source_occurrence_id=occurrence.id,
                source_run_id=self.run.id,
                raw_item_id=raw.id,
                content_hash_matched=True,
            )
        )
        s.add(
            NormalizationResultModel(
                raw_item_id=raw.id,
                opportunity_id=opportunity_id,
                source_occurrence_id=occurrence.id,
                status="SUCCEEDED",
                identity_decision="NEW",
                normalizer_version="probe-v1",
            )
        )
        s.flush()
        return raw.id

    def _dependents(self, opportunity_id: UUID, raw_id: UUID) -> None:
        del raw_id
        s = self.session
        assessment = MatchAssessmentModel(
            owner_sub=OWNER,
            opportunity_id=opportunity_id,
            opportunity_version=1,
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
            assessed_at=NOW,
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
        s.add(assessment)
        s.flush()
        s.add(
            MatchAnalysisModel(
                assessment_id=assessment.id,
                cache_key="b" * 64,
                status="AI_SKIPPED",
                schema_version="v1",
                analyzed_at=NOW,
            )
        )
        s.add(
            MatchAnalysisClaimModel(
                assessment_id=assessment.id,
                owner="probe",
                claimed_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
            )
        )
        # The insert above also creates the `current_assessment` pointer (a trigger).
        s.add(
            RelevanceMarkModel(
                owner_sub=OWNER, opportunity_id=opportunity_id, relevant=False, reason="AREA"
            )
        )
        s.flush()

    def duplicate_pair(self, first: UUID, second: UUID) -> None:
        low, high = sorted((first, second), key=str)
        self.session.add(
            DuplicateCandidateModel(
                opportunity_id=low, duplicate_opportunity_id=high, rule="title_location_window"
            )
        )
        self.session.commit()

    def application(self, opportunity_id: UUID) -> None:
        self.session.add(
            ApplicationProcessModel(
                owner_sub=OWNER,
                opportunity_id=opportunity_id,
                profile_version_id=self.profile_id,
                current_stage="INTERESTED",
                started_at=NOW,
            )
        )
        self.session.commit()

    def relevant_mark(self, opportunity_id: UUID) -> None:
        self.session.add(
            RelevanceMarkModel(owner_sub=OWNER, opportunity_id=opportunity_id, relevant=True)
        )
        self.session.commit()

    def count(self, model: type, column: object, ids: list[UUID]) -> int:
        self.session.expire_all()
        return (
            self.session.scalar(
                select(func.count()).select_from(model).where(column.in_(ids))  # type: ignore[attr-defined]
            )
            or 0
        )

    def present(self, ids: list[UUID] | None = None) -> set[UUID]:
        self.session.expire_all()
        return set(
            self.session.scalars(
                select(OpportunityModel.id).where(
                    OpportunityModel.id.in_(ids or self.opportunity_ids)
                )
            )
        )

    def raw_present(self) -> set[UUID]:
        self.session.expire_all()
        return set(
            self.session.scalars(select(RawItemModel.id).where(RawItemModel.id.in_(self.raw_ids)))
        )

    def cleanup(self) -> None:
        s = self.session
        s.rollback()
        s.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
        opps = self.opportunity_ids
        s.execute(
            text("DELETE FROM matching.current_assessment WHERE opportunity_id = ANY(:o)"),
            {"o": opps},
        )
        s.execute(
            text(
                "DELETE FROM matching.match_factor WHERE assessment_id IN "
                "(SELECT id FROM matching.match_assessment WHERE opportunity_id = ANY(:o))"
            ),
            {"o": opps},
        )
        for table in ("crm.application_process", "matching.match_assessment"):
            s.execute(text(f"DELETE FROM {table} WHERE opportunity_id = ANY(:o)"), {"o": opps})
        s.execute(
            text("DELETE FROM opportunities.normalization_result WHERE raw_item_id = ANY(:r)"),
            {"r": self.raw_ids},
        )
        s.execute(
            text("DELETE FROM opportunities.opportunity WHERE id = ANY(:o)"), {"o": opps}
        )
        s.execute(
            text("DELETE FROM acquisition.raw_item WHERE source_definition_id = :s"),
            {"s": self.source.id},
        )
        s.execute(text("DELETE FROM acquisition.source_run WHERE id = :r"), {"r": self.run.id})
        s.execute(
            text("DELETE FROM acquisition.source_definition WHERE id = :s"), {"s": self.source.id}
        )
        s.execute(
            text("DELETE FROM profile.employment_preference WHERE profile_version_id = :p"),
            {"p": self.profile_id},
        )
        s.execute(
            text("DELETE FROM profile.profile_version WHERE id = :p"), {"p": self.profile_id}
        )
        s.execute(
            text("DELETE FROM profile.career_profile WHERE id = :p"), {"p": self.profile}
        )
        s.commit()
        s.close()


@pytest.fixture()
def fx() -> _Fixture:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    fixture = _Fixture(engine)
    try:
        yield fixture  # type: ignore[misc]
    finally:
        fixture.cleanup()
        engine.dispose()


def test_eight_day_old_opportunity_is_deleted_with_every_dependent(fx: _Fixture) -> None:
    old = fx.opportunity(8, full=True)
    partner = fx.opportunity(1)
    fx.duplicate_pair(old, partner)
    assert fx.count(MatchFactorModel, MatchFactorModel.assessment_id, [
        r for r in fx.session.scalars(
            select(MatchAssessmentModel.id).where(MatchAssessmentModel.opportunity_id == old)
        )
    ]) == 1

    report = run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)

    assert old not in fx.present()
    assert partner in fx.present()
    expected = {
        "opportunity": 1,
        "match_assessment": 1,
        "match_factor": 1,
        "match_analysis": 1,
        "match_analysis_claim": 1,
        "current_assessment": 1,
        "source_occurrence": 1,
        "source_occurrence_observation": 1,
        "normalization_result": 1,
        "duplicate_candidate": 1,
        "relevance_mark": 1,
        "raw_item": 1,
        "raw_item_payload": 1,
    }
    for table, number in expected.items():
        assert report.rows.get(table, 0) >= number, table
    # The old opportunity's raw item and payload are gone; the partner's own remain.
    remaining_raw = fx.raw_present()
    assert len(remaining_raw) == 1
    payloads = fx.session.scalar(
        select(func.count()).select_from(RawItemPayloadModel).where(
            RawItemPayloadModel.raw_item_id.in_(fx.raw_ids)
        )
    )
    assert payloads == 1
    for model, column in (
        (SourceOccurrenceModel, SourceOccurrenceModel.opportunity_id),
        (MatchAssessmentModel, MatchAssessmentModel.opportunity_id),
        (CurrentAssessmentModel, CurrentAssessmentModel.opportunity_id),
        (RelevanceMarkModel, RelevanceMarkModel.opportunity_id),
        (NormalizationResultModel, NormalizationResultModel.opportunity_id),
    ):
        assert fx.count(model, column, [old]) == 0, model.__name__
    assert fx.count(DuplicateCandidateModel, DuplicateCandidateModel.opportunity_id, [old]) == 0
    assert report.complete and not report.stopped


def test_rerun_is_idempotent(fx: _Fixture) -> None:
    fx.opportunity(8, full=True)
    first = run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    second = run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert first.opportunities >= 1
    assert second.opportunities == 0
    assert second.rows.get("raw_item", 0) == 0
    assert second.batches == 0


def test_recent_opportunity_is_kept(fx: _Fixture) -> None:
    recent = fx.opportunity(6, full=True)
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert recent in fx.present()
    assert len(fx.raw_present()) == 1


def test_old_multi_occurrence_opportunity_goes_with_every_occurrence_and_raw_item(
    fx: _Fixture,
) -> None:
    """R55-E4: a job attached to two sources is one opportunity, deleted once, whole."""
    old = fx.opportunity(8, full=True)
    fx.raw_item(old)
    fx.session.commit()
    assert fx.count(SourceOccurrenceModel, SourceOccurrenceModel.opportunity_id, [old]) == 2

    report = run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)

    assert old not in fx.present()
    assert fx.count(SourceOccurrenceModel, SourceOccurrenceModel.opportunity_id, [old]) == 0
    assert fx.raw_present() == set()
    assert report.rows.get("source_occurrence", 0) >= 2
    assert report.rows.get("raw_item", 0) >= 2


def test_recent_multi_occurrence_opportunity_is_kept_with_both_occurrences(
    fx: _Fixture,
) -> None:
    recent = fx.opportunity(2, full=True)
    fx.raw_item(recent)
    fx.session.commit()

    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)

    assert recent in fx.present()
    assert fx.count(SourceOccurrenceModel, SourceOccurrenceModel.opportunity_id, [recent]) == 2
    assert len(fx.raw_present()) == 2


def test_old_multi_occurrence_opportunity_with_application_keeps_every_occurrence(
    fx: _Fixture,
) -> None:
    kept = fx.opportunity(30, full=True)
    fx.raw_item(kept)
    fx.session.commit()
    fx.application(kept)

    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)

    assert kept in fx.present()
    assert fx.count(SourceOccurrenceModel, SourceOccurrenceModel.opportunity_id, [kept]) == 2
    assert len(fx.raw_present()) == 2


def test_published_at_wins_over_first_seen(fx: _Fixture) -> None:
    posted_long_ago = fx.opportunity(0.5, published_days=9)
    posted_recently = fx.opportunity(30, published_days=2)
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert posted_long_ago not in fx.present()
    assert posted_recently in fx.present()


def test_old_opportunity_with_application_is_kept_with_its_dependents(fx: _Fixture) -> None:
    kept = fx.opportunity(30, full=True)
    fx.application(kept)
    gone = fx.opportunity(30, full=True)
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert fx.present() == {kept}
    assert gone not in fx.present()
    assert fx.count(MatchAssessmentModel, MatchAssessmentModel.opportunity_id, [kept]) == 1
    assert fx.count(CurrentAssessmentModel, CurrentAssessmentModel.opportunity_id, [kept]) == 1
    assert len(fx.raw_present()) == 1


def test_old_opportunity_with_relevant_mark_is_kept(fx: _Fixture) -> None:
    kept = fx.opportunity(30, full=True)
    fx.relevant_mark(kept)
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert kept in fx.present()
    assert fx.count(RelevanceMarkModel, RelevanceMarkModel.opportunity_id, [kept]) == 2
    assert len(fx.raw_present()) == 1


def test_raw_item_still_referenced_by_a_kept_opportunity_is_kept(fx: _Fixture) -> None:
    old = fx.opportunity(30)
    kept = fx.opportunity(1)
    old_raw = next(
        iter(
            fx.session.scalars(
                select(SourceOccurrenceModel.raw_item_id).where(
                    SourceOccurrenceModel.opportunity_id == old
                )
            )
        )
    )
    # A later normalisation of the same evidence points at the kept opportunity.
    kept_occurrence = fx.session.scalar(
        select(SourceOccurrenceModel.id).where(SourceOccurrenceModel.opportunity_id == kept)
    )
    fx.session.add(
        NormalizationResultModel(
            raw_item_id=old_raw,
            opportunity_id=kept,
            source_occurrence_id=kept_occurrence,
            status="SUCCEEDED",
            identity_decision="REFRESHED",
            normalizer_version="probe-v2",
        )
    )
    fx.session.commit()
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert old not in fx.present()
    assert kept in fx.present()
    assert old_raw in fx.raw_present()
    assert len(fx.raw_present()) == 2


def test_dry_run_deletes_nothing_and_reports_counts(fx: _Fixture) -> None:
    old = fx.opportunity(30, full=True)
    protected = fx.opportunity(30, full=True)
    fx.application(protected)
    marked = fx.opportunity(30)
    fx.relevant_mark(marked)

    report = run_opportunity_retention(fx.engine, retention_days=7)

    assert report.dry_run is True
    assert fx.present() == {old, protected, marked}
    assert len(fx.raw_present()) == 3
    assert report.rows["opportunity"] >= 1
    assert report.rows["match_assessment"] >= 1
    assert report.rows["raw_item"] >= 1
    assert report.rows["raw_item_payload"] >= 1
    assert report.kept_with_application >= 1
    assert report.kept_with_relevant_mark >= 1
    dumped = report.as_dict()
    assert dumped["dry_run"] is True and isinstance(dumped["cutoff"], str)


def test_batches_are_oldest_first_and_bounded(fx: _Fixture) -> None:
    oldest = fx.opportunity(4000)
    middle = fx.opportunity(3999)
    newest_old = fx.opportunity(3998)
    older_elsewhere = fx.session.scalar(
        text(
            "SELECT count(*) FROM opportunities.opportunity "
            "WHERE coalesce(published_at, first_seen_at) < :t AND id <> ALL(:mine)"
        ),
        {"t": NOW - timedelta(days=3999), "mine": fx.opportunity_ids},
    )
    assert older_elsewhere == 0, "the shared test database holds older rows than the probe"

    report = run_opportunity_retention(
        fx.engine, retention_days=7, batch_size=1, max_batches=1, dry_run=False
    )

    assert report.batches == 1 and report.complete is False
    assert fx.present() == {middle, newest_old}
    assert oldest not in fx.present()


def test_retention_days_zero_skips_the_opportunity_part(fx: _Fixture) -> None:
    old = fx.opportunity(30, full=True)
    report = run_opportunity_retention(fx.engine, retention_days=0, dry_run=False)
    assert report.cutoff is None and report.batches == 0 and report.opportunities == 0
    assert old in fx.present()


def test_a_survivor_is_kept_while_a_kept_duplicate_points_at_it(fx: _Fixture) -> None:
    survivor = fx.opportunity(30)
    kept_duplicate = fx.opportunity(1)
    fx.session.get(OpportunityModel, kept_duplicate).duplicate_of = survivor  # type: ignore[union-attr]
    fx.session.commit()
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert fx.present() == {survivor, kept_duplicate}
    fx.session.expire_all()
    assert fx.session.get(OpportunityModel, kept_duplicate).duplicate_of == survivor  # type: ignore[union-attr]


def test_a_survivor_and_its_old_duplicate_go_together(fx: _Fixture) -> None:
    survivor = fx.opportunity(30)
    duplicate = fx.opportunity(31)
    fx.session.get(OpportunityModel, duplicate).duplicate_of = survivor  # type: ignore[union-attr]
    fx.session.commit()
    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert fx.present() == set()


def test_batch_rechecks_protection_after_the_lock(
    fx: _Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opportunity_radar.operations import opportunity_retention as module

    protected = fx.opportunity(30, full=True)
    fx.application(protected)
    # A lock statement that (as after a concurrent commit) still returns the protected row.
    monkeypatch.setattr(
        module,
        "_LOCK_BATCH",
        "SELECT o.id FROM opportunities.opportunity o WHERE o.id = ANY(:mine) "
        "AND :cutoff IS NOT NULL AND :batch_size > 0 FOR UPDATE OF o SKIP LOCKED",
    )
    original = module.text
    monkeypatch.setattr(
        module,
        "text",
        lambda sql: (
            original(sql).bindparams(mine=[protected])
            if sql is module._LOCK_BATCH
            else original(sql)
        ),
    )
    report = run_opportunity_retention(fx.engine, retention_days=7, dry_run=False, max_batches=1)
    assert protected in fx.present()
    assert report.opportunities == 0


def test_purges_run_even_when_the_opportunity_delete_fails(
    fx: _Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opportunity_radar.operations import opportunity_retention as module

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret detail that must not reach the report")

    monkeypatch.setattr(module, "_delete_all", boom)
    called: list[str] = []
    monkeypatch.setattr(module, "_purge_ai_call_records", lambda *a, **k: called.append("ai"))
    monkeypatch.setattr(module, "_purge_tavily_cache", lambda *a, **k: called.append("tavily"))
    report = run_opportunity_retention(
        fx.engine, retention_days=7, ai_call_record_retention_days=7, dry_run=False
    )
    assert called == ["ai", "tavily"]
    assert report.errors == {"opportunities": "RuntimeError"} and report.complete is False


def test_a_failing_purge_does_not_stop_the_other(
    fx: _Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from opportunity_radar.operations import opportunity_retention as module

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("x")

    monkeypatch.setattr(module, "_purge_ai_call_records", boom)
    called: list[str] = []
    monkeypatch.setattr(module, "_purge_tavily_cache", lambda *a, **k: called.append("tavily"))
    report = run_opportunity_retention(
        fx.engine, retention_days=7, ai_call_record_retention_days=7, dry_run=False
    )
    assert called == ["tavily"] and report.errors == {"ai_call_record": "ValueError"}


def test_stop_callback_ends_the_run_before_the_next_batch(fx: _Fixture) -> None:
    fx.opportunity(30)
    fx.opportunity(31)
    report = run_opportunity_retention(
        fx.engine, retention_days=7, dry_run=False, should_stop=lambda: True
    )
    assert report.stopped and not report.complete and report.batches == 0
    assert len(fx.present()) == 2


def test_expired_tavily_cache_and_old_ai_call_records_are_purged(fx: _Fixture) -> None:
    with Session(fx.engine) as s, s.begin():
        s.add_all(
            [
                TavilyExtractCacheModel(
                    url_hash=uuid4().hex + uuid4().hex,
                    canonical_url="https://example.test/expired",
                    status="success",
                    expires_at=NOW - timedelta(hours=1),
                ),
                TavilyExtractCacheModel(
                    url_hash=uuid4().hex + uuid4().hex,
                    canonical_url="https://example.test/live",
                    status="success",
                    expires_at=NOW + timedelta(days=1),
                ),
            ]
        )
        ids = {"old": uuid4(), "new": uuid4()}
        for key, age in (("old", 8), ("new", 1)):
            s.execute(
                text(
                    "INSERT INTO platform.ai_call_record (id, task, provider, model, attempt, "
                    "success, fallback_used, cache_hit, created_at) VALUES (:id, 'probe', "
                    "'probe', 'probe', 1, true, false, false, :at)"
                ),
                {"id": ids[key], "at": NOW - timedelta(days=age)},
            )
    try:
        dry = run_opportunity_retention(
            fx.engine, retention_days=7, ai_call_record_retention_days=7
        )
        assert dry.rows["tavily_extract_cache"] >= 1 and dry.rows["ai_call_record"] >= 1
        report = run_opportunity_retention(
            fx.engine, retention_days=7, ai_call_record_retention_days=7, dry_run=False
        )
        assert report.rows["tavily_extract_cache"] >= 1
        assert report.rows["ai_call_record"] >= 1
        with Session(fx.engine) as s:
            left = set(
                s.scalars(
                    text(
                        "SELECT id FROM platform.ai_call_record WHERE id = ANY(:ids)"
                    ),
                    {"ids": list(ids.values())},
                )
            )
            live = s.scalar(
                text(
                    "SELECT count(*) FROM acquisition.tavily_extract_cache "
                    "WHERE canonical_url = 'https://example.test/live'"
                )
            )
        assert left == {ids["new"]}
        assert live == 1
    finally:
        with Session(fx.engine) as s, s.begin():
            s.execute(text("DELETE FROM platform.ai_call_record WHERE id = ANY(:i)"),
                      {"i": list(ids.values())})
            s.execute(
                text(
                    "DELETE FROM acquisition.tavily_extract_cache "
                    "WHERE canonical_url LIKE 'https://example.test/%'"
                )
            )


def test_retention_is_due_once_per_utc_day(fx: _Fixture) -> None:
    day = datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
    with Session(fx.engine) as s, s.begin():
        s.execute(
            text("DELETE FROM platform.worker_job_state WHERE job_name = :j"), {"j": JOB_NAME}
        )
    try:
        assert retention_due(fx.engine, now=day)
        record_retention_attempt(fx.engine, success=False, error="Boom", now=day)
        assert retention_due(fx.engine, now=day)  # a failed or partial run does not count
        record_retention_attempt(fx.engine, success=True, now=day)
        assert not retention_due(fx.engine, now=day.replace(hour=23, minute=59))
        assert retention_due(fx.engine, now=day + timedelta(days=1))
        record_retention_attempt(
            fx.engine, success=False, error="Boom", now=day + timedelta(days=1)
        )
        assert retention_due(fx.engine, now=day + timedelta(days=1))  # success kept, not erased
    finally:
        with Session(fx.engine) as s, s.begin():
            s.execute(
                text("DELETE FROM platform.worker_job_state WHERE job_name = :j"), {"j": JOB_NAME}
            )


def test_undated_opportunity_with_old_source_updated_at_is_old(fx: _Fixture) -> None:
    # R55-A5: first seen today, but the source says it last changed 20 days ago.
    stale = fx.opportunity(0, updated_days=20)
    fresh_update = fx.opportunity(0, updated_days=2)
    never_updated = fx.opportunity(0)
    dated = fx.opportunity(0, published_days=1, updated_days=20)

    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)

    assert stale not in fx.present()
    assert {fresh_update, never_updated, dated} <= fx.present()


def test_stale_report_counts_per_source_and_applies_with_protections(fx: _Fixture) -> None:
    from scripts import stale_cleanup_report

    plain = fx.opportunity(0, updated_days=20)
    with_application = fx.opportunity(0, updated_days=20)
    fx.application(with_application)
    marked = fx.opportunity(0, updated_days=30)
    fx.relevant_mark(marked)
    fresh = fx.opportunity(0, updated_days=1)

    def mine() -> dict[str, int]:
        rows = [r for r in stale_by_source(fx.engine) if r.source_name == fx.source.name]
        assert len(rows) == 1
        return {
            "stale": rows[0].stale_opportunities,
            "application": rows[0].kept_with_application,
            "relevant": rows[0].kept_with_relevant_mark,
            "eligible": rows[0].eligible_opportunities,
            "raw": rows[0].linked_raw_items,
        }

    assert mine() == {"stale": 3, "application": 1, "relevant": 1, "eligible": 1, "raw": 1}
    # Reporting deletes nothing.
    assert {plain, with_application, marked, fresh} <= fx.present()

    stale_cleanup_report.main(["--apply"])

    assert plain not in fx.present()
    assert {with_application, marked, fresh} <= fx.present()
    assert mine()["eligible"] == 0


def test_stale_report_counts_an_opportunity_without_occurrence_as_no_source(
    fx: _Fixture,
) -> None:
    orphan = fx.opportunity(0, updated_days=20)
    fx.session.execute(
        text("DELETE FROM opportunities.normalization_result WHERE opportunity_id = :o"),
        {"o": orphan},
    )
    fx.session.execute(
        text(
            "DELETE FROM opportunities.source_occurrence_observation WHERE source_occurrence_id "
            "IN (SELECT id FROM opportunities.source_occurrence WHERE opportunity_id = :o)"
        ),
        {"o": orphan},
    )
    fx.session.execute(
        text("DELETE FROM opportunities.source_occurrence WHERE opportunity_id = :o"),
        {"o": orphan},
    )
    fx.session.commit()

    rows = {r.source_name: r for r in stale_by_source(fx.engine)}
    assert rows["no_source"].eligible_opportunities >= 1

    run_opportunity_retention(fx.engine, retention_days=7, dry_run=False)
    assert orphan not in fx.present()


# --- R55-B5: shorter retention for opportunities outside the profile's areas/countries ------

_TARGET_FAMILIES = ("SOFTWARE_ENGINEERING", "DATA")
#: What `classify_role_family` stores when the title alone decided the area.
_TITLE = {"rule": "title", "term": "account executive", "origin": "title"}


def _off_target_run(fx: _Fixture, **overrides: object):
    options: dict[str, object] = {
        "retention_days": 7,
        "off_target_retention_days": 2,
        "target_role_families": _TARGET_FAMILIES,
        "target_countries": ("BR",),
        "dry_run": False,
    }
    options.update(overrides)
    return run_opportunity_retention(fx.engine, **options)  # type: ignore[arg-type]


def test_off_target_area_goes_after_the_short_threshold_on_target_stays(fx: _Fixture) -> None:
    off_area = fx.opportunity(3, role_family="SALES", evidence=_TITLE)
    on_target = fx.opportunity(3, role_family="SOFTWARE_ENGINEERING")
    unknown_area = fx.opportunity(3, role_family="UNKNOWN")
    young_off_area = fx.opportunity(1, role_family="SALES", evidence=_TITLE)

    report = _off_target_run(fx)

    assert fx.present() == {on_target, unknown_area, young_off_area}
    assert off_area not in fx.present()
    assert report.rows["opportunity_off_target"] >= 1
    assert report.off_target_retention_days == 2


def test_off_target_country_goes_but_any_empty_and_target_country_stay(fx: _Fixture) -> None:
    other_country = fx.opportunity(3, role_family="DATA", allowed_countries=["US"])
    worldwide = fx.opportunity(3, role_family="DATA", allowed_countries=["ANY"])
    unknown_country = fx.opportunity(3, role_family="DATA", allowed_countries=[])
    never_derived = fx.opportunity(3, role_family="DATA", allowed_countries=None)
    includes_target = fx.opportunity(3, role_family="DATA", allowed_countries=["US", "BR"])

    _off_target_run(fx)

    assert fx.present() == {worldwide, unknown_country, never_derived, includes_target}
    assert other_country not in fx.present()


def test_off_target_keeps_protected_opportunities(fx: _Fixture) -> None:
    applied = fx.opportunity(3, role_family="SALES", evidence=_TITLE)
    fx.application(applied)
    marked = fx.opportunity(3, role_family="SALES", evidence=_TITLE)
    fx.relevant_mark(marked)

    _off_target_run(fx)

    assert fx.present() == {applied, marked}


def test_off_target_dry_run_deletes_nothing_and_counts(fx: _Fixture) -> None:
    off_area = fx.opportunity(3, role_family="SALES", evidence=_TITLE, full=True)
    on_target = fx.opportunity(3, role_family="DATA")

    report = _off_target_run(fx, dry_run=True)

    assert report.dry_run is True
    assert fx.present() == {off_area, on_target}
    assert report.rows["opportunity_off_target"] >= 1
    assert report.rows["opportunity"] >= 1
    assert isinstance(report.as_dict()["off_target_cutoff"], str)


def test_off_target_threshold_is_inert_without_profile_scope_or_when_not_shorter(
    fx: _Fixture,
) -> None:
    off_area = fx.opportunity(3, role_family="SALES", evidence=_TITLE)
    other_country = fx.opportunity(3, role_family="DATA", allowed_countries=["US"])

    no_scope = _off_target_run(fx, target_role_families=(), target_countries=())
    assert no_scope.off_target_cutoff is None
    not_shorter = _off_target_run(fx, off_target_retention_days=7)
    assert not_shorter.off_target_cutoff is None
    disabled = _off_target_run(fx, off_target_retention_days=0)
    assert disabled.off_target_cutoff is None

    assert fx.present() == {off_area, other_country}


def test_off_target_old_opportunity_is_still_deleted_by_the_normal_threshold(
    fx: _Fixture,
) -> None:
    old_on_target = fx.opportunity(8, role_family="DATA")

    _off_target_run(fx)

    assert old_on_target not in fx.present()


def test_off_target_area_needs_title_evidence_a_department_alone_keeps_it(fx: _Fixture) -> None:
    department_only = fx.opportunity(
        3,
        role_family="SALES",
        evidence={"rule": "department", "term": "sales", "origin": "department"},
    )
    no_evidence = fx.opportunity(3, role_family="SALES")
    title_and_department_off = fx.opportunity(
        3,
        role_family="SALES",
        evidence={
            "rule": "department_refined_by_title",
            "origin": "title",
            "department_family": "MARKETING",
        },
    )
    department_on_target = fx.opportunity(
        3,
        role_family="SALES",
        evidence={
            "rule": "department_refined_by_title",
            "origin": "title",
            "department_family": "DATA",
        },
    )
    title_only = fx.opportunity(3, role_family="SALES", evidence=_TITLE)

    _off_target_run(fx)

    assert fx.present() == {department_only, no_evidence, department_on_target}
    assert title_and_department_off not in fx.present()
    assert title_only not in fx.present()


def test_off_target_keeps_a_duplicate_survivor_when_evidence_has_no_rule(fx: _Fixture) -> None:
    # LLM-confirmed rows carry evidence without a `rule`; the predicate must be false, not NULL.
    survivor = fx.opportunity(30)
    kept_duplicate = fx.opportunity(3, role_family="SALES", evidence={"origin": "llm"})
    fx.session.get(OpportunityModel, kept_duplicate).duplicate_of = survivor  # type: ignore[union-attr]
    fx.session.commit()

    _off_target_run(fx)

    assert fx.present() == {survivor, kept_duplicate}


def test_off_target_title_rule_with_an_unmatched_department_is_kept(fx: _Fixture) -> None:
    evidence = {**_TITLE, "department_unmatched": True}
    unmatched = fx.opportunity(3, role_family="SALES", evidence=evidence)
    plain = fx.opportunity(3, role_family="SALES", evidence=_TITLE)

    _off_target_run(fx)

    assert fx.present() == {unmatched}
    assert plain not in fx.present()
