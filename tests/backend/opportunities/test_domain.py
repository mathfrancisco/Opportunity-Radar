from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from opportunity_radar.opportunities.domain import (
    ContractType,
    NormalizationError,
    NormalizationInput,
    OpportunityStatus,
    Seniority,
    WorkMode,
    build_candidate,
    infer_contract_type,
    infer_seniority,
    infer_work_mode,
    normalize_title,
    normalize_url,
)


def _input(**changes: object) -> NormalizationInput:
    values: dict[str, object] = {
        "raw_item_id": uuid4(),
        "source_definition_id": uuid4(),
        "external_id": "external-1",
        "title": "Senior C++ Engineer",
        "company_name": "Acme",
        "location_text": "Remote",
        "published_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
    }
    values.update(changes)
    return NormalizationInput(**values)  # type: ignore[arg-type]


def test_normalizes_title_and_url_deterministically() -> None:
    assert normalize_title("  Dév. C++ / C# Engineer! ") == "dév c++ c# engineer"
    assert (
        normalize_url("HTTPS://Example.COM/jobs/?utm_source=feed&z=2&a=1#details")
        == "https://example.com/jobs?a=1&z=2"
    )
    assert normalize_url("ftp://example.com/job") is None


def test_infers_only_explicit_unambiguous_taxonomy_evidence() -> None:
    assert infer_work_mode("Engineer", "Remote", {}) is WorkMode.REMOTE
    assert infer_work_mode("Engineer", None, {"isRemote": True}) is WorkMode.REMOTE
    assert infer_work_mode("Engineer", None, {"company_logo": "remote-logo"}) is WorkMode.UNKNOWN
    assert infer_work_mode("Remote Hybrid Engineer", None, {}) is WorkMode.UNKNOWN
    assert infer_seniority("Staff Engineer", None, {}) is Seniority.STAFF
    assert infer_seniority("Engineer", None, {}) is Seniority.UNKNOWN
    assert (
        infer_contract_type("Engineer", None, {"employment_type": "full-time"})
        is ContractType.FULL_TIME
    )
    assert infer_contract_type("Engineer", None, {}) is ContractType.UNKNOWN


def test_fingerprint_matches_exact_evidence_and_separates_company_and_day() -> None:
    company_id = UUID("11111111-1111-1111-1111-111111111111")
    first = build_candidate(_input(company_id=company_id))
    same = build_candidate(_input(company_id=company_id))
    other_company = build_candidate(_input(company_id=uuid4()))
    other_day = build_candidate(
        _input(
            company_id=company_id,
            published_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        )
    )

    assert first.fingerprint == same.fingerprint
    assert first.fingerprint != other_company.fingerprint
    assert first.fingerprint != other_day.fingerprint


def test_fingerprint_does_not_merge_unknown_companies_across_sources() -> None:
    first = build_candidate(_input(company_name=None))
    other_source = build_candidate(
        _input(company_name=None, source_definition_id=uuid4())
    )

    assert first.fingerprint != other_source.fingerprint


def test_input_requires_title_and_stable_external_identity() -> None:
    with pytest.raises(NormalizationError):
        _input(title="  ")
    with pytest.raises(NormalizationError):
        _input(external_id=None, url=None)


def test_status_transitions_are_explicit_and_archived_is_terminal() -> None:
    assert OpportunityStatus.DISCOVERED.can_transition_to(OpportunityStatus.ACTIVE)
    assert OpportunityStatus.STALE.can_transition_to(OpportunityStatus.ACTIVE)
    assert OpportunityStatus.CLOSED.can_transition_to(OpportunityStatus.ARCHIVED)
    assert not OpportunityStatus.ACTIVE.can_transition_to(OpportunityStatus.REJECTED)
    assert not OpportunityStatus.ARCHIVED.can_transition_to(OpportunityStatus.ACTIVE)
    with pytest.raises(NormalizationError):
        OpportunityStatus.ARCHIVED.require_transition_to(OpportunityStatus.ACTIVE)
