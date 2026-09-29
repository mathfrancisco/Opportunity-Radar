"""Tests for matching/benchmark.py (card F20-22): pure functions over report JSON, no I/O."""

from __future__ import annotations

import pytest

from opportunity_radar.matching.benchmark import (
    VariantResult,
    decide,
    label_accuracy,
    model_size_b,
    percentile,
    variant_from_report,
)


def _report(
    *,
    model: str = "openai/gpt-oss-120b",
    effort: str = "low",
    label: str | None = None,
    completed_rate: float = 1.0,
    fidelity: float | None = 0.9,
    prompt_tokens: float = 1000.0,
    output_tokens: float = 400.0,
    latencies: tuple[int, ...] = (100, 200, 300, 400, 500),
    adherence: dict[str, int | None] | None = None,
    cases_digest: str = "abc123",
) -> dict:
    cases = [
        {"case_id": f"case-{index}", "split": "all", "total_ms": ms}
        for index, ms in enumerate(latencies)
    ]
    human_review = (
        {case_id: {"adherence": value, "support": None} for case_id, value in adherence.items()}
        if adherence is not None
        else {case["case_id"]: {"adherence": None, "support": None} for case in cases}
    )
    return {
        "model": model,
        "label": label,
        "cases_digest": cases_digest,
        "inference": {"options": {"reasoning_effort": effort}},
        "summary": {
            "all": {
                "completed_rate": completed_rate,
                "fidelity": fidelity,
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
            }
        },
        "cases": cases,
        "human_review": human_review,
    }


# --- percentile -----------------------------------------------------------------------


def test_percentile_empty_is_none() -> None:
    assert percentile([], 0.5) is None


def test_percentile_p50_and_p95() -> None:
    values = [float(v) for v in range(1, 11)]  # 1..10; nearest-rank, index = round(f*(n-1))

    assert percentile(values, 0.5) == 5.0  # round(0.5 * 9) = 4 -> ordered[4]
    assert percentile(values, 0.95) == 10.0  # round(0.95 * 9) = 9 -> ordered[9]


def test_percentile_rejects_out_of_range_fraction() -> None:
    with pytest.raises(ValueError, match="fraction"):
        percentile([1.0], 1.5)


# --- label_accuracy ---------------------------------------------------------------------


def test_label_accuracy_none_when_empty() -> None:
    assert label_accuracy({}) is None


def test_label_accuracy_none_when_any_case_unrated() -> None:
    review = {"a": {"adherence": 1}, "b": {"adherence": None}}

    assert label_accuracy(review) is None


def test_label_accuracy_computed_when_fully_rated() -> None:
    review = {"a": {"adherence": 1}, "b": {"adherence": 0}, "c": {"adherence": 1}}

    assert label_accuracy(review) == pytest.approx(2 / 3)


# --- model_size_b -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "size"),
    [
        ("openai/gpt-oss-120b", 120.0),
        ("openai/gpt-oss-20b", 20.0),
        ("qwen/qwen3.8-27b", 27.0),
        ("unnamed-model", None),
    ],
)
def test_model_size_b(model: str, size: float | None) -> None:
    assert model_size_b(model) == size


# --- variant_from_report ------------------------------------------------------------


def test_variant_from_report_reads_summary_and_percentiles() -> None:
    report = _report(latencies=(100, 200, 300, 400, 500))

    variant = variant_from_report(report, split="all")

    assert variant.model == "openai/gpt-oss-120b"
    assert variant.reasoning_effort == "low"
    assert variant.label == "openai/gpt-oss-120b@low"
    assert variant.valid_json_rate == 1.0
    assert variant.claims_checked == 0.9
    assert variant.latency_p50_ms == 300
    assert variant.latency_p95_ms == 500
    assert variant.prompt_tokens_mean == 1000.0
    assert variant.output_tokens_mean == 400.0
    assert variant.cases_digest == "abc123"
    # Every case is unrated by default: no human_review filled yet.
    assert variant.label_accuracy is None


def test_variant_from_report_includes_label_in_display_name() -> None:
    report = _report(label="baseline-pinned")

    variant = variant_from_report(report)

    assert variant.label == "openai/gpt-oss-120b@low (baseline-pinned)"


def test_variant_from_report_missing_fields_are_none_not_estimated() -> None:
    variant = variant_from_report({})

    assert variant.model == "?"
    assert variant.reasoning_effort == "?"
    assert variant.valid_json_rate is None
    assert variant.claims_checked is None
    assert variant.latency_p50_ms is None
    assert variant.latency_p95_ms is None


