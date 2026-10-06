"""Per-rule activation of the content rules (card F50-02), no database needed."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from opportunity_radar.opportunities.content_classification import (
    ALWAYS_ON_RULES,
    CONTENT_RULE_NAMES,
    DESCRIPTION_RULES,
    GATED_RULE_MIN_EMISSIONS,
    GATED_RULES,
    PRECISION_GATE,
    failing_gated_rules,
)
from opportunity_radar.opportunities.domain import (
    CanonicalCandidate,
    NormalizationInput,
    build_candidate,
)
from opportunity_radar.platform.config import Settings
from scripts.measure_content_classification import (
    MIN_RULE_EMISSIONS,
    Case,
    build_cases,
    load_gold,
    measure,
)

VERSIONED_GOLD = Path("docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json")
needs_versioned_gold = pytest.mark.skipif(
    not VERSIONED_GOLD.exists(), reason="docs/ is not part of the test image"
)

DATABASE_URL = "postgresql+psycopg://u:p@localhost:5432/x_test"


def _candidate(
    title: str,
    location: str | None,
    description: str | None,
    *,
    content_rules: bool | frozenset[str] = False,
) -> CanonicalCandidate:
    return build_candidate(
        NormalizationInput(
            raw_item_id=uuid4(),
            source_definition_id=uuid4(),
            source_type="manual",
            external_id="external-1",
            title=title,
            company_name="Acme",
            location_text=location,
            description=description,
            published_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        ),
        content_rules=content_rules,
    )


def _settings(**values: Any) -> Settings:
    return Settings(database_url=DATABASE_URL, _env_file=None, **values)  # type: ignore[call-arg]


def _fields(candidate: CanonicalCandidate) -> tuple[str, str, tuple[str, ...], str]:
    return (
        candidate.seniority.value,
        candidate.work_mode.value,
        candidate.allowed_countries,
        candidate.allowed_countries_version,
    )


# One description per rule, each on a posting whose title and location say nothing.
_TITLE = "Backend Engineer"
_LOCATION = "São Paulo, SP"
RULE_FIXTURES: dict[str, tuple[str, str, str]] = {
    "seniority:description_years_range": (
        "Looking for 3-5 years of experience.",
        "seniority",
        "MID",
    ),
    "seniority:description_years_min": (
        "We need 5+ years of experience.",
        "seniority",
        "SENIOR",
    ),
    "seniority:description_entry_phrase": (
        "This is an entry-level position.",
        "seniority",
        "JUNIOR",
    ),
    "seniority:description_intern_phrase": (
        "Vaga de estágio em dados, cursando graduação.",
        "seniority",
        "INTERN",
    ),
    "work_mode:description_phrase": ("Regime híbrido, 3 dias.", "work_mode", "HYBRID"),
    "allowed_countries:description": (
        "Must be located in Brazil.",
        "allowed_countries",
        "BR",
    ),
}

# Literals pinned on the base commit (content rules off), before this card touched anything.
BASE_PINS: dict[str, tuple[tuple[str, str, str | None], tuple[str, str, tuple[str, ...], str]]] = {
    "years_min": (
        (_TITLE, _LOCATION, "We need 5+ years of experience building APIs."),
        ("UNKNOWN", "UNKNOWN", (), "regions-v1"),
    ),
    "years_range": (
        (_TITLE, _LOCATION, "Looking for 3-5 years of experience."),
        ("UNKNOWN", "UNKNOWN", (), "regions-v1"),
    ),
    "entry": (
        (_TITLE, _LOCATION, "This is an entry-level position."),
        ("UNKNOWN", "UNKNOWN", (), "regions-v1"),
    ),
    "intern": (
        (_TITLE, _LOCATION, "Vaga de estágio em dados, cursando graduação."),
        ("UNKNOWN", "UNKNOWN", (), "regions-v1"),
    ),
    "work_mode": (
        ("Data Engineer", _LOCATION, "Regime híbrido, 3 dias."),
        ("UNKNOWN", "UNKNOWN", (), "regions-v1"),
    ),
    "country": (
        ("Data Engineer", "Remote", "Trabalho remoto no Brasil."),
        ("UNKNOWN", "REMOTE", (), "regions-v1"),
    ),
    "all_three": (
        (
            _TITLE,
            _LOCATION,
            "5+ years of experience. Regime híbrido, 3 dias. Must be located in Brazil.",
        ),
        ("UNKNOWN", "UNKNOWN", (), "regions-v1"),
    ),
    "title_and_location": (
        ("Senior Data Engineer", "Remote — Brazil", None),
        ("SENIOR", "REMOTE", ("BR",), "regions-v1"),
    ),
}


@pytest.mark.parametrize("name", list(BASE_PINS))
def test_flag_off_and_empty_list_keep_the_base_output(name: str) -> None:
    (title, location, description), expected = BASE_PINS[name]
    default_settings = _settings()
    assert default_settings.content_rules == frozenset()
    for content_rules in (False, frozenset(), default_settings.content_rules):
        candidate = _candidate(title, location, description, content_rules=content_rules)
        assert _fields(candidate) == expected
        assert candidate.classification_reasons == ()


def test_only_years_min_enabled_changes_seniority_and_nothing_else() -> None:
    rules = frozenset({"seniority:description_years_min"})
    description = "5+ years of experience. Regime híbrido, 3 dias. Must be located in Brazil."
    candidate = _candidate(_TITLE, _LOCATION, description, content_rules=rules)

    assert _fields(candidate) == ("SENIOR", "UNKNOWN", (), "regions-v1")
    (reason,) = candidate.classification_reasons
    assert reason["code"] == "SENIORITY_CLASSIFICATION"
    assert reason["rule"] == "description_years_min"
    assert reason["mapping_version"] == "seniority-v4"
    assert reason["evidence"] and "5+ years of experience" in reason["evidence"]

    # The same posting with the work-mode and country phrases only yields nothing new.
    phrases_only = "Regime híbrido, 3 dias. Must be located in Brazil."
    assert _fields(_candidate(_TITLE, _LOCATION, phrases_only, content_rules=rules)) == (
        "UNKNOWN",
        "UNKNOWN",
        (),
        "regions-v1",
    )


def test_a_title_decided_value_keeps_the_title_mapping_version_under_partial_activation() -> None:
    candidate = _candidate(
        "Senior Data Engineer",
        "Remote — Brazil",
        "5+ years of experience. Regime híbrido, 3 dias.",
        content_rules=frozenset({"seniority:description_years_min"}),
    )
    assert candidate.seniority.value == "SENIOR"
    (reason,) = candidate.classification_reasons
    assert reason["source"] == "title"
    assert reason["mapping_version"] == "seniority-v6"
    assert candidate.allowed_countries_version == "regions-v1"


@pytest.mark.parametrize("rule", sorted(DESCRIPTION_RULES))
def test_each_rule_alone_affects_only_its_own_field(rule: str) -> None:
    description, field, expected = RULE_FIXTURES[rule]
    baseline = _candidate(_TITLE, _LOCATION, description)
    alone = _candidate(_TITLE, _LOCATION, description, content_rules=frozenset({rule}))
    others = _candidate(
        _TITLE, _LOCATION, description, content_rules=frozenset(DESCRIPTION_RULES - {rule})
    )

    values = {
        "seniority": (baseline.seniority.value, alone.seniority.value, others.seniority.value),
        "work_mode": (
            baseline.work_mode.value,
            alone.work_mode.value,
            others.work_mode.value,
        ),
        "allowed_countries": (
            ",".join(baseline.allowed_countries),
            ",".join(alone.allowed_countries),
            ",".join(others.allowed_countries),
        ),
    }
    for name, (before, with_rule, without_rule) in values.items():
        if name == field:
            assert with_rule == expected
            assert without_rule == before  # every other rule on, this one off: nothing
        else:
            assert with_rule == before
    if field == "allowed_countries":
        assert alone.allowed_countries_version == "allowed-countries-v2"
    else:
        assert alone.allowed_countries_version == baseline.allowed_countries_version


def test_always_on_names_are_accepted_and_change_nothing() -> None:
    settings = _settings(content_classification_enabled_rules=",".join(sorted(ALWAYS_ON_RULES)))
    rules = settings.content_rules
    assert isinstance(rules, frozenset) and rules == ALWAYS_ON_RULES
    for description, _, _ in RULE_FIXTURES.values():
        base = _candidate(_TITLE, _LOCATION, description)
        assert _fields(_candidate(_TITLE, _LOCATION, description, content_rules=rules)) == _fields(
            base
        )


def test_unknown_rule_name_fails_settings_validation_naming_it() -> None:
    with pytest.raises(ValidationError) as error:
        _settings(
            content_classification_enabled_rules="seniority:description_years_min,seniority:nope"
        )
    assert "seniority:nope" in str(error.value)
    assert "description_years_min'" not in str(error.value).split("valid names")[0]


def test_rule_list_is_parsed_with_whitespace_and_empty_items() -> None:
    settings = _settings(
        content_classification_enabled_rules=(
            " seniority:description_years_min , ,work_mode:description_phrase,"
        )
    )
    assert settings.content_rules == frozenset(
        {"seniority:description_years_min", "work_mode:description_phrase"}
    )


def test_old_boolean_still_enables_every_rule() -> None:
    settings = _settings(content_classification_v4_enabled=True)
    assert settings.content_rules is True
    # Naming rules as well changes nothing: the boolean means all.
    both = _settings(
        content_classification_v4_enabled=True,
        content_classification_enabled_rules="seniority:description_years_min",
    )
    assert both.content_rules is True

    candidate = _candidate(
        _TITLE,
        _LOCATION,
        "5+ years of experience. Regime híbrido, 3 dias. Must be located in Brazil.",
        content_rules=settings.content_rules,
    )
    assert _fields(candidate) == ("SENIOR", "HYBRID", ("BR",), "allowed-countries-v2")
    versions = {
        reason["code"]: reason["mapping_version"] for reason in candidate.classification_reasons
    }
    assert versions == {
        "SENIORITY_CLASSIFICATION": "seniority-v4",
        "WORK_MODE_CLASSIFICATION": "work-mode-v7",
        "ALLOWED_COUNTRIES_CLASSIFICATION": "allowed-countries-v2",
    }


def test_every_rule_is_reachable_from_the_fixtures() -> None:
    assert set(RULE_FIXTURES) == DESCRIPTION_RULES
    assert CONTENT_RULE_NAMES == DESCRIPTION_RULES | ALWAYS_ON_RULES


# --------------------------------------------------------------------- GATED_RULES regression


def _synthetic_cases(correct: int, wrong: int) -> list[Case]:
    cases = [
        Case(f"ok-{n}", "seniority", "SENIOR", "Engineer", "5+ years of experience", None)
        for n in range(correct)
    ]
    cases += [
        Case(f"bad-{n}", "seniority", "MID", "Engineer", "5+ years of experience", None)
        for n in range(wrong)
    ]
    return cases


def _precision(cases: list[Case]) -> dict[str, tuple[int, int]]:
    report = measure(cases, min_gold_jobs=1)
    return {rule: (r["correct"], r["emitted"]) for rule, r in report["rules"].items()}


def test_gate_constants_match_the_measurement_script() -> None:
    assert GATED_RULE_MIN_EMISSIONS == MIN_RULE_EMISSIONS == 20
    assert PRECISION_GATE == 0.90


def test_a_gated_rule_at_85_percent_fails_the_check() -> None:
    rule = "seniority:description_years_min"
    precision = _precision(_synthetic_cases(correct=17, wrong=3))
    assert precision[rule] == (17, 20)
    assert failing_gated_rules(precision, (rule,)) == [rule]
    # The same rule at 90% with enough emissions passes; with too few emissions it fails.
    assert failing_gated_rules(_precision(_synthetic_cases(18, 2)), (rule,)) == []
    assert failing_gated_rules(_precision(_synthetic_cases(19, 0)), (rule,)) == [rule]
    # A gated rule the gold never emitted has no evidence either.
    assert failing_gated_rules({}, (rule,)) == [rule]


def test_gated_rules_are_known_rule_names() -> None:
    assert set(GATED_RULES) <= CONTENT_RULE_NAMES


def test_default_setting_is_a_subset_of_the_gated_rules() -> None:
    settings = _settings()
    assert settings.content_classification_enabled_rules == ""
    assert settings.content_classification_v4_enabled is False
    assert settings.content_classification_rule_set <= set(GATED_RULES)


@needs_versioned_gold
def test_every_gated_rule_reaches_the_gate_on_the_versioned_gold() -> None:
    """Mechanism of the F50-02 gate: empty `GATED_RULES` passes; a listed rule must hold up."""
    cases = build_cases(load_gold(VERSIONED_GOLD), {}, gold_text=True)
    report = measure(cases)
    precision = {rule: (r["correct"], r["emitted"]) for rule, r in report["rules"].items()}
    assert failing_gated_rules(precision) == []
    # A rule that is declared safe is also one the measurement script can print.
    assert set(precision) <= CONTENT_RULE_NAMES
