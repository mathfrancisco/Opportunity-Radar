from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from opportunity_radar.opportunities import content_classification as content
from opportunity_radar.opportunities.domain import (
    SKILL_TAXONOMY,
    SKILL_TAXONOMY_VERSION,
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
from opportunity_radar.opportunities.regions import (
    LATAM_COUNTRIES,
    REGIONS_VERSION_V2,
    resolve_allowed_countries_v2,
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


# Card F20-23 ground truth: docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json
# labelled 13 real work_mode=UNKNOWN postings with recoverable evidence. The deterministic
# rule only ever looked at title/location/metadata, never description, so any posting that
# states its mode only in a standardized "Work Model for this Role" description section (a
# Greenhouse-style pattern used by several real employers in the sample) stayed UNKNOWN.
# Excerpts below are anonymised/trimmed reproductions of that evidence, not verbatim scrapes.
@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        # "Work model  Hybrid  Office requirement  2 days per week at the office"
        (
            "Controllership Expert - Record to Report",
            "Work model  Hybrid  Office requirement  2 days per week at the office",
            WorkMode.HYBRID,
        ),
        # "Our hybrid work model brings us to the office at least twice a week"
        (
            "Operations & Capabilities Lead",
            "Our hybrid work model brings us to the office at least twice a week, "
            "on strategic days.",
            WorkMode.HYBRID,
        ),
        # "Roles are open in Brazil (hybrid model) or key US hubs"
        (
            "Senior Staff Software Engineer - Money Boxes",
            "Roles are open in Brazil (hybrid model) or key US hubs.",
            WorkMode.HYBRID,
        ),
        # "Work Model for this Role - Hybrid 2-3 times/week: Our hybrid work model ..."
        (
            "Lead Software Engineer (CloudNetwork)",
            "Work Model for this Role - Hybrid 2-3 times/week: Our hybrid work model brings "
            "us to the office at least twice a week.",
            WorkMode.HYBRID,
        ),
        # same section, all-caps heading as seen in another real posting
        (
            "Senior Security Engineer (Incident Response)",
            "WORK MODEL FOR THIS ROLE - Hybrid 2-3 times/week: Our hybrid work model brings "
            "us to the office at least twice a week.",
            WorkMode.HYBRID,
        ),
        # title-only marker: already handled by the existing title regex, kept here as a
        # regression pin for the "(Hybrid)" title-marker case F20-23 also flagged.
        (
            "Enterprise Sales Development Representative US (Hybrid)",
            None,
            WorkMode.HYBRID,
        ),
        (
            "Sales Development Representative - DACH (Berlin Hybrid)",
            None,
            WorkMode.HYBRID,
        ),
        # "This is a fully on-site role based at our Bogota office"
        (
            "Customer Excellence Senior Analyst - Bogota (German Speaker)",
            "This is a fully on-site role based at our Bogota office.",
            WorkMode.ONSITE,
        ),
        # "Location: San Francisco, CA (SF HQ) preferred, on-site five days a week"
        (
            "Legal Operations Manager",
            "Location: San Francisco, CA (SF HQ) preferred, on-site five days a week.",
            WorkMode.ONSITE,
        ),
    ],
)
def test_infers_work_mode_from_the_standardized_description_section(
    title: str, description: str | None, expected: WorkMode
) -> None:
    assert infer_work_mode(title, None, {}, description) is expected