# --- decide ---------------------------------------------------------------------------


def _variant(**overrides: object) -> VariantResult:
    base = dict(
        label="m",
        model="openai/gpt-oss-120b",
        reasoning_effort="low",
        split="all",
        cases_digest="d",
        label_accuracy=0.9,
        valid_json_rate=1.0,
        claims_checked=0.8,
        latency_p50_ms=200.0,
        latency_p95_ms=400.0,
        prompt_tokens_mean=1000.0,
        output_tokens_mean=400.0,
    )
    base.update(overrides)
    return VariantResult(**base)  # type: ignore[arg-type]


def test_decide_empty_variants() -> None:
    decision = decide([])

    assert decision.decided is False
    assert "nenhuma variante" in decision.reason


def test_decide_pending_when_any_variant_unrated() -> None:
    variants = [_variant(label="a", label_accuracy=0.9), _variant(label="b", label_accuracy=None)]

    decision = decide(variants)

    assert decision.decided is False
    assert "rubrica humana pendente" in decision.reason
    assert "b" in decision.reason


def test_decide_rejects_variant_below_json_validity_floor() -> None:
    variants = [
        _variant(
            label="120b", model="openai/gpt-oss-120b", label_accuracy=0.90, valid_json_rate=1.0
        ),
        _variant(
            label="20b", model="openai/gpt-oss-20b", label_accuracy=0.89, valid_json_rate=0.90
        ),
    ]

    decision = decide(variants, min_valid_json_rate=0.98)

    assert decision.decided is True
    assert decision.chosen == "120b"
    assert decision.eligible == ("120b",)


def test_decide_rejects_variant_outside_accuracy_tolerance() -> None:
    variants = [
        _variant(label="120b", model="openai/gpt-oss-120b", label_accuracy=0.95),
        _variant(label="20b", model="openai/gpt-oss-20b", label_accuracy=0.80),
    ]

    decision = decide(variants, accuracy_tolerance_pp=2.0)

    assert decision.decided is True
    assert decision.chosen == "120b"


def test_decide_picks_smallest_model_among_eligible() -> None:
    variants = [
        _variant(label="120b", model="openai/gpt-oss-120b", label_accuracy=0.95),
        _variant(label="20b", model="openai/gpt-oss-20b", label_accuracy=0.94),
        _variant(label="qwen-27b", model="qwen/qwen3.8-27b", label_accuracy=0.94),
    ]

    decision = decide(variants, accuracy_tolerance_pp=2.0)

    assert decision.decided is True
    assert decision.chosen == "20b"
    assert set(decision.eligible) == {"120b", "20b", "qwen-27b"}


def test_decide_no_eligible_variant() -> None:
    # Both variants are within tolerance of each other but neither meets the JSON floor,
    # so nothing is eligible even though a decision is technically comparable.
    variants = [
        _variant(
            label="120b", model="openai/gpt-oss-120b", label_accuracy=0.95, valid_json_rate=0.80
        ),
        _variant(
            label="20b", model="openai/gpt-oss-20b", label_accuracy=0.94, valid_json_rate=0.85
        ),
    ]

    decision = decide(variants, accuracy_tolerance_pp=2.0, min_valid_json_rate=0.98)

    assert decision.decided is False
    assert "nenhuma variante" in decision.reason


def test_decide_unknown_size_never_wins_tie_over_known_size() -> None:
    variants = [
        _variant(label="mystery", model="mystery-model", label_accuracy=0.95, latency_p95_ms=1.0),
        _variant(
            label="20b", model="openai/gpt-oss-20b", label_accuracy=0.95, latency_p95_ms=9999.0
        ),
    ]

    decision = decide(variants, accuracy_tolerance_pp=2.0)

    assert decision.chosen == "20b"


def test_decide_ties_on_size_break_by_latency() -> None:
    variants = [
        _variant(
            label="fast", model="openai/gpt-oss-20b", label_accuracy=0.95, latency_p95_ms=100.0
        ),
        _variant(
            label="slow", model="openai/gpt-oss-20b", label_accuracy=0.95, latency_p95_ms=900.0
        ),
    ]

    decision = decide(variants, accuracy_tolerance_pp=2.0)

    assert decision.chosen == "fast"
