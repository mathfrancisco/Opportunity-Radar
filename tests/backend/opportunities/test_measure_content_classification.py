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


def _case(field: str, expected: str | None, description: str, *, title: str = "Engineer") -> Case:
    return Case(
        opportunity_id=f"{field}-{expected}-{description}",
        field=field,
        expected=expected,
        title=title,
        description=description,
        location_text=None,
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
    assert len(first) == 20  # one entry per (opportunity, field)
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
