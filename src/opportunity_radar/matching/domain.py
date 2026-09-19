"""Pure, versioned rules for deterministic opportunity matching.

This module deliberately consumes stable snapshots only. Persistence and HTTP adapters
are responsible for translating their models into these value objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from opportunity_radar.opportunities.domain import (
    CompensationPeriod,
    ContractType,
    OpportunityStatus,
    Seniority,
    WorkMode,
)

ZERO = Decimal("0")
ONE = Decimal("1")
HALF = Decimal("0.5")
HUNDRED = Decimal("100")


class MatchingError(ValueError):
    """Raised when a matching snapshot or rule set is invalid."""


class KnowledgeState(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    UNKNOWN = "UNKNOWN"


class MissingPolicy(StrEnum):
    NEUTRAL = "NEUTRAL"
    PENALIZE = "PENALIZE"
    EXCLUDE_AND_RENORMALIZE = "EXCLUDE_AND_RENORMALIZE"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"


class FactorStatus(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Verdict(StrEnum):
    HIGH_PRIORITY = "HIGH_PRIORITY"
    RECOMMENDED = "RECOMMENDED"
    WATCHLIST = "WATCHLIST"
    LOW_MATCH = "LOW_MATCH"
    INELIGIBLE = "INELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CompanyPriority(StrEnum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"
    BLOCKED = "BLOCKED"


class ProfileWorkAuthorization(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    REQUIRES_SPONSORSHIP = "REQUIRES_SPONSORSHIP"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OpportunityWorkAuthorization(StrEnum):
    REQUIRED_LOCAL_AUTHORIZATION = "REQUIRED_LOCAL_AUTHORIZATION"
    SPONSORSHIP_AVAILABLE = "SPONSORSHIP_AVAILABLE"
    SPONSORSHIP_NOT_AVAILABLE = "SPONSORSHIP_NOT_AVAILABLE"
    NOT_STATED = "NOT_STATED"


@dataclass(frozen=True, slots=True)
class CompensationSnapshot:
    """Comparable source-declared compensation; never an inferred salary."""

    minimum: Decimal | None = None
    maximum: Decimal | None = None
    currency: str | None = None
    period: CompensationPeriod | None = None

    def __post_init__(self) -> None:
        if self.minimum is not None and self.minimum < ZERO:
            raise MatchingError("compensation minimum must not be negative")
        if self.maximum is not None and self.maximum < ZERO:
            raise MatchingError("compensation maximum must not be negative")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise MatchingError("compensation minimum must not exceed maximum")
        if self.currency is not None and len(self.currency) != 3:
            raise MatchingError("compensation currency must use an ISO 4217 code")


@dataclass(frozen=True, slots=True)
class CompensationEvidenceSnapshot:
    minimum: Decimal | None
    maximum: Decimal | None
    currency: str | None
    period: str
    gross_net: str
    evidence_text: str | None
    evidence_source: str | None
    source_occurrence_id: UUID
    raw_item_id: UUID


@dataclass(frozen=True, slots=True)
class OpportunitySnapshot:
    opportunity_id: UUID
    content_version: int
    status: OpportunityStatus
    work_mode: WorkMode = WorkMode.UNKNOWN
    seniority: Seniority = Seniority.UNKNOWN
    allowed_countries: tuple[str, ...] = ()
    contract_types: tuple[ContractType, ...] = ()
    required_skills: tuple[str, ...] = ()
    preferred_skills: tuple[str, ...] = ()
    skill_evidence_refs: tuple[str, ...] = ()
    company_priority: CompanyPriority | None = None
    compensation: CompensationSnapshot | None = None
    compensation_candidates: tuple[CompensationEvidenceSnapshot, ...] = ()
    compensation_conflict: bool = False
    work_authorization: OpportunityWorkAuthorization = (
        OpportunityWorkAuthorization.NOT_STATED
    )
    timezone_overlap_hours: Decimal | None = None
    required_timezone_overlap_hours: Decimal | None = None
    published_at: datetime | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.content_version < 1:
            raise MatchingError("opportunity content version must be positive")
        _require_unique("allowed countries", self.allowed_countries)
        _require_unique("required skills", self.required_skills)
        _require_unique("preferred skills", self.preferred_skills)
        _require_unique("skill evidence refs", self.skill_evidence_refs)
        if self.timezone_overlap_hours is not None and self.timezone_overlap_hours < ZERO:
            raise MatchingError("timezone overlap must not be negative")
        if (
            self.required_timezone_overlap_hours is not None
            and self.required_timezone_overlap_hours < ZERO
        ):
            raise MatchingError("required timezone overlap must not be negative")


@dataclass(frozen=True, slots=True)
class ProfileSnapshot:
    profile_version_id: UUID
    skills: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    accepted_work_modes: tuple[WorkMode, ...] = ()
    accepted_contract_types: tuple[ContractType, ...] = ()
    accepted_seniorities: tuple[Seniority, ...] = ()
    compensation: CompensationSnapshot | None = None
    work_authorization: ProfileWorkAuthorization = ProfileWorkAuthorization.UNKNOWN
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_unique("profile skills", self.skills)
        _require_unique("profile countries", self.countries)


@dataclass(frozen=True, slots=True)
class HardFilterResult:
    code: str
    result: KnowledgeState
    reason: str
    evidence_refs: tuple[str, ...]
    severity: str = "HARD"
    confidence: Decimal = ONE


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    status: EligibilityStatus
    filters: tuple[HardFilterResult, ...]

    @property
    def disqualifiers(self) -> tuple[HardFilterResult, ...]:
        return tuple(item for item in self.filters if item.result is KnowledgeState.FALSE)

    @property
    def unknowns(self) -> tuple[HardFilterResult, ...]:
        return tuple(item for item in self.filters if item.result is KnowledgeState.UNKNOWN)


@dataclass(frozen=True, slots=True)
class FactorRule:
    code: str
    weight: Decimal
    missing_policy: MissingPolicy = MissingPolicy.NEUTRAL

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise MatchingError("factor code is required")
        if not ZERO <= self.weight <= ONE:
            raise MatchingError("factor weight must be between zero and one")


@dataclass(frozen=True, slots=True)
class MatchingRuleSet:
    version: str
    factors: tuple[FactorRule, ...]
    company_priority_scores: tuple[tuple[CompanyPriority, Decimal], ...] = (
        (CompanyPriority.HIGH, ONE),
        (CompanyPriority.NORMAL, Decimal("0.7")),
        (CompanyPriority.LOW, Decimal("0.4")),
        (CompanyPriority.BLOCKED, ZERO),
    )
    high_priority_threshold: Decimal = Decimal("80")
    recommended_threshold: Decimal = Decimal("65")
    watchlist_threshold: Decimal = Decimal("45")

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise MatchingError("matching rules require a version")
        _require_unique("factor codes", tuple(factor.code for factor in self.factors))
        if sum((factor.weight for factor in self.factors), ZERO) != ONE:
            raise MatchingError("factor weights must total one")
        if not (
            HUNDRED
            >= self.high_priority_threshold
            >= self.recommended_threshold
            >= self.watchlist_threshold
            >= ZERO
        ):
            raise MatchingError("verdict thresholds must descend within zero and one hundred")
        priorities = [priority for priority, _ in self.company_priority_scores]
        if len(priorities) != len(set(priorities)):
            raise MatchingError("company priority scores must be unique")
        for _, score in self.company_priority_scores:
            if not ZERO <= score <= ONE:
                raise MatchingError("company priority score must be between zero and one")


@dataclass(frozen=True, slots=True)
class MatchFactor:
    factor_code: str
    weight: Decimal
    raw_score: Decimal | None
    contribution: Decimal
    status: FactorStatus
    confidence: Decimal
    missing_policy: MissingPolicy
    explanation: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchResult:
    opportunity_id: UUID
    opportunity_content_version: int
    profile_version_id: UUID
    rules_version: str
    eligibility: EligibilityResult
    factors: tuple[MatchFactor, ...]
    score: Decimal
    confidence: Decimal
    verdict: Verdict
    review_required: bool


DEFAULT_FACTORS: tuple[FactorRule, ...] = (
    FactorRule(
        "GEOGRAPHY_CONTRACT_FIT",
        Decimal("0.20"),
        MissingPolicy.REQUIRE_REVIEW,
    ),
    FactorRule("TECHNOLOGY_FIT", Decimal("0.25")),
    FactorRule("COMPANY_PRIORITY", Decimal("0.15")),
    FactorRule("DOMAIN_EXPERIENCE", Decimal("0.15")),
    FactorRule("SENIORITY_SCOPE", Decimal("0.10")),
    FactorRule("CONTRACT_COMPENSATION", Decimal("0.05")),
    FactorRule("TIMEZONE", Decimal("0.05")),
    FactorRule("RECENCY", Decimal("0.05")),
)


def default_rule_set(version: str = "matching-v1") -> MatchingRuleSet:
    """Return the first explicit, fully weighted deterministic rule set."""
    return MatchingRuleSet(version=version, factors=DEFAULT_FACTORS)


def evaluate_match(
    opportunity: OpportunitySnapshot,
    profile: ProfileSnapshot,
    rules: MatchingRuleSet,
    *,
    assessed_at: datetime | None = None,
) -> MatchResult:
    """Evaluate stable inputs without source calls, inference, or wall-clock dependence."""
    eligibility = evaluate_eligibility(opportunity, profile)
    factors = tuple(
        _evaluate_factor(rule, opportunity, profile, rules, assessed_at)
        for rule in rules.factors
    )
    score = _score(factors)
    review_required = opportunity.compensation_conflict or any(
        factor.missing_policy is MissingPolicy.REQUIRE_REVIEW
        and factor.status is FactorStatus.UNKNOWN
        for factor in factors
    )
    return MatchResult(
        opportunity_id=opportunity.opportunity_id,
        opportunity_content_version=opportunity.content_version,
        profile_version_id=profile.profile_version_id,
        rules_version=rules.version,
        eligibility=eligibility,
        factors=factors,
        score=score,
        confidence=_confidence(factors),
        verdict=_verdict(score, eligibility, review_required, rules),
        review_required=review_required,
    )


def evaluate_eligibility(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> EligibilityResult:
    """Apply only conclusive hard filters supported by normalized snapshots."""
    filters = (
        _active_filter(opportunity),
        _work_mode_filter(opportunity, profile),
        _country_filter(opportunity, profile),
        _work_authorization_filter(opportunity, profile),
        _timezone_filter(opportunity),
        _seniority_filter(opportunity, profile),
        _contract_filter(opportunity, profile),
    )
    if any(item.result is KnowledgeState.FALSE for item in filters):
        status = EligibilityStatus.INELIGIBLE
    elif any(item.result is KnowledgeState.UNKNOWN for item in filters):
        status = EligibilityStatus.UNKNOWN
    else:
        status = EligibilityStatus.ELIGIBLE
    return EligibilityResult(status=status, filters=filters)


def _active_filter(opportunity: OpportunitySnapshot) -> HardFilterResult:
    is_active = opportunity.status in {
        OpportunityStatus.DISCOVERED,
        OpportunityStatus.ACTIVE,
    }
    is_stale = opportunity.status is OpportunityStatus.STALE
    result = (
        KnowledgeState.TRUE
        if is_active
        else KnowledgeState.UNKNOWN
        if is_stale
        else KnowledgeState.FALSE
    )
    return HardFilterResult(
        code="OPPORTUNITY_ACTIVE",
        result=result,
        reason=(
            "Opportunity is active or newly discovered."
            if is_active
            else "Opportunity freshness is stale."
            if is_stale
            else "Opportunity is closed, rejected, or archived."
        ),
        evidence_refs=opportunity.evidence_refs,
    )


def _work_mode_filter(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> HardFilterResult:
    if opportunity.work_mode is WorkMode.UNKNOWN or not profile.accepted_work_modes:
        return _unknown_filter(
            "WORK_MODE_COMPATIBLE", "Work-mode compatibility is not stated."
        )
    compatible = opportunity.work_mode in profile.accepted_work_modes
    return _binary_filter(
        "WORK_MODE_COMPATIBLE",
        compatible,
        "Work mode is compatible.",
        "Work mode is not accepted.",
        opportunity,
        profile,
    )


def _country_filter(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> HardFilterResult:
    if not opportunity.allowed_countries or not profile.countries:
        return _unknown_filter(
            "COUNTRY_ALLOWED", "Residence eligibility is not stated."
        )
    allowed = _normalized_set(opportunity.allowed_countries)
    compatible = bool(allowed & _normalized_set(profile.countries))
    return _binary_filter(
        "COUNTRY_ALLOWED",
        compatible,
        "Profile country is allowed.",
        "Profile country is not allowed.",
        opportunity,
        profile,
    )


def _seniority_filter(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> HardFilterResult:
    if opportunity.seniority is Seniority.UNKNOWN or not profile.accepted_seniorities:
        return _unknown_filter(
            "SENIORITY_COMPATIBLE", "Seniority compatibility is not stated."
        )
    compatible = opportunity.seniority in profile.accepted_seniorities
    return _binary_filter(
        "SENIORITY_COMPATIBLE",
        compatible,
        "Seniority is compatible.",
        "Seniority is outside profile preference.",
        opportunity,
        profile,
    )


def _work_authorization_filter(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> HardFilterResult:
    requirement = opportunity.work_authorization
    authorization = profile.work_authorization
    if (
        requirement is OpportunityWorkAuthorization.NOT_STATED
        or authorization is ProfileWorkAuthorization.UNKNOWN
    ):
        return _unknown_filter(
            "WORK_AUTHORIZATION_COMPATIBLE",
            "Work-authorization requirements are not stated conclusively.",
        )
    incompatible = (
        authorization is ProfileWorkAuthorization.REQUIRES_SPONSORSHIP
        and requirement
        in {
            OpportunityWorkAuthorization.REQUIRED_LOCAL_AUTHORIZATION,
            OpportunityWorkAuthorization.SPONSORSHIP_NOT_AVAILABLE,
        }
    )
    return _binary_filter(
        "WORK_AUTHORIZATION_COMPATIBLE",
        not incompatible,
        "Work-authorization requirements are compatible.",
        "The opportunity requires authorization the profile does not have.",
        opportunity,
        profile,
    )


def _timezone_filter(opportunity: OpportunitySnapshot) -> HardFilterResult:
    overlap = opportunity.timezone_overlap_hours
    required = opportunity.required_timezone_overlap_hours
    if overlap is None or required is None:
        return _unknown_filter(
            "TIMEZONE_COMPATIBLE", "Required timezone overlap is not stated."
        )
    compatible = overlap >= required
    return HardFilterResult(
        code="TIMEZONE_COMPATIBLE",
        result=KnowledgeState.TRUE if compatible else KnowledgeState.FALSE,
        reason=(
            "Timezone overlap meets the requirement."
            if compatible
            else "Timezone overlap is below the required minimum."
        ),
        evidence_refs=opportunity.evidence_refs,
    )


def _contract_filter(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> HardFilterResult:
    if not opportunity.contract_types or not profile.accepted_contract_types:
        return _unknown_filter(
            "CONTRACT_COMPATIBLE", "Contract compatibility is not stated."
        )
    compatible = bool(set(opportunity.contract_types) & set(profile.accepted_contract_types))
    return _binary_filter(
        "CONTRACT_COMPATIBLE",
        compatible,
        "Contract is compatible.",
        "Contract is not accepted.",
        opportunity,
        profile,
    )


def _unknown_filter(code: str, reason: str) -> HardFilterResult:
    return HardFilterResult(
        code=code,
        result=KnowledgeState.UNKNOWN,
        reason=reason,
        evidence_refs=(),
        confidence=ZERO,
    )


def _binary_filter(
    code: str,
    compatible: bool,
    true_reason: str,
    false_reason: str,
    opportunity: OpportunitySnapshot,
    profile: ProfileSnapshot,
) -> HardFilterResult:
    return HardFilterResult(
        code=code,
        result=KnowledgeState.TRUE if compatible else KnowledgeState.FALSE,
        reason=true_reason if compatible else false_reason,
        evidence_refs=opportunity.evidence_refs + profile.evidence_refs,
    )


def _evaluate_factor(
    rule: FactorRule,
    opportunity: OpportunitySnapshot,
    profile: ProfileSnapshot,
    rules: MatchingRuleSet,
    assessed_at: datetime | None,
) -> MatchFactor:
    state, raw_score, explanation, evidence_refs = _factor_measurement(
        rule.code, opportunity, profile, rules, assessed_at
    )
    if state is KnowledgeState.TRUE or state is KnowledgeState.FALSE:
        raw = raw_score
        status = FactorStatus.KNOWN
    elif state is KnowledgeState.NOT_APPLICABLE:
        raw = None
        status = FactorStatus.NOT_APPLICABLE
    else:
        raw = _missing_score(rule.missing_policy)
        status = FactorStatus.UNKNOWN
    contribution = ZERO if raw is None else HUNDRED * rule.weight * raw
    return MatchFactor(
        factor_code=rule.code,
        weight=rule.weight,
        raw_score=raw,
        contribution=contribution,
        status=status,
        confidence=ONE if status is FactorStatus.KNOWN else ZERO,
        missing_policy=rule.missing_policy,
        explanation=explanation,
        evidence_refs=evidence_refs,
    )


def _factor_measurement(
    code: str,
    opportunity: OpportunitySnapshot,
    profile: ProfileSnapshot,
    rules: MatchingRuleSet,
    assessed_at: datetime | None,
) -> tuple[KnowledgeState, Decimal | None, str, tuple[str, ...]]:
    if code == "GEOGRAPHY_CONTRACT_FIT":
        filters = evaluate_eligibility(opportunity, profile).filters
        states = (filters[1], filters[2], filters[3], filters[4], filters[6])
        evidence_refs = opportunity.evidence_refs + profile.evidence_refs
        if any(item.result is KnowledgeState.FALSE for item in states):
            return (
                KnowledgeState.FALSE,
                ZERO,
                "A hard compatibility constraint failed.",
                evidence_refs,
            )
        if any(item.result is KnowledgeState.UNKNOWN for item in states):
            return (
                KnowledgeState.UNKNOWN,
                None,
                "Geography or contract data is incomplete.",
                evidence_refs,
            )
        return (
            KnowledgeState.TRUE,
            ONE,
            "Geography and contract are compatible.",
            evidence_refs,
        )
    if code == "TECHNOLOGY_FIT":
        return _technology_measurement(opportunity, profile)
    if code == "COMPANY_PRIORITY":
        if opportunity.company_priority is None:
            return KnowledgeState.UNKNOWN, None, "Company priority is not configured.", ()
        score = dict(rules.company_priority_scores).get(opportunity.company_priority)
        if score is None:
            return KnowledgeState.UNKNOWN, None, "Company priority has no configured score.", ()
        return (
            KnowledgeState.TRUE,
            score,
            "Company priority is configured.",
            opportunity.evidence_refs,
        )
    if code == "SENIORITY_SCOPE":
        result = _seniority_filter(opportunity, profile)
        return _filter_measurement(result)
    if code == "CONTRACT_COMPENSATION":
        return _contract_compensation_measurement(opportunity, profile)
    if code == "RECENCY":
        return _recency_measurement(opportunity, assessed_at)
    if code == "TIMEZONE":
        return _filter_measurement(_timezone_filter(opportunity))
    if code == "DOMAIN_EXPERIENCE":
        return (
            KnowledgeState.UNKNOWN,
            None,
            "No normalized evidence is available for this factor.",
            (),
        )
    return (
        KnowledgeState.UNKNOWN,
        None,
        "This rule has no deterministic evaluator.",
        (),
    )


def _technology_measurement(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> tuple[KnowledgeState, Decimal | None, str, tuple[str, ...]]:
    required = _normalized_set(opportunity.required_skills)
    preferred = _normalized_set(opportunity.preferred_skills)
    if not required and not preferred:
        return KnowledgeState.UNKNOWN, None, "Opportunity skills are not classified.", ()
    profile_skills = _normalized_set(profile.skills)
    required_score = _overlap_score(required, profile_skills)
    preferred_score = _overlap_score(preferred, profile_skills)
    if required and preferred:
        raw = Decimal("0.8") * required_score + Decimal("0.2") * preferred_score
    elif required:
        raw = required_score
    else:
        raw = preferred_score
    return (
        KnowledgeState.TRUE,
        raw,
        "Technology fit uses exact canonical skill overlap.",
        opportunity.skill_evidence_refs + profile.evidence_refs,
    )


def _contract_compensation_measurement(
    opportunity: OpportunitySnapshot, profile: ProfileSnapshot
) -> tuple[KnowledgeState, Decimal | None, str, tuple[str, ...]]:
    contract = _contract_filter(opportunity, profile)
    if contract.result is KnowledgeState.FALSE:
        return _filter_measurement(contract)
    if contract.result is KnowledgeState.UNKNOWN:
        return _filter_measurement(contract)
    if opportunity.compensation_conflict:
        return (
            KnowledgeState.UNKNOWN,
            None,
            "Source compensation evidence conflicts and requires review.",
            tuple(
                f"source-occurrence:{item.source_occurrence_id}:compensation"
                for item in opportunity.compensation_candidates
            ),
        )
    if opportunity.compensation is None or profile.compensation is None:
        return (
            KnowledgeState.UNKNOWN,
            None,
            "Contract is compatible, but compensation cannot be compared.",
            contract.evidence_refs,
        )
    opportunity_compensation = opportunity.compensation
    profile_compensation = profile.compensation
    if (
        opportunity_compensation.currency is None
        or profile_compensation.currency is None
        or opportunity_compensation.period is None
        or profile_compensation.period is None
        or opportunity_compensation.currency != profile_compensation.currency
        or opportunity_compensation.period != profile_compensation.period
        or opportunity_compensation.maximum is None
        or profile_compensation.minimum is None
    ):
        return (
            KnowledgeState.UNKNOWN,
            None,
            "Compensation units or ranges cannot be compared.",
            contract.evidence_refs,
        )
    compatible = opportunity_compensation.maximum >= profile_compensation.minimum
    if (
        compatible
        and opportunity_compensation.minimum is not None
        and profile_compensation.maximum is not None
    ):
        compatible = opportunity_compensation.minimum <= profile_compensation.maximum
    return (
        KnowledgeState.TRUE if compatible else KnowledgeState.FALSE,
        ONE if compatible else ZERO,
        "Contract and compensation are compatible."
        if compatible
        else "Compensation range is outside profile preference.",
        contract.evidence_refs,
    )


def _recency_measurement(
    opportunity: OpportunitySnapshot, assessed_at: datetime | None
) -> tuple[KnowledgeState, Decimal | None, str, tuple[str, ...]]:
    if opportunity.published_at is None or assessed_at is None:
        return (
            KnowledgeState.UNKNOWN,
            None,
            "Publication date or assessment timestamp is unavailable.",
            (),
        )
    published = _as_utc(opportunity.published_at)
    assessed = _as_utc(assessed_at)
    age_days = (assessed.date() - published.date()).days
    if age_days < 0:
        return (
            KnowledgeState.UNKNOWN,
            None,
            "Publication date is after assessment timestamp.",
            (),
        )
    if age_days <= 3:
        score = ONE
    elif age_days <= 7:
        score = Decimal("0.9")
    elif age_days <= 14:
        score = Decimal("0.75")
    elif age_days <= 30:
        score = Decimal("0.5")
    else:
        score = Decimal("0.25")
    return (
        KnowledgeState.TRUE,
        score,
        f"Opportunity was published {age_days} day(s) ago.",
        opportunity.evidence_refs,
    )


def _filter_measurement(
    result: HardFilterResult,
) -> tuple[KnowledgeState, Decimal | None, str, tuple[str, ...]]:
    if result.result is KnowledgeState.TRUE:
        raw_score = ONE
    elif result.result is KnowledgeState.FALSE:
        raw_score = ZERO
    else:
        raw_score = None
    return result.result, raw_score, result.reason, result.evidence_refs


def _missing_score(policy: MissingPolicy) -> Decimal | None:
    if policy is MissingPolicy.NEUTRAL or policy is MissingPolicy.REQUIRE_REVIEW:
        return HALF
    if policy is MissingPolicy.PENALIZE:
        return ZERO
    return None


def _score(factors: tuple[MatchFactor, ...]) -> Decimal:
    total = sum((factor.contribution for factor in factors), ZERO)
    excluded_weight = sum(
        (
            factor.weight
            for factor in factors
            if factor.raw_score is None
            and factor.missing_policy is MissingPolicy.EXCLUDE_AND_RENORMALIZE
        ),
        ZERO,
    )
    if excluded_weight == ZERO:
        return total
    active_weight = ONE - excluded_weight
    if active_weight == ZERO:
        return ZERO
    return total / active_weight


def _confidence(factors: tuple[MatchFactor, ...]) -> Decimal:
    """Coverage of weighted factors; unknown evidence never gains confidence."""
    return sum((factor.weight * factor.confidence for factor in factors), ZERO)


def _verdict(
    score: Decimal,
    eligibility: EligibilityResult,
    review_required: bool,
    rules: MatchingRuleSet,
) -> Verdict:
    if eligibility.status is EligibilityStatus.INELIGIBLE:
        return Verdict.INELIGIBLE
    if review_required:
        return Verdict.REVIEW_REQUIRED
    if score >= rules.high_priority_threshold:
        return Verdict.HIGH_PRIORITY
    if score >= rules.recommended_threshold:
        return Verdict.RECOMMENDED
    if score >= rules.watchlist_threshold:
        return Verdict.WATCHLIST
    return Verdict.LOW_MATCH


def _normalized_set(values: tuple[str, ...]) -> frozenset[str]:
    return frozenset(value.strip().casefold() for value in values if value.strip())


def _overlap_score(required: frozenset[str], actual: frozenset[str]) -> Decimal:
    if not required:
        return ONE
    return Decimal(len(required & actual)) / Decimal(len(required))


def _require_unique(label: str, values: tuple[str, ...]) -> None:
    normalized = _normalized_set(values)
    if len(normalized) != len(values) or not normalized:
        if values:
            raise MatchingError(f"{label} must be non-empty and unique")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise MatchingError("matching timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
