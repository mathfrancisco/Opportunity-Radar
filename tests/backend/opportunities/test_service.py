from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from opportunity_radar.opportunities.domain import (
    CanonicalCandidate,
    NormalizationInput,
    build_candidate,
)
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.opportunities.service import _reconcile_enrichment


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
