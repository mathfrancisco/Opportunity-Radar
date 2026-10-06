"""Precision measurement of the content rules (card F48-15), no database needed."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.measure_content_classification import (
    Case,
    build_cases,
    build_label_sample,
    classify,
    evaluate_candidate_gate,
    load_gold,
    main,
    measure,
    passing_rules,
    unknown_rates,
)

GOLD = Path("docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json")
needs_gold = pytest.mark.skipif(not GOLD.exists(), reason="docs/ is not part of the test image")


VERSIONED_GOLD = Path("docs/50-roadmap-motor-de-busca/rotulagem/f50-01-gold.json")
needs_versioned_gold = pytest.mark.skipif(
    not VERSIONED_GOLD.exists(), reason="docs/ is not part of the test image"
)


def _case(
    field: str,
    expected: str | None,
    description: str,
    *,
    title: str = "Engineer",
    source_type: str | None = None,
    location_text: str | None = None,
) -> Case:
    return Case(
        opportunity_id=f"{field}-{expected}-{description}",
        field=field,
        expected=expected,
        title=title,
        description=description,
        location_text=location_text,
        source_type=source_type,
    )


def test_classify_returns_value_and_rule_or_none() -> None:
    assert classify(_case("seniority", "MID", "3-5 years of experience")) == (
        "MID",
        "description_years_range",
    )
    assert classify(_case("seniority", None, "Nothing useful")) == (None, None)
    assert classify(_case("work_mode", "HYBRID", "Regime híbrido, 3 dias.")) == (
        "HYBRID",
        "description_phrase",
    )
    assert classify(_case("seniority", "JUNIOR", "x", title="Junior Engineer")) == (
        "JUNIOR",
        "title",
    )


def test_measure_reports_precision_per_rule_and_unknown_rates() -> None:
    cases = [
        _case("seniority", "MID", "3-5 years of experience"),  # correct
        _case("seniority", "MID", "3 to 5 years of experience with Go"),  # correct
        _case("seniority", "SENIOR", "3-5 years of experience in sales"),  # wrong
        _case("seniority", None, "5+ years of experience"),  # false positive: expected UNKNOWN
        _case("seniority", "JUNIOR", "Nothing useful"),  # not emitted -> stays UNKNOWN
        _case("work_mode", "HYBRID", "Regime híbrido, 3 dias."),  # correct
    ]
    report = measure(cases, min_gold_jobs=1)
    years = report["rules"]["seniority:description_years_range"]
    assert (years["emitted"], years["correct"]) == (3, 2)
    assert years["precision"] == round(2 / 3, 4)
    minimum = report["rules"]["seniority:description_years_min"]
    assert (minimum["emitted"], minimum["correct"], minimum["precision"]) == (1, 0, 0.0)
    assert report["rules"]["work_mode:description_phrase"]["precision"] == 1.0
    seniority = report["fields"]["seniority"]
    assert seniority["cases"] == 5
    assert seniority["unknown_before"] == 5  # every gold case starts UNKNOWN
    assert seniority["unknown_after"] == 1
    assert report["gate"]["passes"] is False


def test_legacy_gold_cannot_pass_gate_even_when_precision_looks_high() -> None:
    cases = [_case("seniority", "MID", f"3-5 years of experience {i}") for i in range(9)]
    cases.append(_case("seniority", "SENIOR", "3-5 years of experience 9"))
    assert measure(cases, min_gold_jobs=1)["gate"]["passes"] is False
    assert measure([], min_gold_jobs=1)["gate"]["passes"] is False  # no evidence
    assert measure(cases)["gate"]["min_gold_jobs"] == 200


def test_rule_gate_is_independent_and_requires_minimum_support() -> None:
    rules = {
        "A": {"emitted": 20, "precision": 0.89},
        "B": {"emitted": 20, "precision": 0.90},
        "C": {"emitted": 19, "precision": 1.0},
    }
    assert passing_rules(rules) == ["B"]


@needs_gold
def test_gold_loader_reads_the_f20_23_labels_and_skips_role_family() -> None:
    gold = load_gold(GOLD)
    assert {item["field"] for item in gold} == {"seniority", "work_mode"}
    assert len(gold) == 37
    assert sum(item["expected"] is None for item in gold) == 9  # "manter UNKNOWN"


@needs_gold
def test_gold_without_description_text_can_use_the_evidence_quote_as_proxy() -> None:
    gold = load_gold(GOLD)
    cases = build_cases(gold, texts={}, evidence_as_text=True)
    assert len(cases) == len(gold)
    assert all(case.description for case in cases)
    assert measure(cases)["fields"]["seniority"]["cases"] == 24


def test_unknown_rates_before_and_after_on_rows_with_description() -> None:
    rows = [
        {"title": "Engineer", "description": "3-5 years of experience", "location_text": None},
        {"title": "Engineer", "description": "Nothing here", "location_text": None},
        {"title": "Junior Engineer", "description": "x", "location_text": None},
        {"title": "Engineer", "description": None, "location_text": None},  # ignored
    ]
    rates = unknown_rates(rows)
    assert rates["seniority"] == {
        "rows": 3,
        "unknown_before": 2,
        "unknown_after": 1,
        "rate_before": round(2 / 3, 4),
        "rate_after": round(1 / 3, 4),
    }


def test_label_sample_is_unlabelled_deterministic_and_blind() -> None:
    rows = [
        {
            "opportunity_id": f"id-{i}",
            "title": "Engineer",
            "company": "Acme",
            "description": "3-5 years of experience. " + "x" * 2000,
            "location_text": "Remote",
            "seniority": "UNKNOWN",
            "work_mode": "UNKNOWN",
        }
        for i in range(30)
    ]
    first = build_label_sample(rows, size=10, seed=7)
    assert first == build_label_sample(rows, size=10, seed=7)
    assert len(first) == 30  # one entry per (opportunity, field)
    for item in first:
        assert item["valor_recomendado"] is None and item["recomendacao"] is None
        assert "proposta_v4" not in item  # labeller must not see the rule's answer
        assert len(item["trecho_descricao"]) <= 1200


@needs_gold
def test_main_offline_evidence_mode_prints_report_and_gate_exit_code(
    capsys: object, tmp_path: Path
) -> None:
    exit_code = main(
        [
            "--gold",
            str(GOLD),
            "--evidence-as-text",
            "--check-gate",
            "--candidate-rule",
            "seniority:description_years_range",
        ]
    )
    out = capsys.readouterr().out  # type: ignore[attr-defined]
    report = json.loads(out)
    assert report["gate"]["threshold"] == 0.9
    assert exit_code == (0 if report["gate"]["passes"] else 1)
    assert report["mode"] == "evidence-as-text (proxy, not the real description)"


def test_measure_reports_precision_and_coverage_per_source_type() -> None:
    cases = [
        _case("seniority", "MID", "3-5 years of experience a", source_type="greenhouse"),
        _case("seniority", "MID", "3-5 years of experience b", source_type="greenhouse"),
        _case("seniority", "SENIOR", "3-5 years of experience c", source_type="greenhouse"),
        _case("seniority", "JUNIOR", "Nothing useful", source_type="greenhouse"),
        _case("seniority", "MID", "3-5 years of experience d", source_type="lever"),
        _case("seniority", "JUNIOR", "Nothing useful too", source_type="lever"),
    ]
    report = measure(cases, min_gold_jobs=1)
    greenhouse = report["by_source_type"]["greenhouse"]
    rule = greenhouse["rules"]["seniority:description_years_range"]
    assert (rule["emitted"], rule["correct"], rule["precision"]) == (3, 2, round(2 / 3, 4))
    assert greenhouse["fields"]["seniority"]["cases"] == 4
    assert greenhouse["fields"]["seniority"]["coverage"] == 0.75  # (4 - 1) / 4
    lever = report["by_source_type"]["lever"]
    assert lever["rules"]["seniority:description_years_range"]["precision"] == 1.0
    assert lever["fields"]["seniority"]["coverage"] == 0.5
    assert report["fields"]["seniority"]["coverage"] == round(4 / 6, 4)


def test_case_without_source_type_is_grouped_as_unknown() -> None:
    report = measure([_case("seniority", "MID", "3-5 years of experience")], min_gold_jobs=1)
    assert list(report["by_source_type"]) == []
    assert report["unassigned_source_type_cases"] == 1


def test_unknown_judgment_is_excluded_from_precision_and_legacy_gold_blocks_gate() -> None:
    applicable = _case("seniority", "MID", "3-5 years of experience", source_type="greenhouse")
    unknown = _case("seniority", "MID", "3-5 years of experience", source_type="greenhouse")
    unknown = replace(unknown, opportunity_id="unknown-id", judgment="unknown")
    report = measure([applicable, unknown], min_gold_jobs=1)
    assert report["judgments"]["unknown"] == 1
    assert report["rules"]["seniority:description_years_range"]["emitted"] == 1
    assert report["gate"]["passes"] is False
    assert report["gate"]["population_passes"] is False


def test_selected_rule_gate_is_explicit_and_applies_to_every_selected_rule() -> None:
    rules = {
        "seniority:description_years_min": {"emitted": 20, "precision": 0.89},
        "seniority:description_years_range": {"emitted": 20, "precision": 0.90},
        "seniority:description_entry_phrase": {"emitted": 19, "precision": 1.0},
    }
    assert evaluate_candidate_gate(True, rules, ())["passes"] is False
    assert evaluate_candidate_gate(True, rules, ["seniority:description_years_range"])["passes"]
    assert not evaluate_candidate_gate(
        True,
        rules,
        ["seniority:description_years_min", "seniority:description_years_range"],
    )["passes"]
    assert not evaluate_candidate_gate(True, rules, ["seniority:description_entry_phrase"])[
        "passes"
    ]


def test_inapplicable_emission_is_false_positive() -> None:
    case = _case("seniority", None, "3-5 years of experience", source_type="greenhouse")
    case = replace(case, judgment="inapplicable")
    report = measure([case], min_gold_jobs=1)
    assert (
        report["excluded_emissions_by_rule"]["seniority:description_years_range"]["inapplicable"]
        == 1
    )
    assert "seniority:description_years_range" not in report["rules"]


def test_gold_rejects_duplicate_opportunity_field(tmp_path: Path) -> None:
    gold = _write_gold(
        tmp_path / "duplicate.json",
        [
            {"opportunity_id": "a", "field": "seniority", "valor_recomendado": "MID"},
            {"opportunity_id": "a", "field": "seniority", "valor_recomendado": "SENIOR"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate gold case"):
        load_gold(gold)


def test_allowed_countries_is_measured() -> None:
    case = _case("allowed_countries", "BR", "This role is open to candidates based in Brazil.")
    value, rule = classify(case)
    assert value == "BR"
    assert rule == "description"
    report = measure([case], min_gold_jobs=1)
    assert report["rules"]["allowed_countries:description"]["correct"] == 1
    assert report["fields"]["allowed_countries"]["coverage"] == 1.0
    assert classify(_case("allowed_countries", None, "Nothing about countries.")) == (None, None)


def _write_gold(path: Path, entries: list[dict[str, object]]) -> Path:
    path.write_text(json.dumps({"casos": entries}), encoding="utf-8")
    return path


def test_gold_text_mode_needs_no_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gold = _write_gold(
        tmp_path / "gold.json",
        [
            {
                "opportunity_id": "a",
                "field": "seniority",
                "valor_recomendado": "MID",
                "title": "Engineer",
                "trecho_descricao": "3-5 years of experience",
                "source_type": "greenhouse",
            }
        ],
    )
    assert main(["--gold", str(gold), "--gold-text"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "gold embedded text"
    assert report["by_source_type"]["greenhouse"]["fields"]["seniority"]["cases"] == 1
    assert report["unmeasurable"] == []


def test_case_without_embedded_text_is_counted_as_unmeasurable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    gold = _write_gold(
        tmp_path / "gold.json",
        [
            {"opportunity_id": "no-text", "field": "work_mode", "valor_recomendado": "REMOTE"},
            {
                "opportunity_id": "with-text",
                "field": "work_mode",
                "valor_recomendado": "HYBRID",
                "trecho_descricao": "Regime híbrido, 3 dias.",
            },
        ],
    )
    assert main(["--gold", str(gold), "--gold-text"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["unmeasurable"] == [{"opportunity_id": "no-text", "field": "work_mode"}]
    assert report["fields"]["work_mode"]["cases"] == 1


def test_stratified_sample_takes_n_per_source_type() -> None:
    rows = [
        {
            "opportunity_id": f"{source_type}-{i}",
            "title": "Engineer",
            "company": "Acme",
            "description": "Some description",
            "location_text": "Remote",
            "source_type": source_type,
        }
        for source_type in ("greenhouse", "lever", "ashby")
        for i in range(5)
    ]
    sample = build_label_sample(rows, size=999, seed=3, per_source_type=2)
    per_type: dict[str, set[str]] = {}
    for item in sample:
        per_type.setdefault(item["source_type"], set()).add(item["opportunity_id"])
        assert item["valor_recomendado"] is None
    assert {name: len(ids) for name, ids in per_type.items()} == {
        "greenhouse": 2,
        "lever": 2,
        "ashby": 2,
    }


def test_rules_passing_requires_precision_and_volume() -> None:
    few = [_case("seniority", "MID", f"3-5 years of experience {i}") for i in range(19)]
    assert measure(few, min_gold_jobs=1)["gate"]["rules_passing"] == []
    enough = [_case("seniority", "MID", f"3-5 years of experience {i}") for i in range(18)]
    enough += [_case("seniority", "SENIOR", f"3-5 years of experience w{i}") for i in range(2)]
    assert measure(enough, min_gold_jobs=1)["gate"]["rules_passing"] == [
        "seniority:description_years_range"
    ]
    worse = [*enough, _case("seniority", "SENIOR", "3-5 years of experience z")]
    assert measure(worse, min_gold_jobs=1)["gate"]["rules_passing"] == []


@needs_versioned_gold
def test_versioned_gold_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["--gold", str(VERSIONED_GOLD), "--gold-text"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["gold_cases"] == 37
    assert report["unmeasurable"] == []


def test_gold_loader_reads_only_the_cases_a_person_confirmed(tmp_path: Path) -> None:
    # A proposal file: suggestions for every case, a label only where `revisado_por` is set.
    proposal = _write_gold(
        tmp_path / "proposta.json",
        [
            {
                "opportunity_id": "confirmed",
                "field": "seniority",
                "valor_sugerido": "MID",
                "judgment": "applicable",
                "valor_recomendado": "MID",
                "revisado_por": "owner",
            },
            {
                "opportunity_id": "suggested-only",
                "field": "seniority",
                "valor_sugerido": "SENIOR",
                "judgment": None,
                "valor_recomendado": None,
                "revisado_por": None,
            },
            {
                "opportunity_id": "unsigned",
                "field": "seniority",
                "judgment": "applicable",
                "valor_recomendado": "SENIOR",
                "revisado_por": " ",
            },
        ],
    )

    assert [item["opportunity_id"] for item in load_gold(proposal)] == ["confirmed"]


def test_gold_loader_reads_a_signed_suggestion_as_the_label(tmp_path: Path) -> None:
    # Signing a case without writing `judgment` approves the suggestion as written.
    empty = {"judgment": None, "valor_recomendado": None}
    proposal = _write_gold(
        tmp_path / "proposta.json",
        [
            {
                "opportunity_id": "approved",
                "field": "seniority",
                "julgamento_sugerido": "applicable",
                "valor_sugerido": "MID",
                **empty,
                "revisado_por": "owner",
            },
            {
                "opportunity_id": "approved-inapplicable",
                "field": "allowed_countries",
                "julgamento_sugerido": "inapplicable",
                "valor_sugerido": None,
                **empty,
                "revisado_por": "owner",
            },
            {
                "opportunity_id": "own-label",
                "field": "seniority",
                "julgamento_sugerido": "applicable",
                "valor_sugerido": "SENIOR",
                "judgment": "applicable",
                "valor_recomendado": "UNKNOWN",
                "revisado_por": "owner",
            },
            {
                "opportunity_id": "unsigned",
                "field": "seniority",
                "julgamento_sugerido": "applicable",
                "valor_sugerido": "SENIOR",
                **empty,
                "revisado_por": None,
            },
        ],
    )

    assert [
        (item["opportunity_id"], item["judgment"], item["expected"]) for item in load_gold(proposal)
    ] == [
        ("approved", "applicable", "MID"),
        ("approved-inapplicable", "inapplicable", None),
        ("own-label", "applicable", "UNKNOWN"),
    ]


def test_a_confirmed_unknown_makes_an_emission_wrong_and_silence_right() -> None:
    emitted = _case("seniority", "UNKNOWN", "3-5 years of experience", source_type="greenhouse")
    emitted = replace(emitted, judgment="applicable")
    silent = _case("seniority", "UNKNOWN", "A friendly team.", source_type="greenhouse")
    silent = replace(silent, judgment="applicable")

    report = measure([emitted, silent], min_gold_jobs=1)

    assert report["rules"]["seniority:description_years_range"] == {
        **report["rules"]["seniority:description_years_range"],
        "emitted": 1,
        "precision": 0.0,
    }
    assert report["confusion_by_rule"] == {
        "seniority:description_years_range": {"tp": 0, "fp": 1, "fn": 0, "support": 1}
    }
