"""Regression of `matching-v2` over the 50 labeled cases (card F48-12).

The cases carry the `matching-v1` snapshots the rules saw. They are rebuilt into value objects
and re-evaluated with the current rule set; the verdict distribution before (recorded in the
case) and after is what the card reports.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from opportunity_radar.matching.domain import (
    CompanyPriority,
    CompensationSnapshot,
    MatchResult,
    OpportunitySnapshot,
    OpportunityWorkAuthorization,
    ProfileSnapshot,
    ProfileWorkAuthorization,
    Verdict,
    default_rule_set,
    evaluate_match,
)
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.domain import (
    CompensationPeriod,
    ContractType,
    OpportunityStatus,
    Seniority,
    WorkMode,
)
from opportunity_radar.opportunities.role_family import classify_role_family

CASES = Path(__file__).resolve().parents[3] / "prompts/opportunity_analysis/eval/cases"
#: The cases were collected in late February 2026; recency is measured from a fixed date so
#: the distribution is reproducible.
ASSESSED_AT = datetime(2026, 3, 1, tzinfo=timezone.utc)


def _compensation(value: dict[str, Any] | None) -> CompensationSnapshot | None:
    if not value:
        return None
    return CompensationSnapshot(
        minimum=Decimal(value["minimum"]) if value.get("minimum") else None,
        maximum=Decimal(value["maximum"]) if value.get("maximum") else None,
        currency=value.get("currency"),
        period=CompensationPeriod(value["period"]) if value.get("period") else None,
    )


def rebuild(case: dict[str, Any]) -> tuple[OpportunitySnapshot, ProfileSnapshot]:
    payload = case["payload"]
    raw = payload["opportunity_snapshot"]
    profile = payload["profile_snapshot"]
    decision = classify_role_family(
        title=case["posting"]["title"], description=case["posting"]["description"]
    )
    opportunity = OpportunitySnapshot(
        opportunity_id=UUID(raw["opportunity_id"]),
        content_version=raw["content_version"],
        status=OpportunityStatus(raw["status"]),
        work_mode=WorkMode(raw["work_mode"]),
        seniority=Seniority(raw["seniority"]),
        allowed_countries=tuple(raw.get("allowed_countries", ())),
        contract_types=tuple(ContractType(item) for item in raw.get("contract_types", ())),
        required_skills=tuple(raw.get("required_skills", ())),
        preferred_skills=tuple(raw.get("preferred_skills", ())),
        company_priority=(
            CompanyPriority(raw["company_priority"]) if raw.get("company_priority") else None
        ),
        compensation=_compensation(raw.get("compensation")),
        compensation_conflict=raw.get("compensation_conflict", False),
        work_authorization=OpportunityWorkAuthorization(
            raw.get("work_authorization", "NOT_STATED")
        ),
        published_at=(
            datetime.fromisoformat(raw["published_at"]) if raw.get("published_at") else None
        ),
        role_family=decision.role_family.value,
        evidence_refs=tuple(raw.get("evidence_refs", ())),
    )
    return opportunity, ProfileSnapshot(
        profile_version_id=UUID(profile["profile_version_id"]),
        skills=tuple(profile.get("skills", ())),
        countries=tuple(profile.get("countries", ())),
        accepted_work_modes=tuple(WorkMode(i) for i in profile.get("accepted_work_modes", ())),
        accepted_contract_types=tuple(
            ContractType(i) for i in profile.get("accepted_contract_types", ())
        ),
        accepted_seniorities=tuple(
            Seniority(i) for i in profile.get("accepted_seniorities", ())
        ),
        compensation=_compensation(profile.get("compensation")),
        work_authorization=ProfileWorkAuthorization(profile.get("work_authorization", "UNKNOWN")),
        evidence_refs=tuple(profile.get("evidence_refs", ())),
    )


def load() -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(CASES.glob("*.json"))]


def reevaluate(case: dict[str, Any]) -> MatchResult:
    opportunity, profile = rebuild(case)
    return evaluate_match(
        opportunity, profile, default_rule_set(RULES_VERSION), assessed_at=ASSESSED_AT
    )


def distribution(cases: list[dict[str, Any]]) -> Counter[str]:
    return Counter(reevaluate(case).verdict.value for case in cases)


def test_the_labeled_set_has_fifty_cases() -> None:
    assert len(load()) == 50


def test_v2_leaves_the_review_wall_and_reaches_the_positive_verdicts() -> None:
    after = distribution(load())

    positive = (
        after[Verdict.HIGH_PRIORITY.value]
        + after[Verdict.RECOMMENDED.value]
        + after[Verdict.WATCHLIST.value]
    )
    assert positive > 0
    eligible = sum(after.values()) - after[Verdict.INELIGIBLE.value]
    assert positive / eligible >= 0.3
    # matching-v1 recorded 40 REVIEW_REQUIRED of the 40 not-ineligible cases.
    assert after[Verdict.REVIEW_REQUIRED.value] < 40


def test_v2_distribution_is_pinned() -> None:
    """Before: 40 REVIEW_REQUIRED and 10 INELIGIBLE (recorded in the cases, matching-v1)."""
    before = Counter(case["payload"]["verdict"] for case in load())

    assert before == {"REVIEW_REQUIRED": 40, "INELIGIBLE": 10}
    assert distribution(load()) == {"WATCHLIST": 34, "LOW_MATCH": 6, "INELIGIBLE": 10}


def test_a_hard_filter_failure_stays_ineligible_in_v2() -> None:
    recorded = [c for c in load() if c["payload"]["verdict"] == "INELIGIBLE"]

    assert len(recorded) == 10
    assert all(reevaluate(case).verdict is Verdict.INELIGIBLE for case in recorded)


def test_no_case_is_review_required_without_a_conflict() -> None:
    for case in load():
        result = reevaluate(case)
        if result.verdict is Verdict.REVIEW_REQUIRED:
            assert case["payload"]["opportunity_snapshot"]["compensation_conflict"]


def test_reevaluation_is_deterministic() -> None:
    cases = load()

    assert [reevaluate(c) for c in cases] == [reevaluate(c) for c in cases]
