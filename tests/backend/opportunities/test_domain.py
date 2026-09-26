from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from opportunity_radar.opportunities.domain import (
    SKILL_TAXONOMY,
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
    seniority_classification,
)
from opportunity_radar.opportunities.role_family import ROLE_FAMILY_VERSION, RoleFamily


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


def test_candidate_carries_the_role_family_decision_and_its_evidence() -> None:
    """Card F17-02: normalization must classify the area, not just skip past it."""
    candidate = build_candidate(_input(title="Senior C++ Engineer"))
    assert candidate.role_family is RoleFamily.SOFTWARE_ENGINEERING
    assert candidate.role_family_version == ROLE_FAMILY_VERSION
    assert candidate.role_family_evidence["rule"]

    unknown = build_candidate(_input(title="Solutions Engineer"))
    assert unknown.role_family is RoleFamily.UNKNOWN

    department_led = build_candidate(
        _input(
            title="Team Lead",
            metadata={"department": "Sales"},
        )
    )
    assert department_led.role_family is RoleFamily.SALES
    assert department_led.role_family_evidence["origin"] == "department"


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


def test_seniority_classification_records_precedence_and_conflicts() -> None:
    title_value, title_reason = seniority_classification("Junior Engineer", {})
    structured_value, structured_reason = seniority_classification(
        "Engineer", {"seniority": "Mid"}
    )
    conflict_value, conflict_reason = seniority_classification(
        "Senior Engineer", {"seniority": "Junior"}
    )
    unmapped_value, unmapped_reason = seniority_classification(
        "Engineer", {"seniority": "Astronaut"}
    )

    assert title_value is Seniority.JUNIOR
    assert title_reason["source"] == "title"
    assert structured_value is Seniority.MID
    assert structured_reason["source"] == "structured"
    assert structured_reason["external_value"] == "Mid"
    assert conflict_value is Seniority.UNKNOWN
    assert conflict_reason["source"] == "conflict"
    assert unmapped_value is Seniority.UNKNOWN
    assert unmapped_reason["source"] == "structured"


def test_seniority_v2_covers_portuguese_titles_and_abbreviations() -> None:
    from opportunity_radar.opportunities.domain import SENIORITY_MAPPING_VERSION

    assert SENIORITY_MAPPING_VERSION == "seniority-v2"
    assert infer_seniority("Engenheiro Especialista", None, {}) is Seniority.STAFF
    assert infer_seniority("Principal Engineer", None, {}) is Seniority.STAFF
    assert infer_seniority("Desenvolvedor Pl", None, {}) is Seniority.MID
    assert infer_seniority("Desenvolvedor Pl.", None, {}) is Seniority.MID
    assert infer_seniority("Dev Jr", None, {}) is Seniority.JUNIOR
    assert infer_seniority("Dev Sr", None, {}) is Seniority.SENIOR
    assert infer_seniority("Tech Lider", None, {}) is Seniority.LEAD
    assert infer_seniority("Tech Líder", None, {}) is Seniority.LEAD


def test_structured_seniority_conflict_keeps_candidate_unknown() -> None:
    candidate = build_candidate(
        _input(title="Senior Engineer", metadata={"seniority": "Junior"})
    )

    assert candidate.seniority is Seniority.UNKNOWN


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
    assert by_id["react"].taxonomy_version == "skills-v2"
    assert "Required: React.js" in by_id["react"].evidence_text


def test_extracts_skills_from_structured_tags() -> None:
    skills = extract_skills(None, None, {"tags": ["python", "ReactJS"]})

    assert {skill.canonical_id for skill in skills} == {"python", "react"}


