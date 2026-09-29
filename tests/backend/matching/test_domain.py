from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from opportunity_radar.matching.domain import (
    CompanyPriority,
    CompensationSnapshot,
    EligibilityStatus,
    FactorRule,
    KnowledgeState,
    MatchingError,
    MatchingRuleSet,
    MissingPolicy,
    OpportunitySnapshot,
    OpportunityWorkAuthorization,
    ProfileSnapshot,
    ProfileWorkAuthorization,
    Verdict,
    evaluate_match,
)
from opportunity_radar.matching.service import _known_contracts, _optional_enum
from opportunity_radar.opportunities.domain import (
    CompensationPeriod,
    ContractType,
    OpportunityStatus,
    Seniority,
    WorkMode,
)

OPPORTUNITY_ID = UUID("11111111-1111-1111-1111-111111111111")
PROFILE_ID = UUID("22222222-2222-2222-2222-222222222222")
ASSESSED_AT = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


def _opportunity(**changes: object) -> OpportunitySnapshot:
    values: dict[str, object] = {
        "opportunity_id": OPPORTUNITY_ID,
        "content_version": 3,
        "status": OpportunityStatus.ACTIVE,
        "work_mode": WorkMode.REMOTE,
        "seniority": Seniority.SENIOR,
        "allowed_countries": ("BR",),
        "contract_types": (ContractType.FULL_TIME,),
        "required_skills": ("python", "fastapi"),
        "preferred_skills": ("postgresql",),
        "company_priority": CompanyPriority.HIGH,
        "compensation": CompensationSnapshot(
            minimum=Decimal("100000"),
            maximum=Decimal("150000"),
            currency="USD",
            period=CompensationPeriod.YEAR,
        ),
        "work_authorization": OpportunityWorkAuthorization.SPONSORSHIP_AVAILABLE,
        "timezone_overlap_hours": Decimal("8"),
        "required_timezone_overlap_hours": Decimal("4"),
        "published_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
        "evidence_refs": ("opportunity:1",),
    }
    values.update(changes)
    return OpportunitySnapshot(**values)  # type: ignore[arg-type]


def _profile(**changes: object) -> ProfileSnapshot:
    values: dict[str, object] = {
        "profile_version_id": PROFILE_ID,
        "skills": ("python", "fastapi", "postgresql"),
        "countries": ("BR",),
        "accepted_work_modes": (WorkMode.REMOTE,),
        "accepted_contract_types": (ContractType.FULL_TIME,),
        "accepted_seniorities": (Seniority.SENIOR,),
        "compensation": CompensationSnapshot(
            minimum=Decimal("110000"),
            maximum=Decimal("160000"),
            currency="USD",
            period=CompensationPeriod.YEAR,
        ),
        "work_authorization": ProfileWorkAuthorization.AUTHORIZED,
        "evidence_refs": ("profile:1",),
    }
    values.update(changes)
    return ProfileSnapshot(**values)  # type: ignore[arg-type]


def _rules() -> MatchingRuleSet:
    return MatchingRuleSet(
        version="matching-v1",
        factors=(
            FactorRule("GEOGRAPHY_CONTRACT_FIT", Decimal("0.20")),
            FactorRule("TECHNOLOGY_FIT", Decimal("0.25")),
            FactorRule("COMPANY_PRIORITY", Decimal("0.15")),
            FactorRule("SENIORITY_SCOPE", Decimal("0.10")),
            FactorRule("CONTRACT_COMPENSATION", Decimal("0.05")),
            FactorRule("RECENCY", Decimal("0.25")),
        ),
    )


def test_golden_case_perfect_match_is_reproducible_and_explainable() -> None:
    first = evaluate_match(_opportunity(), _profile(), _rules(), assessed_at=ASSESSED_AT)
    second = evaluate_match(_opportunity(), _profile(), _rules(), assessed_at=ASSESSED_AT)

    assert first == second
    assert first.eligibility.status is EligibilityStatus.ELIGIBLE
    assert first.score == Decimal("100.00")
    assert first.confidence == Decimal("1.00")
    assert first.verdict is Verdict.HIGH_PRIORITY
    assert {factor.factor_code for factor in first.factors} == {
        "GEOGRAPHY_CONTRACT_FIT",
        "TECHNOLOGY_FIT",
        "COMPANY_PRIORITY",
        "SENIORITY_SCOPE",
        "CONTRACT_COMPENSATION",
        "RECENCY",
    }


