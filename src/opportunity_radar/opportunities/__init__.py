"""Opportunity normalization bounded context."""

from opportunity_radar.opportunities.domain import (
    CanonicalCandidate,
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
    normalize_company_name,
    normalize_location,
    normalize_title,
    normalize_url,
    opportunity_fingerprint,
)

__all__ = [
    "CanonicalCandidate",
    "ContractType",
    "NormalizationError",
    "NormalizationInput",
    "OpportunityStatus",
    "Seniority",
    "WorkMode",
    "build_candidate",
    "infer_contract_type",
    "infer_seniority",
    "infer_work_mode",
    "normalize_company_name",
    "normalize_location",
    "normalize_title",
    "normalize_url",
    "opportunity_fingerprint",
]