def test_work_mode_from_description_avoids_known_false_positive_shapes() -> None:
    """F20-23 also flagged near-miss phrasing that must stay UNKNOWN, not guessed."""
    # A colleague's remote status is not this role's work mode.
    assert (
        infer_work_mode(
            "Software Engineer",
            None,
            {},
            "Partner with our senior remote engineers across the org on this initiative.",
        )
        is WorkMode.UNKNOWN
    )
    # Generic remote-friendly-company boilerplate, unrelated to this specific role.
    assert (
        infer_work_mode(
            "Software Engineer",
            None,
            {},
            "We are a remote-friendly company that values flexibility and trust.",
        )
        is WorkMode.UNKNOWN
    )
    # Two real F20-23 cases were intentionally left out of the fix: the evidence ("If
    # you're remote, we'll arrange in-person events"; "Home office ... Async working") is
    # too indirect to extract safely without risking false positives elsewhere, so both
    # must remain UNKNOWN rather than being guessed as REMOTE.
    assert (
        infer_work_mode(
            "Backend Engineer (Security)",
            None,
            {},
            "Open to in-person events throughout the year. If you're remote, we'll "
            "arrange these so the team gets real time together.",
        )
        is WorkMode.UNKNOWN
    )
    assert (
        infer_work_mode(
            "Technical Recruiter (3 month FTC, Temp to Perm)",
            None,
            {},
            "Home office - we help provide equipment for a comfortable setup so you're "
            "as productive at home as you are in the office. Async working.",
        )
        is WorkMode.UNKNOWN
    )
    # A conflicting explicit title marker vs. description section must stay UNKNOWN
    # rather than silently favoring either signal.
    assert (
        infer_work_mode(
            "Engineer (Hybrid)",
            None,
            {},
            "Work Model for this Role - Remote",
        )
        is WorkMode.UNKNOWN
    )


def test_seniority_classification_records_precedence_and_conflicts() -> None:
    title_value, title_reason = seniority_classification("Junior Engineer", {})
    structured_value, structured_reason = seniority_classification("Engineer", {"seniority": "Mid"})
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

    assert SENIORITY_MAPPING_VERSION == "seniority-v5"
    assert infer_seniority("Engenheiro Especialista", None, {}) is Seniority.STAFF
    assert infer_seniority("Principal Engineer", None, {}) is Seniority.STAFF
    assert infer_seniority("Desenvolvedor Pl", None, {}) is Seniority.MID
    assert infer_seniority("Desenvolvedor Pl.", None, {}) is Seniority.MID
    assert infer_seniority("Dev Jr", None, {}) is Seniority.JUNIOR
    assert infer_seniority("Dev Sr", None, {}) is Seniority.SENIOR
    assert infer_seniority("Tech Lider", None, {}) is Seniority.LEAD
    assert infer_seniority("Tech Líder", None, {}) is Seniority.LEAD


# Card F20-70: the noun form "estágio"/"estágia" was already covered, but the far more
# common Brazilian job-title form is the person/adjective "estagiário"/"estagiária"
# ("Vaga de Estagiário de X"), and several entry-program keywords (trainee, entry
# level, new grad, apprentice/aprendiz, early career, graduate) had no pattern at all
# and fell into UNKNOWN. docs/44-roadmap-fase-20/fase-20/
# f20-70-lacunas-de-palavra-chave-senioridade.md.
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Vaga de Estagiário de Dados", Seniority.INTERN),
        ("Vaga de Estagiária de Dados", Seniority.INTERN),
        ("Vaga de Estagiario de Dados", Seniority.INTERN),  # no accent
        ("Vaga de Estagiaria de Dados", Seniority.INTERN),  # no accent
        ("Estagiários de Engenharia", Seniority.INTERN),  # plural
        ("Programa Trainee 2027", Seniority.INTERN),
        # seniority-v5 (F52-02, SPEC 52 Q3): a first job, not an internship.
        ("Software Engineer, Entry Level", Seniority.JUNIOR),
        ("Software Engineer - Entry-Level", Seniority.JUNIOR),
        ("New Grad Software Engineer", Seniority.JUNIOR),
        ("New Graduate Software Engineer", Seniority.JUNIOR),
        ("Apprentice Software Engineer", Seniority.INTERN),
        ("Vaga de Aprendiz Administrativo", Seniority.INTERN),
        ("Early Career Software Engineer", Seniority.JUNIOR),
        ("Graduate Software Engineer", Seniority.JUNIOR),
        # An internship named with a junior word is still an internship.
        ("Business Development Associate Intern", Seniority.INTERN),
        ("Graduate Trainee, Data", Seniority.INTERN),
        ("Junior Software Engineer Internship", Seniority.INTERN),
    ],
)
def test_seniority_v3_covers_entry_program_keywords(title: str, expected: Seniority) -> None:
    assert infer_seniority(title, None, {}) is expected


