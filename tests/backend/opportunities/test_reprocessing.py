"""Reprocessing semantics for F17-06: rule vs. evidence, and the payload-expired path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from opportunity_radar.acquisition.models import RawItemModel
from opportunity_radar.opportunities.domain import NormalizationInput, build_candidate
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.repository import RawItemEvidence
from opportunity_radar.opportunities.service import (
    NORMALIZER_VERSION,
    OpportunityService,
    PayloadExpiredError,
    _apply_evidence_fields,
    _apply_rule_fields,
    _normalization_input,
    _refresh_opportunity,
)

NOW = datetime.now(UTC)


class _CandidateSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        return None

    def refresh(self, value: object) -> None:
        del value


class _CandidateRepository:
    def __init__(self, evidence: RawItemEvidence) -> None:
        self.evidence = evidence

    def normalization_result(self, *args: object) -> None:
        del args
        return None

    def raw_item_evidence(self, raw_item_id: object) -> RawItemEvidence:
        del raw_item_id
        return self.evidence


def test_direct_normalization_blocks_source_proposal_candidate() -> None:
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=uuid4(),
        source_definition_id=uuid4(),
        payload_hash="hash",
        item_metadata={"source_proposal_candidate": True},
    )
    evidence = RawItemEvidence(
        raw_item=raw_item,
        source_type="tavily_search",
        company_id=None,
        company_name=None,
        source_configuration={},
    )
    session = _CandidateSession()
    result = OpportunityService(
        session, repository=_CandidateRepository(evidence)  # type: ignore[arg-type]
    ).normalize(raw_item.id)

    assert result.status == "FAILED"
    assert result.normalizer_version == NORMALIZER_VERSION
    assert result.opportunity is None
    assert result.reasons == [{"code": "SOURCE_PROPOSAL_CANDIDATE"}]


def _opportunity(**overrides: object) -> OpportunityModel:
    base: dict[str, object] = dict(
        id=uuid4(),
        fingerprint="a" * 64,
        fingerprint_version="v1",
        canonical_title="Backend Engineer",
        normalized_title="backend engineer",
        work_mode="UNKNOWN",
        seniority="UNKNOWN",
        contract_type="UNKNOWN",
        lifecycle_status="DISCOVERED",
        role_family="UNKNOWN",
        version=1,
    )
    base.update(overrides)
    return OpportunityModel(**base)  # type: ignore[arg-type]


def _candidate(*, location_text: str, updated_at: datetime | None):
    return build_candidate(
        NormalizationInput(
            raw_item_id=uuid4(),
            source_definition_id=uuid4(),
            source_type="lever",
            external_id="job-1",
            title="Backend Engineer",
            location_text=location_text,
            updated_at=updated_at,
        )
    )


def test_rule_fields_reprocess_even_without_source_updated_at() -> None:
    """Criterion: 'Regra nova altera corretamente item sem source_updated_at.'"""
    opportunity = _opportunity(seniority="UNKNOWN", allowed_countries=None)
    candidate = _candidate(location_text="Remote — Brazil", updated_at=None)

    changed = _apply_rule_fields(opportunity, candidate)

    assert changed is True
    assert opportunity.allowed_countries == ["BR"]
    assert opportunity.allowed_countries_version == "regions-v1"


def test_evidence_fields_apply_when_candidate_has_no_freshness_signal() -> None:
    """No `source_updated_at` means "the same raw item, new rules" — content applies."""
    opportunity = _opportunity(location_text=None, source_updated_at=None)
    candidate = _candidate(location_text="Remote — Brazil", updated_at=None)

    changed = _apply_evidence_fields(opportunity, candidate)

    assert changed is True
    assert opportunity.location_text == "Remote — Brazil"


def test_out_of_order_replay_does_not_regress_evidence_fields() -> None:
    """Criterion: 'Replay fora de ordem não regride conteúdo/última observação.'"""
    fresher_at = NOW
    opportunity = _opportunity(
        location_text="Remote — Mexico",
        source_updated_at=fresher_at,
    )
    stale_candidate = _candidate(
        location_text="Remote — Brazil", updated_at=fresher_at - timedelta(days=5)
    )

    changed = _apply_evidence_fields(opportunity, stale_candidate)

    assert changed is False
    assert opportunity.location_text == "Remote — Mexico"
    assert opportunity.source_updated_at == fresher_at


def test_identical_replay_does_not_bump_version() -> None:
    """Criterion: 'repetição sem mudança não invalida avaliações' (no version bump)."""
    candidate = _candidate(location_text="Remote — Brazil", updated_at=NOW)
    opportunity = _opportunity(
        canonical_title=candidate.original_title,
        normalized_title=candidate.normalized_title,
        location_text=candidate.location_text,
        normalized_location=candidate.normalized_location,
        description=candidate.description,
        published_at=candidate.published_at,
        source_updated_at=candidate.source_updated_at,
        fingerprint=candidate.fingerprint,
        fingerprint_version=candidate.fingerprint_version,
        work_mode=candidate.work_mode.value,
        seniority=candidate.seniority.value,
        contract_type=candidate.contract_type.value,
        allowed_countries=list(candidate.allowed_countries),
        allowed_countries_version=candidate.allowed_countries_version,
        role_family=candidate.role_family.value,
        role_family_evidence=dict(candidate.role_family_evidence) or None,
        role_family_version=candidate.role_family_version,
        version=1,
    )

    _refresh_opportunity(opportunity, candidate)

    assert opportunity.version == 1


def test_a_real_change_bumps_version() -> None:
    opportunity = _opportunity(location_text=None, source_updated_at=None, version=1)
    candidate = _candidate(location_text="Remote — Brazil", updated_at=None)

    _refresh_opportunity(opportunity, candidate)

    assert opportunity.version == 2


def test_legacy_item_with_an_expired_payload_raises_payload_expired() -> None:
    """Criterion: 'Payload expirado é explicitado e não impede o restante do
    reprocessamento' — a distinct, catchable error, not a generic normalization failure.
    """
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=uuid4(),
        source_definition_id=uuid4(),
        external_id="job-1",
        canonical_url=None,
        identity_key="job-1",
        payload_hash="hash",
        item_metadata={},  # no collected_item_v1 snapshot: pre-contract, legacy path
    )
    evidence = RawItemEvidence(
        raw_item=raw_item,
        source_type="lever",
        company_id=None,
        company_name="Example Corp",
        source_configuration={},
    )

    with pytest.raises(PayloadExpiredError):
        _normalization_input(evidence)
