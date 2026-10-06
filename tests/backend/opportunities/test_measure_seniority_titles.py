"""Baseline of the title-only seniority classifier (card F52-01), no database needed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import measure_seniority_titles
from scripts.measure_seniority_titles import (
    baseline,
    build_label_sample,
    classify,
    main,
    measure_sample,
    unknown_pattern,
)

SAMPLE = Path("docs/pesquisas/f52-01-amostra-senioridade.json")
needs_sample = pytest.mark.skipif(not SAMPLE.exists(), reason="docs/ is not part of the test image")


def _rows(*titles: str) -> list[dict[str, str]]:
    return [
        {"opportunity_id": f"id-{index:03d}", "title": title, "company": "Acme"}
        for index, title in enumerate(titles)
    ]


@pytest.mark.parametrize(
    ("title", "pattern", "detail"),
    [
        ("Senior Staff Engineer - Enterprise Messaging", "two_levels", "SENIOR+STAFF"),
        ("Desenvolvedor(a) .NET PL/SR", "two_levels", "MID+SENIOR"),
        ("Software Engineer II", "numeral", None),
        ("Software Engineer I", "numeral", None),
        ("Engineer II/III, Automation", "numeral", None),
        ("Software Architect (AWS, NodeJS)", "uncovered_word", "architect"),
        ("Head of Engineering", "uncovered_word", "head of"),
        ("Associate Software Engineer", "uncovered_word", "associate"),
        ("Data Engineer - Finance", "no_signal", None),
        # A bare digit is a requisition id, not a level.
        ("Desk Side Engineer 6439365", "no_signal", None),
    ],
)
def test_unknown_pattern_names_the_first_reason(
    monkeypatch: pytest.MonkeyPatch, title: str, pattern: str, detail: str | None
) -> None:
    # The grouping explains a title the classifier left UNKNOWN; `seniority-v5` reads most
    # of these, so the classifier is replaced by one that reads nothing.
    monkeypatch.setattr(measure_seniority_titles, "classify", lambda title: "UNKNOWN")

    assert unknown_pattern(title) == (pattern, detail)


def test_accent_pattern_is_a_title_that_classifies_once_the_accent_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `seniority-v5` ignores accents, so the pattern is shown on a classifier that does not.
    monkeypatch.setattr(
        measure_seniority_titles,
        "classify",
        lambda title: "JUNIOR" if "junior" in title.casefold() else "UNKNOWN",
    )

    assert unknown_pattern("Analista de Dados Júnior") == ("accent", None)
    assert unknown_pattern("Engenharia de Dados") == ("no_signal", None)


def test_baseline_counts_levels_patterns_and_the_title_only_ceiling() -> None:
    report = baseline(
        _rows(
            "Senior Software Engineer",
            "Founding Engineer",
            "Software Engineer IV",
            "Data Engineer",
        )
    )

    assert report["titles"] == 4
    assert report["levels"] == {"SENIOR": 1, "UNKNOWN": 3}
    assert report["coverage"] == 0.25
    assert report["unknown"] == 3
    patterns = report["unknown_patterns"]
    assert {name: stats["titles"] for name, stats in patterns.items()} == {
        "accent": 0,
        "two_levels": 0,
        "numeral": 1,
        "uncovered_word": 1,
        "no_signal": 1,
    }
    assert patterns["uncovered_word"]["details"] == {"founding": 1}
    assert patterns["no_signal"]["examples"] == ["Data Engineer"]
    # Only the title with no level word stays out of reach of a title-only classifier.
    assert report["coverage_ceiling_title_only"] == 0.75


def test_baseline_of_no_titles_reports_zero_instead_of_dividing() -> None:
    report = baseline([])

    assert report["coverage"] == 0.0
    assert report["unknown_patterns"]["no_signal"]["share_of_unknown"] == 0.0


def test_label_sample_is_blind_stratified_and_repeatable() -> None:
    rows = _rows(
        *(f"Data Engineer {letter}" for letter in "abcdefgh"),
        *(f"Senior Engineer {letter}" for letter in "abcdefgh"),
        "Data Engineer a",  # same title twice: labelled once
    )

    sample = build_label_sample(rows, unknown_size=3, classified_size=2, seed=7)

    assert sample == build_label_sample(rows, unknown_size=3, classified_size=2, seed=7)
    assert len({entry["title"] for entry in sample}) == 5
    assert sum(classify(entry["title"]) == "UNKNOWN" for entry in sample) == 3
    for entry in sample:
        assert set(entry) == {"opportunity_id", "title", "company", "nivel_rotulado", "observacao"}
        assert entry["nivel_rotulado"] is None


def test_measure_sample_reports_precision_per_emitted_level() -> None:
    report = measure_sample(
        [
            {"title": "Senior Software Engineer", "nivel_rotulado": "SENIOR"},
            {"title": "Senior Account Engineer", "nivel_rotulado": "MID"},
            {"title": "Engineering Manager", "nivel_rotulado": "MANAGER"},
            # A range label: the emitted level is correct when it is one of the values.
            {"title": "Pleno Developer", "nivel_rotulado": ["MID", "SENIOR"]},
            {"title": "Software Engineer IV", "nivel_rotulado": "SENIOR"},
            {"title": "Data Engineer", "nivel_rotulado": "UNKNOWN"},
            {"title": "Staff Engineer", "nivel_rotulado": None},
        ]
    )

    assert report["entries"] == 7
    assert report["labelled"] == 6
    assert report["precision"] == 0.75
    assert report["precision_by_level"] == {
        "MANAGER": {"emitted": 1, "correct": 1, "precision": 1.0},
        "MID": {"emitted": 1, "correct": 1, "precision": 1.0},
        "SENIOR": {"emitted": 2, "correct": 1, "precision": 0.5},
    }
    assert report["unknown_by_pattern"] == {
        "no_signal": {"no_level": 1},
        "numeral": {"has_level": 1},
    }


def test_measure_sample_without_labels_reports_no_precision() -> None:
    report = measure_sample([{"title": "Senior Engineer", "nivel_rotulado": None}])

    assert report["labelled"] == 0
    assert report["precision"] is None
    assert report["precision_by_level"] == {}


def test_measure_sample_rejects_a_label_that_is_not_a_seniority() -> None:
    with pytest.raises(ValueError, match="invalid nivel_rotulado"):
        measure_sample([{"opportunity_id": "x", "title": "Engineer", "nivel_rotulado": "Sênior"}])


@needs_sample
def test_versioned_sample_has_the_card_strata_and_runs_offline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    entries = json.loads(SAMPLE.read_text(encoding="utf-8"))["casos"]

    assert len(entries) == 300
    assert len({entry["opportunity_id"] for entry in entries}) == 300
    assert main(["--sample", str(SAMPLE)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["entries"] == 300
    assert report["labelled"] <= 300