# Negative cases from the same diagnostic: a bare "graduate" naming an academic
# credential, not a job level, must not become JUNIOR; "internal"/"international"
# must not become INTERN (title-only `\b` boundaries already prevented this — this
# locks the behavior in as a regression test).
@pytest.mark.parametrize(
    "title",
    [
        "Graduate School Recruiting Coordinator",
        "Graduate Degree Program Advisor",
        "Graduate Program Coordinator",
        "Internal Communications Specialist",
        "International Sales Analyst",
    ],
)
def test_seniority_v3_does_not_regress_false_positives(title: str) -> None:
    assert infer_seniority(title, None, {}) is Seniority.UNKNOWN


# Regression: senior/mid/lead terms that already worked in seniority-v2 must keep
# working unchanged after the v3 additions (same evidence as
# test_seniority_v2_covers_portuguese_titles_and_abbreviations, re-asserted here per
# card F20-70's explicit "não regredir" acceptance criterion).
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Senior Engineer", Seniority.SENIOR),
        ("Sr Engineer", Seniority.SENIOR),
        ("Desenvolvedor Pleno", Seniority.MID),
        ("Middle Engineer", Seniority.MID),
        ("Junior Developer", Seniority.JUNIOR),
    ],
)
def test_seniority_v3_does_not_regress_existing_terms(title: str, expected: Seniority) -> None:
    assert infer_seniority(title, None, {}) is expected


# Card F52-02: one case per row of the P2 table of docs/52-spec-aderencia-ao-nivel.md.
@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Dev. Back-end Node.js Sênior | Pix [Remoto]", Seniority.SENIOR),
        ("Desenvolvedor(a) Backend Sênior - Node.js", Seniority.SENIOR),
        ("Analista de Dados Júnior", Seniority.JUNIOR),
        ("Senior Staff Engineer - Enterprise Messaging", Seniority.STAFF),
        ("Software Engineer I", Seniority.JUNIOR),
        ("Software Engineer II", Seniority.MID),
        ("Software Engineer III", Seniority.SENIOR),
        ("Software Architect (AWS, NodeJS)", Seniority.SENIOR),
        ("Head of Engineering", Seniority.DIRECTOR),
        ("Tech Lead | Engenheiro(a) Backend Especialista", Seniority.LEAD),
        ("Associate Software Engineer", Seniority.JUNIOR),
        ("Systems Software Engineer - New College Grad 2026", Seniority.JUNIOR),
        ("Desenvolvedor Pl/Sr", Seniority.MID),
        ("Entry Level Developer", Seniority.JUNIOR),
    ],
)
def test_seniority_v5_classifies_the_titles_of_the_spec_52_table(
    title: str, expected: Seniority
) -> None:
    assert infer_seniority(title, None, {}) is expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # Two levels in one compound title: the higher one.
        ("Sr. Staff Software Engineer", Seniority.STAFF),
        ("Finance Data Engineer (Senior Manager)", Seniority.MANAGER),
        ("Senior Director of Engineering", Seniority.DIRECTOR),
        ("Associate Director, Data", Seniority.DIRECTOR),
        # An inverted title is not a range from senior to manager.
        ("Manager, Senior Data Engineer", Seniority.MANAGER),
        # A level word beats a numeral and a role that only implies a level.
        ("Senior Software Engineer II", Seniority.SENIOR),
        ("Principal Architect", Seniority.STAFF),
        ("Estágio em Engenharia de Dados", Seniority.INTERN),
        ("Java Developer Semi Senior", Seniority.MID),
        ("Engineer I - Payments", Seniority.JUNIOR),
    ],
)
def test_seniority_v5_takes_the_highest_named_level(title: str, expected: Seniority) -> None:
    assert infer_seniority(title, None, {}) is expected


