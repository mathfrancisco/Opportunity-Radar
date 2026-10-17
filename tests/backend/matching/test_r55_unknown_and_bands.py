"""R55-D2 (unknown is not neutral) and R55-D3 (seniority bands) over `matching-v6`."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from itertools import product
from uuid import UUID

import pytest

from opportunity_radar.matching.domain import (
    SENIORITY_ABOVE_PREFERENCE_SCORE,
    SENIORITY_ADJACENT_SCORE,
    UNKNOWN_FACTOR_SCORE,
    EligibilityStatus,
    FactorRule,
    KnowledgeState,
    MatchingError,
    MatchingRuleSet,
    MissingPolicy,
    OpportunitySnapshot,
    ProfileSnapshot,
    Verdict,
    default_rule_set,
    evaluate_eligibility,
    evaluate_match,
)
from opportunity_radar.opportunities.domain import (
    ContractType,
    OpportunityStatus,
    Seniority,
    WorkMode,
    infer_seniority,
)

ASSESSED_AT = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
J, M, S = Seniority.JUNIOR, Seniority.MID, Seniority.SENIOR


def _opportunity(**changes: object) -> OpportunitySnapshot:
    values: dict[str, object] = {
        "opportunity_id": UUID("11111111-1111-1111-1111-111111111111"),
        "content_version": 1,
        "status": OpportunityStatus.ACTIVE,
        "work_mode": WorkMode.REMOTE,
        "seniority": M,
        "allowed_countries": ("BR",),
        "contract_types": (ContractType.FULL_TIME,),
        "required_skills": ("python",),
        "role_family": "SOFTWARE_ENGINEERING",
    }
    values.update(changes)
    return OpportunitySnapshot(**values)  # type: ignore[arg-type]


def _profile(**changes: object) -> ProfileSnapshot:
    values: dict[str, object] = {
        "profile_version_id": UUID("22222222-2222-2222-2222-222222222222"),
        "skills": ("python",),
        "countries": ("BR",),
        "accepted_work_modes": (WorkMode.REMOTE,),
        "accepted_contract_types": (ContractType.FULL_TIME,),
        "accepted_seniorities": (J, M),
        "role_families": ("SOFTWARE_ENGINEERING",),
    }
    values.update(changes)
    return ProfileSnapshot(**values)  # type: ignore[arg-type]


def _factor(result, code: str):  # type: ignore[no-untyped-def]
    return next(item for item in result.factors if item.factor_code == code)


# --- R55-D2 ------------------------------------------------------------------------------


def test_unknown_scores_below_the_neutral_midpoint() -> None:
    assert Decimal("0") < UNKNOWN_FACTOR_SCORE < Decimal("0.5")


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        (Decimal("0"), True),
        (UNKNOWN_FACTOR_SCORE, True),
        (Decimal("0.5"), True),
        (Decimal("0.5001"), False),
        (Decimal("1"), False),
        (Decimal("-0.0001"), False),
    ],
)
def test_unknown_score_boundaries(value: Decimal, valid: bool) -> None:
    factors = (FactorRule("TECHNOLOGY_FIT", Decimal("1")),)
    if valid:
        assert MatchingRuleSet("t", factors, unknown_score=value).unknown_score == value
    else:
        with pytest.raises(MatchingError):
            MatchingRuleSet("t", factors, unknown_score=value)


def test_a_known_middling_fit_outranks_an_unknown_one() -> None:
    """Half of the required skills known is 0.5; no skills at all is unknown (0.45)."""
    profile = _profile()
    known_middling = evaluate_match(
        _opportunity(required_skills=("python", "go")),
        profile,
        default_rule_set(),
        assessed_at=ASSESSED_AT,
    )
    unknown = evaluate_match(
        _opportunity(required_skills=()), profile, default_rule_set(), assessed_at=ASSESSED_AT
    )

    assert _factor(known_middling, "TECHNOLOGY_FIT").raw_score == Decimal("0.5")
    assert _factor(unknown, "TECHNOLOGY_FIT").raw_score == UNKNOWN_FACTOR_SCORE
    assert known_middling.score > unknown.score


def test_the_unknown_score_still_comes_from_the_rule_set() -> None:
    legacy = MatchingRuleSet(
        "matching-v5", default_rule_set().factors, unknown_score=Decimal("0.5")
    )
    opportunity = _opportunity(required_skills=())

    old = evaluate_match(opportunity, _profile(), legacy, assessed_at=ASSESSED_AT)
    new = evaluate_match(opportunity, _profile(), default_rule_set(), assessed_at=ASSESSED_AT)

    assert _factor(old, "TECHNOLOGY_FIT").raw_score == Decimal("0.5")
    assert old.score > new.score


def test_excluded_factors_do_not_take_the_unknown_score() -> None:
    result = evaluate_match(
        _opportunity(), _profile(), default_rule_set(), assessed_at=ASSESSED_AT
    )

    for code in ("TIMEZONE", "CONTRACT_COMPENSATION"):
        factor = _factor(result, code)
        assert factor.missing_policy is MissingPolicy.EXCLUDE_AND_RENORMALIZE
        assert factor.raw_score is None


def _grid() -> list[tuple[OpportunitySnapshot, ProfileSnapshot]]:
    """Synthetic postings that differ only in which evidence they carry (36 combinations)."""
    cases = []
    for skills, family, level, recent in product(
        (("python",), ("python", "go"), ()),
        ("SOFTWARE_ENGINEERING", "DATA", None),
        (M, Seniority.UNKNOWN),
        (True, False),
    ):
        cases.append(
            (
                _opportunity(
                    required_skills=skills,
                    role_family=family,
                    seniority=level,
                    published_at=ASSESSED_AT if recent else None,
                ),
                _profile(),
            )
        )
    return cases


def _scores(rules: MatchingRuleSet) -> list[Decimal]:
    return [
        evaluate_match(opportunity, profile, rules, assessed_at=ASSESSED_AT).score
        for opportunity, profile in _grid()
    ]


def test_score_distribution_on_the_synthetic_grid_is_less_concentrated() -> None:
    """Before (unknown = neutral 0.5) against after (unknown 0.45), same 36 postings."""
    neutral = MatchingRuleSet(
        "matching-v5", default_rule_set().factors, unknown_score=Decimal("0.5")
    )
    before = Counter(_scores(neutral))
    after = Counter(_scores(default_rule_set()))

    assert sum(before.values()) == sum(after.values()) == 36
    # Pinned measurement, reported in docs/55-plano-melhorias/evidencias.
    assert (len(before), max(before.values())) == (15, 5)
    assert (len(after), max(after.values())) == (29, 2)


# --- R55-D3 ------------------------------------------------------------------------------

_FIT = Decimal("1")
_ADJACENT = SENIORITY_ADJACENT_SCORE
_ABOVE = SENIORITY_ABOVE_PREFERENCE_SCORE


@pytest.mark.parametrize(
    ("accepted", "posting", "state", "raw"),
    [
        # accepted levels are a full fit
        ((J, M), M, KnowledgeState.TRUE, _FIT),
        ((J, M), J, KnowledgeState.TRUE, _FIT),
        ((M,), M, KnowledgeState.TRUE, _FIT),
        # the junior/mid band: the other level is a near fit, never an elimination
        ((J,), M, KnowledgeState.TRUE, _ADJACENT),
        ((M,), J, KnowledgeState.TRUE, _ADJACENT),
        ((Seniority.UNKNOWN, J), M, KnowledgeState.TRUE, _ADJACENT),
        # senior tier above the preference is a penalty, not an elimination
        ((J, M), S, KnowledgeState.TRUE, _ABOVE),
        ((J,), Seniority.STAFF, KnowledgeState.TRUE, _ABOVE),
        ((M,), Seniority.LEAD, KnowledgeState.TRUE, _ABOVE),
        # outside the band and not above: still ineligible
        ((J, M), Seniority.INTERN, KnowledgeState.FALSE, Decimal("0")),
        ((Seniority.INTERN,), J, KnowledgeState.FALSE, Decimal("0")),
        ((S,), M, KnowledgeState.FALSE, Decimal("0")),
        # unknown on either side is unknown
        ((J, M), Seniority.UNKNOWN, KnowledgeState.UNKNOWN, None),
        ((), M, KnowledgeState.UNKNOWN, None),
    ],
)
def test_seniority_band_table(
    accepted: tuple[Seniority, ...],
    posting: Seniority,
    state: KnowledgeState,
    raw: Decimal | None,
) -> None:
    opportunity = _opportunity(seniority=posting)
    profile = _profile(accepted_seniorities=accepted)

    eligibility = evaluate_eligibility(opportunity, profile)
    seniority_filter = next(
        item for item in eligibility.filters if item.code == "SENIORITY_COMPATIBLE"
    )
    factor = _factor(
        evaluate_match(opportunity, profile, default_rule_set(), assessed_at=ASSESSED_AT),
        "SENIORITY_SCOPE",
    )

    assert seniority_filter.result is state
    if raw is None:
        assert factor.raw_score == UNKNOWN_FACTOR_SCORE
    else:
        assert factor.raw_score == raw


def test_an_adjacent_level_stays_eligible_and_is_not_capped_at_watchlist() -> None:
    result = evaluate_match(
        _opportunity(seniority=M),
        _profile(accepted_seniorities=(J,)),
        default_rule_set(),
        assessed_at=ASSESSED_AT,
    )

    assert result.eligibility.status is EligibilityStatus.ELIGIBLE
    assert result.verdict in {Verdict.HIGH_PRIORITY, Verdict.RECOMMENDED}


def test_a_senior_posting_is_ranked_lower_but_never_eliminated() -> None:
    accepted = _profile(accepted_seniorities=(J, M))
    senior = evaluate_match(
        _opportunity(seniority=S), accepted, default_rule_set(), assessed_at=ASSESSED_AT
    )
    mid = evaluate_match(
        _opportunity(seniority=M), accepted, default_rule_set(), assessed_at=ASSESSED_AT
    )

    assert senior.verdict is not Verdict.INELIGIBLE
    assert senior.eligibility.status is EligibilityStatus.ELIGIBLE
    assert senior.verdict in {Verdict.WATCHLIST, Verdict.LOW_MATCH}
    assert senior.score < mid.score


@pytest.mark.parametrize(
    "title",
    ["Intermediate Backend Engineer", "Mid-level Data Engineer", "Desenvolvedor Pleno"],
)
def test_intermediate_and_mid_titles_fit_a_junior_profile_end_to_end(title: str) -> None:
    level = infer_seniority(title, None, {})
    result = evaluate_match(
        _opportunity(seniority=level),
        _profile(accepted_seniorities=(J,)),
        default_rule_set(),
        assessed_at=ASSESSED_AT,
    )

    assert level is M
    assert result.eligibility.status is EligibilityStatus.ELIGIBLE
    assert _factor(result, "SENIORITY_SCOPE").raw_score == _ADJACENT


# --- replay gate: the new numbers belong to matching-v6 only -------------------------------


@pytest.mark.parametrize("version", ["matching-v1", "matching-v4", "matching-v5"])
def test_replaying_an_older_version_gives_its_own_numbers(version: str) -> None:
    rules = default_rule_set(version)
    unknown = evaluate_match(
        _opportunity(required_skills=()), _profile(), rules, assessed_at=ASSESSED_AT
    )
    adjacent = evaluate_match(
        _opportunity(seniority=M),
        _profile(accepted_seniorities=(J,)),
        rules,
        assessed_at=ASSESSED_AT,
    )

    assert rules.unknown_score == Decimal("0.5")
    assert rules.seniority_bands is False
    assert _factor(unknown, "TECHNOLOGY_FIT").raw_score == Decimal("0.5")
    assert adjacent.eligibility.status is EligibilityStatus.INELIGIBLE
    assert _factor(adjacent, "SENIORITY_SCOPE").raw_score == Decimal("0")


def test_only_matching_v6_applies_the_unknown_score_and_the_band() -> None:
    rules = default_rule_set("matching-v6")
    unknown = evaluate_match(
        _opportunity(required_skills=()), _profile(), rules, assessed_at=ASSESSED_AT
    )
    adjacent = evaluate_match(
        _opportunity(seniority=M),
        _profile(accepted_seniorities=(J,)),
        rules,
        assessed_at=ASSESSED_AT,
    )

    assert rules.unknown_score == UNKNOWN_FACTOR_SCORE
    assert rules.seniority_bands is True
    assert _factor(unknown, "TECHNOLOGY_FIT").raw_score == UNKNOWN_FACTOR_SCORE
    assert adjacent.eligibility.status is not EligibilityStatus.INELIGIBLE
    assert _factor(adjacent, "SENIORITY_SCOPE").raw_score == SENIORITY_ADJACENT_SCORE
