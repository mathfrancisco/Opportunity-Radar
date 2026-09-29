"""Compare `scripts/eval_analysis.py` reports across model / effort variants (card F20-22).

    python scripts/benchmark_report.py \
        data/evals/2026-09-27-v1-openai_gpt-oss-120b-baseline-pinned.json \
        data/evals/2026-09-28-v1-openai_gpt-oss-20b.json \
        data/evals/2026-09-29-v1-qwen_qwen3.8-27b.json \
        --output docs/pesquisas/benchmark-modelos-groq.md

Reads report JSON files `scripts/eval_analysis.py` already wrote — never calls Groq, never
re-scores a case. Each file becomes one row: label accuracy (from the operator's filled
`human_review`, blank until then), valid-JSON rate, claims checked (fidelity), latency
p50/p95, and mean input/output tokens. The decision in `matching/benchmark.py` applies the
card's written-in-advance criterion once every row's rubric is filled; until then it says
so instead of guessing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from opportunity_radar.matching.benchmark import (
    Decision,
    VariantResult,
    decide,
    variant_from_report,
)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}" if abs(value) < 10 else f"{value:.0f}"
    return str(value)


def markdown_report(variants: list[VariantResult], decision: Decision) -> str:
    lines = [
        "# Benchmark de modelos — job_match (F20-22)",
        "",
        "| Variante | Split | Acerto de rótulo | JSON válido | Claims conferidos "
        "(fidelidade) | Latência p50 | Latência p95 | Tokens entrada | Tokens saída |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for variant in variants:
        lines.append(
            f"| {variant.label} | {variant.split} | {_fmt(variant.label_accuracy)} | "
            f"{_fmt(variant.valid_json_rate)} | {_fmt(variant.claims_checked)} | "
            f"{_fmt(variant.latency_p50_ms)} ms | {_fmt(variant.latency_p95_ms)} ms | "
            f"{_fmt(variant.prompt_tokens_mean)} | {_fmt(variant.output_tokens_mean)} |"
        )
    lines += [
        "",
        "## Decisão",
        "",
        f"- Decidido: {'sim' if decision.decided else 'não'}",
        f"- Motivo: {decision.reason}",
    ]
    if decision.chosen:
        lines.append(f"- Escolhido: {decision.chosen}")
    if decision.eligible:
        lines.append(f"- Elegíveis: {', '.join(decision.eligible)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path, help="report JSON files to compare")
    parser.add_argument("--split", choices=("all", "tuning", "reserved"), default="all")
    parser.add_argument("--accuracy-tolerance-pp", type=float, default=2.0)
    parser.add_argument("--min-valid-json-rate", type=float, default=0.98)
    parser.add_argument("--output", type=Path, help="write the markdown table here too")
    args = parser.parse_args(argv)

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    variants = [variant_from_report(report, split=args.split) for report in reports]
    decision = decide(
        variants,
        accuracy_tolerance_pp=args.accuracy_tolerance_pp,
        min_valid_json_rate=args.min_valid_json_rate,
    )
    text = markdown_report(variants, decision)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