@pytest.mark.parametrize(
    ("title", "expected", "levels"),
    [
        ("Desenvolvedor Pl/Sr", Seniority.MID, "MID,SENIOR"),
        ("Desenvolvedor(a) .NET Core Senior/Pleno(a)", Seniority.MID, "MID,SENIOR"),
        ("Desenvolvedor(a) COBOL | Pleno a Sênior", Seniority.MID, "MID,SENIOR"),
        ("Dev Java (Junior, Pleno e Sênior)", Seniority.JUNIOR, "JUNIOR,MID,SENIOR"),
        ("Junior to Senior Fullstack Engineer", Seniority.JUNIOR, "JUNIOR,SENIOR"),
        ("Software Engineer (Mid-Level, Senior or Staff)", Seniority.MID, "MID,SENIOR,STAFF"),
        ("Senior/Staff/Principal Engineer", Seniority.SENIOR, "SENIOR,STAFF"),
        ("Engineer II/III, Automation", Seniority.MID, "MID,SENIOR"),
    ],
)
def test_seniority_v5_keeps_the_lowest_level_of_a_range_and_cites_the_range(
    title: str, expected: Seniority, levels: str
) -> None:
    # SPEC 52, Q1: the lowest level is stored and the range goes to the evidence.
    value, reason = seniority_classification(title, {})

    assert value is expected
    assert reason["value"] == expected.value
    assert reason["range"] == levels
    assert reason["mapping_version"] == "seniority-v5"


def test_seniority_v5_cites_no_range_for_a_single_or_compound_level() -> None:
    assert seniority_classification("Senior Staff Engineer", {})[1]["range"] is None
    assert seniority_classification("Junior Engineer", {})[1]["range"] is None
    assert seniority_classification("Engineer", {})[1]["range"] is None


@pytest.mark.parametrize(
    "title",
    [
        "Member of Technical Staff, Pre-Training Data",  # a team name, at every level
        "Oracle PL/SQL Developer",
        "Solutions Engineer - Middle East",
        "Account Executive, Mid-Market",
        "Software Engineer IV",  # numerals above III have no agreed level
        "Desk Side Engineer 6439365",
        "AI Engineer",  # "AI" is not the numeral
    ],
)
def test_seniority_v5_does_not_read_a_level_into_lookalikes(title: str) -> None:
    assert infer_seniority(title, None, {}) is Seniority.UNKNOWN


def test_structured_seniority_conflict_keeps_candidate_unknown() -> None:
    candidate = build_candidate(_input(title="Senior Engineer", metadata={"seniority": "Junior"}))

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
    other_source = build_candidate(_input(company_name=None, source_definition_id=uuid4()))

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
    compensation = extract_compensation({"salary": "$80k - $100k"}, None, source_type="remotive")

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
    assert by_id["react"].taxonomy_version == "skills-v4"
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
        "We may use artificial intelligence (AI) tools to support parts of the hiring process.",
        {},
    )
    assert {skill.canonical_id for skill in ai_alias} == {"ai"}

    agentic_alias = extract_skills(None, "Required: experience with agentic AI systems.", {})
    assert {skill.canonical_id for skill in agentic_alias} == {"ai"}


def test_removes_the_bare_ci_alias_that_false_matched_the_company_name() -> None:
    """Regression for the F20-02 rotulagem follow-up (rotulagem/f20-02-curadoria-skills-v2.md).

    82% of the real-corpus occurrences of the bare token `ci` came from the company
    name "CI&T", not from CI/CD content (the tokenizer splits on `&`). The alias was
    removed; only the multi-word forms remain.
    """
    ci_and_t_only = extract_skills(
        None,
        "CI&T, we help large enterprises reinvent through technology, "
        "consulting and design, always with the potential of AI.",
        {},
    )
    assert "cicd" not in {skill.canonical_id for skill in ci_and_t_only}

    ci_slash_cd = extract_skills(
        None,
        "You will own our CI/CD pipeline and developer environments.",
        {},
    )
    assert "cicd" in {skill.canonical_id for skill in ci_slash_cd}


