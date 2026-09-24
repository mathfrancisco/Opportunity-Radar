"""Run the evaluation set against the local model and compare it with a baseline.

    python scripts/eval_analysis.py --prompt v1 --model qwen3:8b-q4_K_M
    python scripts/eval_analysis.py --prompt v1 --model qwen3:8b-q4_K_M \
        --baseline data/evals/2026-09-24-v1-llama3.2_3b.json

Card F16-06. Uses the production adapter with the production `Settings`, so it measures
what will actually run. Each case runs once: the fixed `seed` makes two runs of the same
pair comparable. Writes `data/evals/<date>-<prompt>-<model>.json` and `.md`. The verdict
adherence column is left blank for the operator; no model judges another.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opportunity_radar.matching.analysis import AnalysisPolicy
from opportunity_radar.matching.evaluation import (
    CRITERIA,
    CaseScore,
    EvalCase,
    compare,
    load_cases,
    missing_kinds,
    score_case,
    summarize,
)
from opportunity_radar.matching.ollama import OllamaAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt, prompts_root
from opportunity_radar.platform.config import Settings

CASES_DIR = prompts_root() / "opportunity_analysis" / "eval" / "cases"
OUTPUT_DIR = Path("data/evals")


def _adapter(settings: Settings, *, prompt: str, model: str) -> OllamaAnalysisAdapter:
    return OllamaAnalysisAdapter(
        base_url=settings.ollama_base_url,
        model=model,
        prompt=load_prompt(prompt),
        timeout_seconds=settings.ollama_analysis_timeout_seconds,
        connect_timeout_seconds=settings.ollama_analysis_connect_timeout_seconds,
        max_retries=settings.ollama_analysis_max_retries,
        retry_after_seconds=settings.ollama_analysis_retry_after_seconds,
        # Every case must reach the model, whatever the production policy would skip,
        # and no answer may come from the in-memory cache of a previous case.
        policy=AnalysisPolicy(skip_verdicts=frozenset(), skip_ineligible=False),
        cache_max_entries=0,
        num_ctx=settings.ollama_num_ctx,
        num_predict=settings.ollama_num_predict,
        seed=settings.ollama_seed,
        keep_alive=settings.ollama_keep_alive,
        think=settings.ollama_think,
    )


async def _run(adapter: OllamaAnalysisAdapter, cases: list[EvalCase]) -> list[CaseScore]:
    await adapter.warm_up()
    scores = []
    for case in cases:
        outcome = await adapter.analyze(case.request())
        scores.append(score_case(case, outcome))
        print(f"{case.case_id}: {outcome.status.value}", flush=True)
    return scores


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}" if value < 10 else f"{value:.0f}"
    return str(value)


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Avaliação da análise — {report['prompt']} × {report['model']}",
        "",
        f"Rodada em {report['ran_at']}, {len(report['cases'])} casos.",
        "",
        "| Critério | Atual | Baseline | Comparação |",
        "| --- | ---: | ---: | --- |",
    ]
    baseline = report.get("baseline_summary") or {}
    comparison = report.get("comparison") or {}
    for criterion in CRITERIA:
        lines.append(
            f"| {criterion} | {_fmt(report['summary'].get(criterion))} | "
            f"{_fmt(baseline.get(criterion))} | {comparison.get(criterion, '—')} |"
        )
    lines += [
        "",
        "Aderência ao veredito: 0 ou 1, preenchida pelo operador.",
        "",
        "| Caso | Status | Fidelidade | Cobertura | Invenções | Português | Tokens "
        "(entrada/saída) | ms | Aderência |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for case in report["cases"]:
        status = case["status"] + (f" ({case['failure_code']})" if case["failure_code"] else "")
        lines.append(
            f"| {case['case_id']} | {status} | {_fmt(case['fidelity'])} | "
            f"{_fmt(case['coverage'])} | {_fmt(case['inventions'])} | "
            f"{_fmt(case['portuguese'])} | {_fmt(case['prompt_tokens'])}/"
            f"{_fmt(case['output_tokens'])} | {_fmt(case['total_ms'])} |  |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="v1", help="prompt version directory, e.g. v1")
    parser.add_argument("--model", help="Ollama model; defaults to OLLAMA_MODEL_ANALYSIS")
    parser.add_argument("--baseline", type=Path, help="a previous run's JSON report")
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    model = args.model or settings.ollama_model_analysis
    cases = load_cases(args.cases)
    if not cases:
        print(f"no cases in {args.cases}; export drafts with scripts/export_eval_cases.py")
        return 2
    gaps = missing_kinds(cases)
    if gaps:
        print(f"warning: the set does not cover {', '.join(sorted(gaps))}")

    scores = asyncio.run(_run(_adapter(settings, prompt=args.prompt, model=model), cases))
    summary = summarize(scores)
    report: dict[str, Any] = {
        "ran_at": datetime.now(UTC).isoformat(),
        "prompt": args.prompt,
        "model": model,
        "summary": summary,
        "cases": [score.as_dict() for score in scores],
    }
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report["baseline"] = str(args.baseline)
        report["baseline_summary"] = baseline["summary"]
        report["comparison"] = compare(summary, baseline["summary"])

    args.output.mkdir(parents=True, exist_ok=True)
    safe_model = re.sub(r"[^A-Za-z0-9.-]+", "_", model)
    stem = f"{datetime.now(UTC):%Y-%m-%d}-{args.prompt}-{safe_model}"
    (args.output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / f"{stem}.md").write_text(_markdown(report), encoding="utf-8")
    print(f"wrote {args.output / stem}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