def test_skills_v2_never_removes_or_narrows_a_skills_v1_entry() -> None:
    """Criterion: 'reprocessamento não regride evidência existente' (F20-02/F17-06).

    `skills-v2` (`docs/pesquisas/curadoria-skills-v2.md`) only added `ai`, `cicd` and
    `observability` on top of the 27 `skills-v1` entries. Every `skills-v1` canonical id
    keeps every one of its original aliases in `skills-v2`: a description that matched a
    skill before the bump still matches the same skill after it, so the official
    reprocessing (`NORMALIZER_VERSION` bump) can only add evidence, never drop it.
    """
    skills_v1_baseline: dict[str, tuple[str, ...]] = {
        "python": ("python",),
        "typescript": ("typescript",),
        "javascript": ("javascript",),
        "react": ("react", "react.js", "reactjs"),
        "nextjs": ("next.js", "nextjs"),
        "nodejs": ("node.js", "nodejs"),
        "fastapi": ("fastapi",),
        "django": ("django",),
        "flask": ("flask",),
        "java": ("java",),
        "kotlin": ("kotlin",),
        "go": ("golang", "go"),
        "rust": ("rust",),
        "csharp": ("c#", "csharp", "c-sharp"),
        "dotnet": (".net", "dotnet", ".net core"),
        "sql": ("sql",),
        "postgresql": ("postgresql", "postgres"),
        "mysql": ("mysql",),
        "mongodb": ("mongodb", "mongo db"),
        "redis": ("redis",),
        "docker": ("docker",),
        "kubernetes": ("kubernetes", "k8s"),
        "aws": ("aws", "amazon web services"),
        "azure": ("azure",),
        "gcp": ("gcp", "google cloud platform"),
        "terraform": ("terraform",),
        "graphql": ("graphql",),
    }
    current_by_id = {entry.canonical_id: set(entry.aliases) for entry in SKILL_TAXONOMY}

    assert set(skills_v1_baseline) <= set(current_by_id)
    for canonical_id, baseline_aliases in skills_v1_baseline.items():
        assert set(baseline_aliases) <= current_by_id[canonical_id], (
            f"{canonical_id} lost a skills-v1 alias in skills-v2"
        )
    # F20-02's curated additions are net-new entries, not replacements.
    assert {"ai", "cicd", "observability"} <= set(current_by_id) - set(skills_v1_baseline)


def test_ambiguous_skill_aliases_require_technical_context() -> None:
    prose = extract_skills(
        None,
        "A software engineer who can react quickly in go-to-market work.",
        {},
    )
    portuguese_title = extract_skills("Desenvolvedor React", None, {})
    business_title = extract_skills("Go-to-Market Manager", None, {})
    explicit_sentence = extract_skills(None, "Required: React.", {})
    structured = extract_skills(None, None, {"skills": ["React", "Go"]})

    assert prose == ()
    assert {skill.canonical_id for skill in portuguese_title} == {"react"}
    assert business_title == ()
    assert {skill.canonical_id for skill in explicit_sentence} == {"react"}
    assert {skill.canonical_id for skill in structured} == {"react", "go"}


def test_extracts_skills_added_by_f20_02_curation() -> None:
    """Regression for `docs/pesquisas/curadoria-skills-v2.md` (card F20-02).

    Excerpts below are real acervo text (Render "Senior/Staff Data Scientist" and
    "Engineering Manager, Platform" postings), not fabricated fixtures.
    """
    ai_skills = extract_skills(
        None,
        "focusing on some combination of data analytics, analytics engineering, "
        "machine learning, and experimentation based on your strengths.",
        {},
    )
    assert {skill.canonical_id for skill in ai_skills} == {"ai"}

    ci_and_observability = extract_skills(
        None,
        "bring Render's internal developer platform and shared production "
        "infrastructure (observability, CI/CD, developer environments, storage, "
        "and more) from good to great.",
        {},
    )
    by_id = {skill.canonical_id: skill for skill in ci_and_observability}
    assert {"cicd", "observability"}.issubset(by_id)

    ai_alias = extract_skills(
        None,
        "We may use artificial intelligence (AI) tools to support parts of the "
        "hiring process.",
        {},
    )
    assert {skill.canonical_id for skill in ai_alias} == {"ai"}

    agentic_alias = extract_skills(None, "Required: experience with agentic AI systems.", {})
    assert {skill.canonical_id for skill in agentic_alias} == {"ai"}


def test_candidate_enrichment_does_not_change_fingerprint() -> None:
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