def _skill_ids(description: str, title: str | None = None) -> set[str]:
    return {skill.canonical_id for skill in extract_skills(title, description, {})}


@pytest.mark.parametrize(
    "text",
    [
        "Experience building LLM applications in production.",
        "You will fine-tune LLMs for support tickets.",
        "Work with large language models and evaluation harnesses.",
        "Design RAG pipelines over internal documents.",
        "Hands-on with retrieval-augmented generation and vector stores.",
        "Solid machine learning fundamentals are required.",
        "Build generative AI features for our product.",
        "We are hiring for GenAI platform work.",
        "Ship AI agents that call internal tools.",
        "Experience with agentic workflows is a plus.",
        "We need an AI engineer to own our model serving.",
        "AI/ML experience preferred.",
        "Background in ML/AI research.",
        "Conhecimento em inteligência artificial e aprendizado de máquina.",
        "Experiência com IA generativa.",
        "Atuação com modelos de linguagem.",
        "Our artificial intelligence team is growing.",
    ],
)
def test_ai_skill_matches_specific_terms(text: str) -> None:
    assert "ai" in _skill_ids(text)


@pytest.mark.parametrize(
    "text",
    [
        "We are an AI-powered company.",
        "Join our AI company and help customers.",
        "We use AI to automate everything.",
        "The AI revolution is changing how we work.",
        "Our AI-first culture values curiosity.",
        "Powered by AI, loved by teams.",
        "Retell AI builds voice products.",
        "Send your resume to our email address.",
        "We maintain a large codebase.",
        "Thai speakers are welcome to apply.",
        "A personal aide to the CEO.",
        "Convert the ML markup file to HTML.",
        "Ability to work on a chain of tasks.",
        "Join a mail-order business.",
    ],
)
def test_ai_skill_ignores_the_bare_word(text: str) -> None:
    assert "ai" not in _skill_ids(text)


def test_llm_and_rag_are_own_skills_that_also_match_ai() -> None:
    llm = _skill_ids("Required: LLM experience.")
    rag = _skill_ids("Nice to have: RAG.")

    assert {"llm", "ai"} <= llm and "rag" not in llm
    assert {"rag", "ai"} <= rag and "llm" not in rag
    assert _skill_ids("retrieval-augmented generation") == {"rag", "ai"}
    assert _skill_ids("large language models") == {"llm", "ai"}


@pytest.mark.parametrize(
    ("skill", "positives", "negatives"),
    [
        (
            "spring boot",
            ["Spring Boot services", "Java with SpringBoot", "spring-boot microservices"],
            ["Spring cleaning of the backlog", "Our spring hiring plan", "Spring is here"],
        ),
        (
            "nestjs",
            ["Backend in NestJS", "Nest.js and TypeScript", "nestjs"],
            ["We nest tasks in epics", "Nest is a thermostat brand", "bird nest"],
        ),
        (
            "vue",
            ["Frontend in Vue", "Vue.js 3 and Pinia", "VueJS components"],
            ["A revue of the budget", "Our Park Avenue office", "interview process"],
        ),
        (
            "react native",
            ["Mobile apps with React Native", "react-native and Expo", "ReactNative"],
            ["Native speakers of Portuguese", "We react quickly", "reactive programming"],
        ),
        (
            "rag",
            ["Building RAG systems", "Required: RAG.", "experience with RAG and agents"],
            [
                "cloud storage and leverage",
                "Do not drag your feet",
                "a rag and a bucket",
                "fragment and garage",
            ],
        ),
        (
            "llm",
            ["LLM engineer", "building llms"],
            ["The Fllm project", "llmnr protocol", "a gllm library"],
        ),
    ],
)
def test_new_skills_have_word_boundary_safe_matches(
    skill: str, positives: list[str], negatives: list[str]
) -> None:
    for text in positives:
        assert skill in _skill_ids(text), text
    for text in negatives:
        assert skill not in _skill_ids(text), text


