"""Compares `scripts/eval_analysis.py` reports across model / reasoning-effort variants.

Card F20-22: choosing a model and `reasoning_effort` for `job_match` is a decision made
by measurement, not by opinion. Each variant (one model, one effort) is run offline with
`scripts/eval_analysis.py --model ... AI_REASONING_EFFORT=...` and produces one report
JSON. This module only reads those reports and tabulates them; it never calls Groq and
never re-scores a case — `matching/evaluation.py` already did that when the run happened.

Label accuracy is not automatic: `score_case` cannot judge whether the model's answer
agrees with the verdict, only an operator filling `human_review[case_id]["adherence"]`
can. `decide()` therefore refuses to pick a model until every variant's rubric is filled,
matching the card's rule that the criterion is written before the numbers exist and never
adjusted after seeing them.

Pure functions only; the CLI wrapper lives in `scripts/benchmark_report.py`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_SIZE = re.compile(r"(\d+(?:\.\d+)?)b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class VariantResult:
    label: str
    model: str
    reasoning_effort: str
    split: str
    cases_digest: str
    label_accuracy: float | None
    valid_json_rate: float | None
    claims_checked: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    prompt_tokens_mean: float | None
    output_tokens_mean: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "split": self.split,
            "cases_digest": self.cases_digest,
            "label_accuracy": self.label_accuracy,
            "valid_json_rate": self.valid_json_rate,
            "claims_checked": self.claims_checked,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p95_ms": self.latency_p95_ms,
            "prompt_tokens_mean": self.prompt_tokens_mean,
            "output_tokens_mean": self.output_tokens_mean,
        }


def percentile(values: Sequence[float], fraction: float) -> float | None:
    """Nearest-rank percentile; `None` for an empty sample. No interpolation, no numpy."""
    if not values:
        return None
    if not 0 <= fraction <= 1:
        raise ValueError(f"fraction must be between 0 and 1, got {fraction!r}")
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))
    return ordered[index]


def label_accuracy(human_review: Mapping[str, Mapping[str, Any]]) -> float | None:
    """Share of cases marked `adherence: 1`; `None` while any case is still unrated.

    An empty `human_review` (no cases ran) is also unrated, not perfect accuracy.
    """
    if not human_review:
        return None
    values = [item.get("adherence") for item in human_review.values()]
    if any(value is None for value in values):
        return None
    return sum(1 for value in values if value) / len(values)


def model_size_b(model: str) -> float | None:
    """Parameter count in billions parsed from a model name like `openai/gpt-oss-120b`."""
    match = _SIZE.search(model)
    return float(match.group(1)) if match else None


def variant_from_report(report: Mapping[str, Any], *, split: str = "all") -> VariantResult:
    """One row of the comparison table from one `eval_analysis.py` report JSON."""
    options = (report.get("inference") or {}).get("options") or {}
    summary_by_split = report.get("summary") or {}
    summary = summary_by_split.get(split, summary_by_split)
    cases = report.get("cases") or []
    latencies = [
        float(case["total_ms"])
        for case in cases
        if case.get("split", split) == split and case.get("total_ms") is not None
    ]
    model = str(report.get("model", "?"))
    effort = str(options.get("reasoning_effort", "?"))
    label = f"{model}@{effort}"
    if report.get("label"):
        label += f" ({report['label']})"
    return VariantResult(
        label=label,
        model=model,
        reasoning_effort=effort,
        split=split,
        cases_digest=str(report.get("cases_digest", "")),
        label_accuracy=label_accuracy(report.get("human_review") or {}),
        valid_json_rate=summary.get("completed_rate"),
        claims_checked=summary.get("fidelity"),
        latency_p50_ms=percentile(latencies, 0.50),
        latency_p95_ms=percentile(latencies, 0.95),
        prompt_tokens_mean=summary.get("prompt_tokens"),
        output_tokens_mean=summary.get("output_tokens"),
    )


@dataclass(frozen=True, slots=True)
class Decision:
    decided: bool
    reason: str
    chosen: str | None = None
    eligible: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "decided": self.decided,
            "reason": self.reason,
            "chosen": self.chosen,
            "eligible": list(self.eligible),
        }


def decide(
    variants: Sequence[VariantResult],
    *,
    accuracy_tolerance_pp: float = 2.0,
    min_valid_json_rate: float = 0.98,
) -> Decision:
    """Card F20-22 step 1's criterion: the smallest model within `accuracy_tolerance_pp`
    percentage points of the best label accuracy, with a valid-JSON rate at or above
    `min_valid_json_rate`. "Smallest" is the model's parameter count in `model_size_b`;
    a model whose name does not carry a size (so it cannot be compared) never wins ties
    over one that does.

    Every variant needs a filled `label_accuracy` — the rubric is a person's job, not
    this function's — otherwise the decision is pending, not guessed.
    """
    if not variants:
        return Decision(decided=False, reason="nenhuma variante informada")
    unrated = [v.label for v in variants if v.label_accuracy is None]
    if unrated:
        return Decision(
            decided=False,
            reason=f"rubrica humana pendente em: {', '.join(unrated)}",
        )
    best_accuracy = max(v.label_accuracy for v in variants if v.label_accuracy is not None)
    eligible = [
        v
        for v in variants
        if v.label_accuracy is not None
        and (best_accuracy - v.label_accuracy) * 100 <= accuracy_tolerance_pp
        and v.valid_json_rate is not None
        and v.valid_json_rate >= min_valid_json_rate
    ]
    if not eligible:
        return Decision(
            decided=False,
            reason=(
                f"nenhuma variante fica a até {accuracy_tolerance_pp} p.p. do melhor "
                f"acerto de rótulo ({best_accuracy * 100:.1f}%) com JSON válido >= "
                f"{min_valid_json_rate * 100:.0f}%"
            ),
        )

    def sort_key(variant: VariantResult) -> tuple[float, float]:
        size = model_size_b(variant.model)
        # Unknown size sorts after every known one, so it is never picked over a model
        # the benchmark can actually compare by size; latency breaks a tie.
        size_key = size if size is not None else float("inf")
        latency_key = variant.latency_p95_ms if variant.latency_p95_ms is not None else float("inf")
        return (size_key, latency_key)

    chosen = min(eligible, key=sort_key)
    return Decision(
        decided=True,
        reason="menor modelo dentro da tolerância com JSON válido suficiente",
        chosen=chosen.label,
        eligible=tuple(v.label for v in eligible),
    )


__all__ = [
    "Decision",
    "VariantResult",
    "decide",
    "label_accuracy",
    "model_size_b",
    "percentile",
    "variant_from_report",
]
