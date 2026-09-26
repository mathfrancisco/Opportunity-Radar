from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from opportunity_radar.opportunities.domain import (
    CanonicalCandidate,
    NormalizationInput,
    build_candidate,
)
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.opportunities.service import (
    OpportunityService,
    _reconcile_enrichment,
)


def _opportunity() -> OpportunityModel:
    return OpportunityModel(
        id=uuid4(),
        fingerprint="a" * 64,
        fingerprint_version="v1",
        canonical_title="Backend Engineer",
        normalized_title="backend engineer",
        work_mode="UNKNOWN",
        seniority="UNKNOWN",
        contract_type="UNKNOWN",
        lifecycle_status="DISCOVERED",
        version=1,
    )


def _occurrence(opportunity: OpportunityModel) -> SourceOccurrenceModel:
    now = datetime.now(timezone.utc)
    return SourceOccurrenceModel(
        id=uuid4(),
        opportunity_id=opportunity.id,
        raw_item_id=uuid4(),
        source_definition_id=uuid4(),
        external_id="job-1",
        first_seen_at=now,
        last_seen_at=now,
    )


def _candidate(
    occurrence: SourceOccurrenceModel,
    *,
    minimum: int,
    maximum: int,
    skills: list[str],
) -> CanonicalCandidate:
    return build_candidate(
        NormalizationInput(
            raw_item_id=uuid4(),
            source_definition_id=occurrence.source_definition_id,
            source_type="lever",
            external_id=occurrence.external_id,
            title="Backend Engineer",
            metadata={
                "salaryRange": {
                    "min": minimum,
                    "max": maximum,
                    "currency": "USD",
                },
                "skills": skills,
            },
        )
    )


def test_same_occurrence_replaces_current_compensation_and_skill_evidence() -> None:
    opportunity = _opportunity()
    occurrence = _occurrence(opportunity)
    first_raw_item_id = uuid4()
    first = _candidate(
        occurrence, minimum=100000, maximum=150000, skills=["Python"]
    )

    assert _reconcile_enrichment(
        opportunity=opportunity,
        occurrence=occurrence,
        candidate=first,
        raw_item_id=first_raw_item_id,
    ) == []
    assert {skill.canonical_name for skill in opportunity.skills} == {"python"}

    second_raw_item_id = uuid4()
    second = _candidate(
        occurrence, minimum=120000, maximum=170000, skills=["ReactJS"]
    )
    assert _reconcile_enrichment(
        opportunity=opportunity,
        occurrence=occurrence,
        candidate=second,
        raw_item_id=second_raw_item_id,
    ) == []

    assert len(opportunity.compensations) == 1
    compensation = opportunity.compensations[0]
    assert compensation.amount_min == Decimal("120000")
    assert compensation.amount_max == Decimal("170000")
    assert compensation.raw_item_id == second_raw_item_id
    assert {skill.canonical_name for skill in opportunity.skills} == {"react"}
    assert opportunity.skills[0].evidence[0]["raw_item_id"] == str(
        second_raw_item_id
    )


def test_distinct_occurrences_keep_compensation_evidence_and_report_conflict() -> None:
    opportunity = _opportunity()
    first_occurrence = _occurrence(opportunity)
    second_occurrence = _occurrence(opportunity)

    _reconcile_enrichment(
        opportunity=opportunity,
        occurrence=first_occurrence,
        candidate=_candidate(
            first_occurrence,
            minimum=100000,
            maximum=150000,
            skills=[],
        ),
        raw_item_id=uuid4(),
    )
    reasons = _reconcile_enrichment(
        opportunity=opportunity,
        occurrence=second_occurrence,
        candidate=_candidate(
            second_occurrence,
            minimum=130000,
            maximum=180000,
            skills=[],
        ),
        raw_item_id=uuid4(),
    )

    assert len(opportunity.compensations) == 2
    assert [reason["code"] for reason in reasons] == [
        "CONFLICTING_COMPENSATION_EVIDENCE"
    ]


class _NormalizationSession:
    def add(self, _value) -> None:
        pass

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def refresh(self, _value) -> None:
        pass


class _MergedOpportunityRepository:
    def __init__(self, opportunity: OpportunityModel, raw_item) -> None:
        self.opportunity = opportunity
        self.raw_item = raw_item

    def normalization_result(self, _raw_item_id, _normalizer_version):
        return None

    def raw_item_evidence(self, _raw_item_id):
        return SimpleNamespace(raw_item=self.raw_item)

    def lock_candidate_identities(self, _identity_locks) -> None:
        pass

    def occurrence_by_external_identity(self, **_kwargs):
        return None

    def opportunity_by_normalized_url(self, _normalized_url):
        return None

    def opportunity_by_fingerprint(self, **_kwargs):
        return self.opportunity


def _normalize_merged(
    monkeypatch, opportunity: OpportunityModel, candidate: CanonicalCandidate
) -> None:
    from opportunity_radar.opportunities import service as service_module

    raw_item = SimpleNamespace(
        id=uuid4(),
        source_definition_id=uuid4(),
        item_metadata={},
        fetched_at=datetime.now(timezone.utc),
        source_run_id=uuid4(),
    )
    normalization_input = SimpleNamespace(
        external_id="job-merged",
        title="Backend Engineer",
        metadata={},
        source_type="lever",
    )
    monkeypatch.setattr(
        service_module, "_normalization_input", lambda _evidence: normalization_input
    )
    monkeypatch.setattr(service_module, "build_candidate", lambda _input: candidate)
    monkeypatch.setattr(
        service_module,
        "seniority_classification",
        lambda *_args, **_kwargs: (None, {"code": "TEST"}),
    )
    repository = _MergedOpportunityRepository(opportunity, raw_item)
    OpportunityService(_NormalizationSession(), repository).normalize(raw_item.id)


def test_merged_normalization_bumps_version_when_skill_changes(monkeypatch) -> None:
    opportunity = _opportunity()
    opportunity.skills = []
    opportunity.compensations = []
    opportunity.search_skills = None
    occurrence = _occurrence(opportunity)
    candidate = _candidate(occurrence, minimum=0, maximum=0, skills=["Python"])

    _normalize_merged(monkeypatch, opportunity, candidate)

    assert opportunity.version == 2
    assert opportunity.search_skills == "python"


def test_merged_identical_enrichment_does_not_bump_version(monkeypatch) -> None:
    opportunity = _opportunity()
    opportunity.skills = []
    opportunity.compensations = []
    opportunity.search_skills = None
    occurrence = _occurrence(opportunity)
    candidate = replace(
        _candidate(occurrence, minimum=0, maximum=0, skills=[]),
        compensation=None,
        skills=[],
    )

    _normalize_merged(monkeypatch, opportunity, candidate)
    _normalize_merged(monkeypatch, opportunity, candidate)

    assert opportunity.version == 1