def test_rag_in_structured_tags_matches_any_case() -> None:
    skills = extract_skills(None, None, {"tags": ["rag", "vuejs"]})

    assert {skill.canonical_id for skill in skills} >= {"rag", "ai", "vue"}


def test_react_native_does_not_lose_react_or_the_other_way_round() -> None:
    both = _skill_ids("Required: React.js and React Native.")
    only_native = _skill_ids("Mobile apps with React Native.")

    assert {"react", "react native"} <= both
    assert "react native" in only_native


def test_skill_taxonomy_version_is_bumped_and_reaches_assessment_currency() -> None:
    from opportunity_radar.matching import currency, service

    assert SKILL_TAXONOMY_VERSION == "skills-v4"
    assert currency.SKILL_TAXONOMY_VERSION == SKILL_TAXONOMY_VERSION
    assert service.SKILL_TAXONOMY_VERSION == SKILL_TAXONOMY_VERSION
    assert extract_skills(None, "Required: Vue.", {})[0].taxonomy_version == SKILL_TAXONOMY_VERSION


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


# ---------------------------------------------------------------------------------------
# Card F48-15: seniority-v4 / work-mode-v7 / allowed-countries-v2 (content rules).
# Phrases below are modelled on real postings (Greenhouse/Ashby/Lever, PT and EN).
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "expected", "rule"),
    [
        # year ranges: 0-2 JUNIOR, 3-5 MID, 5+ SENIOR
        (
            "We expect 0-2 years of experience with Python.",
            Seniority.JUNIOR,
            "description_years_range",
        ),
        (
            "Requisitos: 1 a 2 anos de experiência com backend.",
            Seniority.JUNIOR,
            "description_years_range",
        ),
        (
            "You have 3-5 years of professional experience.",
            Seniority.MID,
            "description_years_range",
        ),
        ("Experiência de 3 a 5 anos com Java.", Seniority.MID, "description_years_range"),
        (
            "5-8 years of relevant experience in data engineering",
            Seniority.SENIOR,
            "description_years_range",
        ),
        ("5+ years of experience building APIs", Seniority.SENIOR, "description_years_min"),
        (
            "Mais de 7 anos de experiência com arquitetura",
            Seniority.SENIOR,
            "description_years_min",
        ),
        ("Minimum of 3 years experience with React", Seniority.MID, "description_years_min"),
        ("At least 1 year of experience in support", Seniority.JUNIOR, "description_years_min"),
        ("Pelo menos 2 anos de experiência em vendas", Seniority.JUNIOR, "description_years_min"),
        # entry-level / no-experience phrases
        (
            "This is an entry-level position on our platform team.",
            Seniority.JUNIOR,
            "description_entry_phrase",
        ),
        (
            "No prior experience required, we will train you.",
            Seniority.JUNIOR,
            "description_entry_phrase",
        ),
        (
            "Vaga nível júnior. Sem experiência prévia necessária.",
            Seniority.JUNIOR,
            "description_entry_phrase",
        ),
        (
            "Procuramos um júnior para o time de dados.",
            Seniority.JUNIOR,
            "description_entry_phrase",
        ),
        (
            "Esta é uma vaga de estágio para estudantes.",
            Seniority.INTERN,
            "description_intern_phrase",
        ),
        (
            "This is an internship for students graduating in 2027.",
            Seniority.INTERN,
            "description_intern_phrase",
        ),
    ],
)
def test_seniority_v4_reads_the_description_with_cited_evidence(
    description: str, expected: Seniority, rule: str
) -> None:
    value, reason = content.classify_seniority_v4("Engineer", description, {})
    assert value is expected
    assert reason["source"] == "description"
    assert reason["rule"] == rule
    assert reason["mapping_version"] == "seniority-v4"
    assert reason["evidence"]
    # the cited snippet really comes from the description
    assert " ".join((reason["evidence"] or "").split()) in " ".join(description.casefold().split())


