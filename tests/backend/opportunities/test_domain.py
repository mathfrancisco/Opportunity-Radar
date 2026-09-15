from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from opportunity_radar.opportunities.domain import (
    Compensation,
    CompensationPeriod,
    ContractType,
    GrossNet,
    NormalizationError,
    NormalizationInput,
    OpportunityStatus,
    Seniority,
    SkillClassification,
    WorkMode,
    build_candidate,
    extract_compensation,
    extract_skills,
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
        "source_type": "manual",
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


def test_compensation_uses_decimal_and_rejects_an_inverted_range() -> None:
    compensation = Compensation(
        minimum=Decimal("100000"),
        maximum=Decimal("150000"),
        currency="USD",
        period=CompensationPeriod.YEAR,
        gross_net=GrossNet.GROSS,
        evidence="USD 100000-150000 per year gross",
        evidence_source="test",
    )

    assert compensation.minimum == Decimal("100000")
    with pytest.raises(NormalizationError):
        Compensation(
            minimum=Decimal("150001"),
            maximum=Decimal("150000"),
            currency="USD",
            period=None,
            gross_net=None,
            evidence="source range",
            evidence_source="test",
        )


def test_extracts_structured_compensation_before_explicit_text() -> None:
    lever = extract_compensation(
        {"salaryRange": {"min": 100000, "max": 150000, "currency": "USD"}},
        "Salary BRL 1 - BRL 2 per month",
        source_type="lever",
    )
    ashby = extract_compensation(
        {
            "compensation": {
                "summaryComponents": [
                    {"name": "Equity", "min": 1, "max": 2},
                    {
                        "compensationType": "Salary",
                        "minValue": "120000",
                        "maxValue": "150000",
                        "currencyCode": "USD",
                        "interval": "1 YEAR",
                    },
                ]
            }
        },
        None,
        source_type="ashby",
    )

    assert lever is not None
    assert lever.minimum == Decimal("100000")
    assert lever.period is None
    assert ashby is not None
    assert ashby.period is CompensationPeriod.YEAR
    assert ashby.evidence_source == "ashby.compensation.summaryComponents.Salary"


def test_explicit_text_does_not_guess_currency_or_period() -> None:
    compensation = extract_compensation(
        {"salary": "$80k - $100k"}, None, source_type="remotive"
    )

    assert compensation is not None
    assert compensation.minimum == Decimal("80000")
    assert compensation.maximum == Decimal("100000")
    assert compensation.currency is None
    assert compensation.period is None
    assert compensation.evidence_source == "remotive.salary"


def test_parses_brazilian_compensation_and_rejects_database_overflow() -> None:
    compensation = extract_compensation(
        {"salary": "Remuneração BRL 10.000,00 - 15.000,00 por month"},
        None,
        source_type="manual",
    )

    assert compensation is not None
    assert compensation.minimum == Decimal("10000.00")
    assert compensation.maximum == Decimal("15000.00")
    with pytest.raises(NormalizationError, match="database precision"):
        extract_compensation(
            {
                "salaryRange": {
                    "min": "1000000000000.00",
                    "currency": "USD",
                }
            },
            None,
            source_type="lever",
        )


def test_extracts_versioned_canonical_skills_with_conservative_classification() -> None:
    skills = extract_skills(
        "ReactJS Engineer",
        "Required: React.js, Python and PostgreSQL. Nice to have Docker. "
        "Do not match reacting or postgresqlish.",
        {},
    )
    by_id = {skill.canonical_id: skill for skill in skills}

    assert set(by_id) == {"react", "python", "postgresql", "docker"}
    assert by_id["react"].classification is SkillClassification.REQUIRED
    assert by_id["docker"].classification is SkillClassification.PREFERRED
    assert by_id["react"].taxonomy_version == "skills-v1"
    assert "Required: React.js" in by_id["react"].evidence_text


def test_extracts_skills_from_structured_tags() -> None:
    skills = extract_skills(None, None, {"tags": ["python", "ReactJS"]})

    assert {skill.canonical_id for skill in skills} == {"python", "react"}


def test_ambiguous_skill_aliases_require_technical_context() -> None:
    prose = extract_skills(
        None,
        "A software engineer who can react quickly in go-to-market work.",
        {},
    )
    portuguese_title = extract_skills("Desenvolvedor React", None, {})
    business_title = extract_skills("Go-to-Market Manager", None, {})
    structured = extract_skills(None, None, {"skills": ["React", "Go"]})

    assert prose == ()
    assert {skill.canonical_id for skill in portuguese_title} == {"react"}
    assert business_title == ()
    assert {skill.canonical_id for skill in structured} == {"react", "go"}


def test_candidate_includes_compensation_and_deduplicated_skills_without_fingerprint_change() -> None:
    candidate = build_candidate(
        _input(
            title="React.js Engineer",
            description="Required: ReactJS and Python. Salary USD 100000 per year.",
        )
    )

    assert candidate.compensation is not None
    assert candidate.compensation.currency == "USD"
    assert {skill.canonical_id for skill in candidate.skills} == {"react", "python"}
    assert candidate.fingerprint_version == "v1"
