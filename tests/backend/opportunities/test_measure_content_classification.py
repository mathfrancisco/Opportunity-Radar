"""Precision measurement of the content rules (card F48-15), no database needed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.measure_content_classification import (
    Case,
    build_cases,
    build_label_sample,
    classify,
    load_gold,
    main,
    measure,
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


def test_gate_passes_only_when_every_rule_reaches_ninety_percent() -> None:
    cases = [_case("seniority", "MID", f"3-5 years of experience {i}") for i in range(9)]
    cases.append(_case("seniority", "SENIOR", "3-5 years of experience 9"))
    assert measure(cases, min_gold_jobs=1)["gate"]["passes"] is True  # 9/10
    cases.append(_case("seniority", "SENIOR", "3-5 years of experience 10"))
    assert measure(cases, min_gold_jobs=1)["gate"]["passes"] is False  # 9/11
    assert measure([], min_gold_jobs=1)["gate"]["passes"] is False  # no evidence
    # perfect precision on too small a gold set still does not pass (>= 200 jobs)
    ok = cases[:9]
    assert measure(ok, min_gold_jobs=1)["gate"]["passes"] is True
    assert measure(ok)["gate"]["passes"] is False
    assert measure(ok)["gate"]["min_gold_jobs"] == 200


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
    exit_code = main(["--gold", str(GOLD), "--evidence-as-text", "--check-gate"])
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
    assert list(report["by_source_type"]) == ["unknown"]


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