@pytest.mark.parametrize(
    "description",
    [
        "We have 15 years of experience helping customers grow.",  # employer, not candidate
        "Our 10 years of experience in fintech drive the product.",
        "2-4 years of experience in a similar role.",  # straddles JUNIOR and MID
        "1-3 years of experience.",
        "3-6 years of experience.",
        "Entry-level position. Requires 5+ years of experience overall.",  # rules disagree
        "Join our internship program alumni network as a mentor.",
        "You will mentor junior engineers and review their work.",
        "A great place to work with a diverse team.",
        "",
    ],
)
def test_seniority_v4_stays_unknown_without_conclusive_evidence(description: str) -> None:
    value, reason = content.classify_seniority_v4("Engineer", description, {})
    assert value is Seniority.UNKNOWN
    assert reason["source"] == "none"
    assert reason["evidence"] is None


def test_seniority_v4_boundary_five_is_senior_only_as_a_lower_bound() -> None:
    assert content.classify_seniority_v4("E", "3-5 years of experience", {})[0] is Seniority.MID
    assert content.classify_seniority_v4("E", "5-7 years of experience", {})[0] is Seniority.SENIOR
    assert content.classify_seniority_v4("E", "5 years of experience", {})[0] is Seniority.SENIOR
    assert content.classify_seniority_v4("E", "4 years of experience", {})[0] is Seniority.MID
    assert content.classify_seniority_v4("E", "2 years of experience", {})[0] is Seniority.JUNIOR


def test_seniority_v4_precedence_structured_then_title_then_description() -> None:
    desc = "5+ years of experience required."
    # title beats description
    value, reason = content.classify_seniority_v4("Junior Engineer", desc, {})
    assert (value, reason["source"]) == (Seniority.JUNIOR, "title")
    # structured beats title and description
    value, reason = content.classify_seniority_v4(
        "Engineer", desc, {"seniority": "Mid"}, source_type="manual"
    )
    assert (value, reason["source"]) == (Seniority.MID, "structured")
    # structured vs title conflict stays UNKNOWN even with a decisive description
    value, reason = content.classify_seniority_v4(
        "Senior Engineer", desc, {"seniority": "Junior"}, source_type="manual"
    )
    assert (value, reason["source"]) == (Seniority.UNKNOWN, "conflict")
    # unmapped structured value never falls through to the description
    value, _ = content.classify_seniority_v4(
        "Engineer", desc, {"seniority": "Astronaut"}, source_type="manual"
    )
    assert value is Seniority.UNKNOWN


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Work Model for this Role: Remote", WorkMode.REMOTE),  # v6 phrase still works
        ("This is a fully remote position open to the whole team.", WorkMode.REMOTE),
        ("Vaga 100% remota, com encontros trimestrais.", WorkMode.REMOTE),
        ("Trabalho remoto com horário flexível.", WorkMode.REMOTE),
        ("Regime híbrido, 3 dias no escritório.", WorkMode.HYBRID),
        ("Modelo de trabalho híbrido em São Paulo.", WorkMode.HYBRID),
        ("This hybrid role requires 3 days per week in the office.", WorkMode.HYBRID),
        ("Vaga presencial em Curitiba.", WorkMode.ONSITE),
        ("Formato presencial integral.", WorkMode.ONSITE),
        ("This is an on-site role at our Lisbon HQ.", WorkMode.ONSITE),
    ],
)
def test_work_mode_v7_reads_description_phrases(description: str, expected: WorkMode) -> None:
    value, reason = content.classify_work_mode_v7("Engineer", "São Paulo", {}, description)
    assert value is expected
    assert reason["source"] == "description"
    assert reason["mapping_version"] == "work-mode-v7"
    assert reason["evidence"]