def test_golden_case_hard_country_disqualifier_dominates_high_score() -> None:
    result = evaluate_match(
        _opportunity(allowed_countries=("US",)),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    assert result.eligibility.status is EligibilityStatus.INELIGIBLE
    assert result.verdict is Verdict.INELIGIBLE
    country = next(
        item for item in result.eligibility.filters if item.code == "COUNTRY_ALLOWED"
    )
    assert country.result is KnowledgeState.FALSE


def test_discovered_opportunity_is_eligible_but_stale_requires_more_evidence() -> None:
    discovered = evaluate_match(
        _opportunity(status=OpportunityStatus.DISCOVERED),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )
    stale = evaluate_match(
        _opportunity(status=OpportunityStatus.STALE),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    assert discovered.eligibility.status is EligibilityStatus.ELIGIBLE
    assert stale.eligibility.status is EligibilityStatus.UNKNOWN


def test_golden_case_absence_remains_unknown_and_explicit_missing_policy_applies() -> None:
    rules = MatchingRuleSet(
        version="matching-v1-review",
        factors=(FactorRule("TIMEZONE", Decimal("1"), MissingPolicy.REQUIRE_REVIEW),),
    )
    result = evaluate_match(
        _opportunity(
            timezone_overlap_hours=None,
            required_timezone_overlap_hours=None,
        ),
        _profile(),
        rules,
        assessed_at=ASSESSED_AT,
    )

    assert result.factors[0].raw_score == Decimal("0.5")
    assert result.factors[0].status.value == "UNKNOWN"
    assert result.review_required is True
    assert result.verdict is Verdict.REVIEW_REQUIRED


def test_golden_case_missing_salary_stays_unknown_instead_of_disqualifying() -> None:
    result = evaluate_match(
        _opportunity(compensation=None),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    factor = next(
        item for item in result.factors if item.factor_code == "CONTRACT_COMPENSATION"
    )
    assert result.eligibility.status is EligibilityStatus.ELIGIBLE
    assert factor.status.value == "UNKNOWN"
    assert factor.raw_score == Decimal("0.5")


def test_conflicting_compensation_requires_review_without_choosing_a_source() -> None:
    result = evaluate_match(
        _opportunity(compensation=None, compensation_conflict=True),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    factor = next(
        item for item in result.factors if item.factor_code == "CONTRACT_COMPENSATION"
    )
    assert factor.status.value == "UNKNOWN"
    assert result.review_required is True
    assert result.verdict is Verdict.REVIEW_REQUIRED


def test_golden_case_ambiguous_seniority_stays_unknown() -> None:
    result = evaluate_match(
        _opportunity(seniority=Seniority.UNKNOWN),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    seniority = next(
        item for item in result.eligibility.filters if item.code == "SENIORITY_COMPATIBLE"
    )
    assert seniority.result is KnowledgeState.UNKNOWN
    assert result.eligibility.status is EligibilityStatus.UNKNOWN


def _seniority_result(seniority: Seniority, accepted: tuple[Seniority, ...]):
    result = evaluate_match(
        _opportunity(seniority=seniority),
        _profile(accepted_seniorities=accepted),
        _rules(),
        assessed_at=ASSESSED_AT,
    )
    return next(
        item for item in result.eligibility.filters if item.code == "SENIORITY_COMPATIBLE"
    ), result


@pytest.mark.parametrize("seniority", [Seniority.JUNIOR, Seniority.INTERN, Seniority.SENIOR])
def test_empty_accepted_seniorities_never_hides_any_level(seniority: Seniority) -> None:
    # F20-72: a profile with no seniority preference is permissive, same as UNKNOWN.
    seniority_filter, result = _seniority_result(seniority, ())

    assert seniority_filter.result is KnowledgeState.UNKNOWN
    assert result.eligibility.status is not EligibilityStatus.INELIGIBLE


def test_explicit_seniority_preference_excludes_levels_below_the_senior_tier() -> None:
    accepted = (Seniority.SENIOR,)
    for excluded in (Seniority.JUNIOR, Seniority.INTERN, Seniority.MID):
        seniority_filter, result = _seniority_result(excluded, accepted)
        assert seniority_filter.result is KnowledgeState.FALSE
        assert result.eligibility.status is EligibilityStatus.INELIGIBLE
    seniority_filter, _ = _seniority_result(
        Seniority.JUNIOR, (Seniority.JUNIOR, Seniority.INTERN)
    )
    assert seniority_filter.result is KnowledgeState.TRUE


_DEFAULT_ACCEPTED = (Seniority.INTERN, Seniority.JUNIOR, Seniority.MID, Seniority.UNKNOWN)


@pytest.mark.parametrize(
    "seniority",
    [Seniority.SENIOR, Seniority.STAFF, Seniority.LEAD, Seniority.MANAGER, Seniority.DIRECTOR],
)
def test_senior_or_above_is_below_the_preference_never_excluded(seniority: Seniority) -> None:
    # F48-13, decision 2: SENIOR+ outside the accepted levels ranks lower, never INELIGIBLE.
    seniority_filter, result = _seniority_result(seniority, _DEFAULT_ACCEPTED)

    assert seniority_filter.result is not KnowledgeState.FALSE
    assert result.eligibility.status is not EligibilityStatus.INELIGIBLE


def test_senior_scores_below_an_accepted_level_on_the_seniority_factor() -> None:
    def factor_score(seniority: Seniority) -> Decimal:
        _, result = _seniority_result(seniority, _DEFAULT_ACCEPTED)
        factor = next(item for item in result.factors if item.factor_code == "SENIORITY_SCOPE")
        assert factor.raw_score is not None
        return factor.raw_score

    assert factor_score(Seniority.SENIOR) < factor_score(Seniority.JUNIOR)
    assert factor_score(Seniority.SENIOR) > Decimal("0")


def test_golden_case_partial_skills_uses_exact_canonical_overlap() -> None:
    result = evaluate_match(
        _opportunity(required_skills=("python", "go"), preferred_skills=()),
        _profile(skills=("python",)),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    factor = next(item for item in result.factors if item.factor_code == "TECHNOLOGY_FIT")
    assert factor.raw_score == Decimal("0.5")


def test_golden_case_old_job_has_explicit_recency_decay() -> None:
    result = evaluate_match(
        _opportunity(published_at=datetime(2026, 7, 1, tzinfo=timezone.utc)),
        _profile(),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    factor = next(item for item in result.factors if item.factor_code == "RECENCY")
    assert factor.raw_score == Decimal("0.25")


def test_excluded_unknown_factor_is_renormalized_only_when_the_rule_requests_it() -> None:
    rules = MatchingRuleSet(
        version="matching-v1-exclude",
        factors=(
            FactorRule("TECHNOLOGY_FIT", Decimal("0.5")),
            FactorRule("TIMEZONE", Decimal("0.5"), MissingPolicy.EXCLUDE_AND_RENORMALIZE),
        ),
    )

    result = evaluate_match(
        _opportunity(
            timezone_overlap_hours=None,
            required_timezone_overlap_hours=None,
        ),
        _profile(),
        rules,
        assessed_at=ASSESSED_AT,
    )

    assert result.score == Decimal("100")
    assert result.factors[1].raw_score is None


def test_rule_set_requires_versioned_complete_weights_and_aware_assessment_time() -> None:
    with pytest.raises(MatchingError, match="total one"):
        MatchingRuleSet(
            version="v1",
            factors=(FactorRule("TECHNOLOGY_FIT", Decimal("0.9")),),
        )
    with pytest.raises(MatchingError, match="timezone-aware"):
        evaluate_match(_opportunity(), _profile(), _rules(), assessed_at=datetime(2026, 9, 15))


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("full-time", ContractType.FULL_TIME),
        ("FULL_TIME", ContractType.FULL_TIME),
        (" Full Time ", ContractType.FULL_TIME),
        ("part-time", ContractType.PART_TIME),
        ("internship", ContractType.INTERNSHIP),
        ("contract", ContractType.CONTRACT),
        ("freelance-ish", None),
    ],
)
def test_profile_contract_spellings_resolve_to_the_same_enum(
    stored: str, expected: ContractType | None
) -> None:
    # F48-04: the profile stores `full-time`, which used to become `FULL-TIME` and miss.
    assert _optional_enum(ContractType, stored) is expected


def test_a_hyphenated_profile_contract_makes_contract_compatible_known() -> None:
    accepted = _known_contracts(("full-time",))
    assert accepted == (ContractType.FULL_TIME,)

    result = evaluate_match(
        _opportunity(contract_types=(ContractType.FULL_TIME,)),
        _profile(accepted_contract_types=accepted),
        _rules(),
        assessed_at=ASSESSED_AT,
    )

    contract = next(
        item for item in result.eligibility.filters if item.code == "CONTRACT_COMPATIBLE"
    )
    assert contract.result is KnowledgeState.TRUE