@pytest.mark.parametrize(
    "description",
    [
        "Partner with senior remote engineers across the globe.",
        "We are hiring for hybrid and remote roles across teams.",  # two modes: ambiguous
        "Great benefits and a modern office.",
    ],
)
def test_work_mode_v7_does_not_guess(description: str) -> None:
    value, reason = content.classify_work_mode_v7("Engineer", "São Paulo", {}, description)
    assert value is WorkMode.UNKNOWN
    assert reason["evidence"] is None


def test_work_mode_v7_title_wins_and_conflict_is_unknown() -> None:
    value, reason = content.classify_work_mode_v7(
        "Engineer (Remote)", "Anywhere", {}, "Vaga presencial em Curitiba."
    )
    assert value is WorkMode.UNKNOWN and reason["source"] == "conflict"
    value, reason = content.classify_work_mode_v7("Engineer (Remote)", None, {}, "Great benefits.")
    assert value is WorkMode.REMOTE and reason["source"] == "title"


@pytest.mark.parametrize(
    ("location", "description", "expected", "source"),
    [
        ("Remote — Brazil", "We are open to candidates in Portugal.", ("BR",), "location"),
        (None, "This role is remote within Brazil.", ("BR",), "description"),
        ("Remote", "You must be located in the United States.", ("US",), "description"),
        ("Remote", "Vaga remota. Residentes no Brasil.", ("BR",), "description"),
        ("Remoto", "Trabalho remoto no México para o time regional.", ("MX",), "description"),
        ("Remote", "Open to candidates based in LATAM.", LATAM_COUNTRIES, "description"),
        ("Remote", "Authorized to work in Canada is required.", ("CA",), "description"),
    ],
)
def test_allowed_countries_v2_uses_location_first_then_description_phrases(
    location: str | None,
    description: str,
    expected: tuple[str, ...],
    source: str,
) -> None:
    countries, evidence = resolve_allowed_countries_v2(location, description)
    assert countries == expected
    assert evidence is not None and evidence["source"] == source and evidence["evidence"]


@pytest.mark.parametrize(
    ("location", "description"),
    [
        ("Remote", "We have customers in Brazil and offices in Portugal."),  # bare names
        ("Remote", "Remote within Brazil, or you must be located in Portugal."),  # conflict
        (None, None),
        ("Remote", ""),
    ],
)
def test_allowed_countries_v2_stays_unknown(location: str | None, description: str | None) -> None:
    assert resolve_allowed_countries_v2(location, description) == ((), None)


def test_content_rules_are_off_by_default_and_versioned_when_on() -> None:
    item = _input(
        title="Data Engineer",
        location_text="Remote",
        description="3-5 years of experience. Trabalho remoto no Brasil.",
    )
    off = build_candidate(item)
    assert off.seniority is Seniority.UNKNOWN
    assert off.allowed_countries == ()
    assert off.allowed_countries_version == "regions-v1"
    assert off.classification_reasons == ()

    on = build_candidate(item, content_rules=True)
    assert on.seniority is Seniority.MID
    assert on.allowed_countries == ("BR",)
    assert on.allowed_countries_version == REGIONS_VERSION_V2 == "allowed-countries-v2"
    codes = {reason["code"]: reason for reason in on.classification_reasons}
    assert codes["SENIORITY_CLASSIFICATION"]["mapping_version"] == "seniority-v4"
    assert codes["WORK_MODE_CLASSIFICATION"]["mapping_version"] == "work-mode-v7"
    assert codes["ALLOWED_COUNTRIES_CLASSIFICATION"]["evidence"]


def test_precision_gate_fails_closed() -> None:
    assert content.gate_passes({"a": (9, 10), "b": (18, 20)}) is True
    assert content.gate_passes({"a": (9, 10), "b": (17, 20)}) is False  # 85%
    assert content.gate_passes({"a": (9, 10), "b": (0, 0)}) is False  # no evidence
    assert content.gate_passes({}) is False
