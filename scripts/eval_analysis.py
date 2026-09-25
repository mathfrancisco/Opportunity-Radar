"""Run the evaluation set against the local model and compare it with a baseline.

    python scripts/eval_analysis.py --prompt v1 --model qwen3:8b-q4_K_M
    python scripts/eval_analysis.py --prompt v2 --model qwen3:8b-q4_K_M \
        --baseline data/evals/2026-09-24-v1-qwen3_8b-q4_K_M.json
    python scripts/eval_analysis.py --prompt v2 --model qwen3:8b-q4_K_M --think \
        --label kv-q8_0 --unload-after            # a card F16-12 candidate

Cards F16-06 and F16-12. Uses the production adapter with the production `Settings`, so
it measures what will actually run, with every cache off: the adapter's memory is
disabled and nothing is read from or written to the analyses table. Critical cases run
`--repeat` times, because a fixed seed reduces variation and does not remove it.

The report (`data/evals/<date>-<prompt>-<model>[-<label>].json` and `.md`) records the
set's hash, the effective inference settings, the server version and model digest, and
— after the run — what `/api/ps` says the model occupies. Nothing is estimated: a number
the server did not give is written as absent. Verdict adherence and whether each quoted
passage supports its claim are blank columns for the operator; no model judges another.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from opportunity_radar.matching.analysis import AnalysisPolicy
from opportunity_radar.matching.evaluation import (
    CRITERIA,
    SPLITS,
    CaseScore,
    EvalCase,
    cases_digest,
    compare,
    load_cases,
    missing_kinds,
    score_case,
    summarize_by_split,
    switch_allowed,
    variation,
)
from opportunity_radar.matching.ollama import OllamaAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt, prompts_root
from opportunity_radar.platform.config import Settings

CASES_DIR = prompts_root() / "opportunity_analysis" / "eval" / "cases"
OUTPUT_DIR = Path("data/evals")


def _adapter(settings: Settings, args: argparse.Namespace, model: str) -> OllamaAnalysisAdapter:
    return OllamaAnalysisAdapter(
        base_url=settings.ollama_base_url,
        model=model,
        prompt=load_prompt(args.prompt),
        timeout_seconds=settings.ollama_analysis_timeout_seconds,
        connect_timeout_seconds=settings.ollama_analysis_connect_timeout_seconds,
        max_retries=settings.ollama_analysis_max_retries,
        retry_after_seconds=settings.ollama_analysis_retry_after_seconds,
        # Every case must reach the model, whatever the production policy would skip,
        # and no answer may come from the in-memory cache of a previous case.
        policy=AnalysisPolicy(skip_verdicts=frozenset(), skip_ineligible=False),
        cache_max_entries=0,
        num_ctx=args.num_ctx or settings.ollama_num_ctx,
        num_predict=args.num_predict or settings.ollama_num_predict,
        seed=settings.ollama_seed,
        keep_alive=settings.ollama_keep_alive,
        think=True if args.think else settings.ollama_think,
    )


async def _run(
    adapter: OllamaAnalysisAdapter, cases: list[EvalCase], repeat: int
) -> tuple[list[CaseScore], dict[str, list[CaseScore]], dict[str, Any]]:
    await adapter.warm_up()
    server = dict(await adapter.describe())
    scores: list[CaseScore] = []
    repeats: dict[str, list[CaseScore]] = defaultdict(list)
    settings_seen: dict[str, Any] = {}
    for case in cases:
        request = case.request()
        prepared = adapter.prepare(request)
        settings_seen = dict(prepared.inference)
        runs = repeat if case.critical else 1
        for attempt in range(runs):
            outcome = await adapter.analyze(request, prepared=prepared, use_cache=False)
            score = score_case(case, outcome, evidence_sources=prepared.evidence_sources)
            if attempt == 0:
                scores.append(score)
            if runs > 1:
                repeats[case.case_id].append(score)
            print(f"{case.case_id} [{attempt + 1}/{runs}]: {outcome.status.value}", flush=True)
    return scores, repeats, {"server": server, "inference": settings_seen}


def _loaded_models(base_url: str) -> list[dict[str, Any]]:
    """What the server reports resident right after the run: size and size in VRAM."""
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/ps", timeout=5.0)
        models = response.json().get("models") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return []
    return [
        {
            "name": item.get("name"),
            "size": item.get("size"),
            "size_vram": item.get("size_vram"),
            "context_length": item.get("context_length"),
        }
        for item in models or []
        if isinstance(item, dict)
    ]


def _unload(base_url: str, model: str) -> None:
    """`keep_alive: 0` frees the VRAM, so the next candidate is measured on its own."""
    try:
        httpx.post(
            f"{base_url.rstrip('/')}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=30.0,
        )
    except httpx.HTTPError:
        print("warning: could not unload the model; the next measurement may include it")


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}" if value < 10 else f"{value:.0f}"
    return str(value)


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Avaliação da análise — {report['prompt']} × {report['model']}"
        + (f" ({report['label']})" if report.get("label") else ""),
        "",
        f"Rodada em {report['ran_at']}, {len(report['cases'])} casos, conjunto "
        f"`{report['cases_digest'][:12]}`. Servidor {report['server'].get('server_version', '—')}"
        f", digest {report['server'].get('model_digest', '—')}.",
        "",
        "Decisão pelo conjunto reservado; `não comparável` é critério que o baseline não "
        "media e exige o gabarito, não uma melhora.",
        "",
        "| Critério | Reservado | Ajuste | Todos | Baseline (reservado) | Comparação |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    summary = report["summary"]
    baseline = (report.get("baseline_summary") or {}).get("reserved") or {}
    comparison = report.get("comparison") or {}
    for criterion in CRITERIA:
        lines.append(
            f"| {criterion} | {_fmt(summary['reserved'].get(criterion))} | "
            f"{_fmt(summary['tuning'].get(criterion))} | {_fmt(summary['all'].get(criterion))} | "
            f"{_fmt(baseline.get(criterion))} | {comparison.get(criterion, '—')} |"
        )
    if "switch_allowed" in report:
        lines += ["", f"Regra de troca atendida: {'sim' if report['switch_allowed'] else 'não'}."]
    lines += [
        "",
        "Memória do modelo após a rodada (`/api/ps`): "
        + (
            "; ".join(
                f"{item['name']}: {item['size_vram']} de {item['size']} bytes na VRAM"
                for item in report["loaded_models"]
            )
            or "não informada"
        )
        + ".",
        "",
        "Rubrica humana: aderência ao veredito (0/1) e sustentação — se cada trecho citado "
        "sustenta a afirmação, com atenção a negação e requisito opcional (0/1).",
        "",
        "| Caso | Split | Status | Fidelidade | Ancorado | Cobertura | Invenções | Opcionais | "
        "Português | Tokens (entrada/saída) | ms | Aderência | Sustentação |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
        "| :---: | :---: |",
    ]
    for case in report["cases"]:
        status = case["status"] + (f" ({case['failure_code']})" if case["failure_code"] else "")
        lines.append(
            f"| {case['case_id']} | {case['split']} | {status} | {_fmt(case['fidelity'])} | "
            f"{_fmt(case['grounded'])} | {_fmt(case['coverage'])} | {_fmt(case['inventions'])} | "
            f"{_fmt(case['optional_mentions'])} | {_fmt(case['portuguese'])} | "
            f"{_fmt(case['prompt_tokens'])}/{_fmt(case['output_tokens'])} | "
            f"{_fmt(case['total_ms'])} |  |  |"
        )
    if report["variation"]:
        lines += [
            "",
            "## Variação nos casos críticos",
            "",
            "| Caso | Execuções | Status | Cobertura média | Desvio | ms |",
            "| --- | ---: | --- | ---: | ---: | --- |",
        ]
        for case_id, item in report["variation"].items():
            lines.append(
                f"| {case_id} | {item['runs']} | {', '.join(item['statuses'])} | "
                f"{_fmt(item['coverage_mean'])} | {_fmt(item['coverage_stdev'])} | "
                f"{', '.join(_fmt(value) for value in item['total_ms'])} |"
            )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="v1", help="prompt version directory, e.g. v2")
    parser.add_argument("--model", help="Ollama model; defaults to OLLAMA_MODEL_ANALYSIS")
    parser.add_argument("--baseline", type=Path, help="a previous run's JSON report")
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--split", choices=("all", *SPLITS), default="all")
    parser.add_argument("--repeat", type=int, default=3, help="runs of each critical case")
    parser.add_argument("--think", action="store_true", help="turn Qwen3 reasoning on")
    parser.add_argument("--num-ctx", type=int, help="override OLLAMA_NUM_CTX")
    parser.add_argument("--num-predict", type=int, help="override OLLAMA_NUM_PREDICT")
    parser.add_argument("--label", help="server-side variant, e.g. kv-f16; goes in the name")
    parser.add_argument("--unload-after", action="store_true", help="keep_alive 0 at the end")
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    model = args.model or settings.ollama_model_analysis
    cases = load_cases(args.cases)
    if args.split != "all":
        cases = [case for case in cases if case.split == args.split]
    if not cases:
        print(f"no cases in {args.cases}; export drafts with scripts/export_eval_cases.py")
        return 2
    gaps = missing_kinds(cases)
    if gaps:
        print(f"warning: the set does not cover {', '.join(sorted(gaps))}")

    scores, repeats, identity = asyncio.run(
        _run(_adapter(settings, args, model), cases, max(1, args.repeat))
    )
    loaded = _loaded_models(settings.ollama_base_url)
    if args.unload_after:
        _unload(settings.ollama_base_url, model)
    summary = summarize_by_split(scores)
    report: dict[str, Any] = {
        "ran_at": datetime.now(UTC).isoformat(),
        "prompt": args.prompt,
        "model": model,
        "label": args.label,
        "cases_digest": cases_digest(cases),
        "server": identity["server"],
        "inference": identity["inference"],
        "loaded_models": loaded,
        "summary": summary,
        "cases": [score.as_dict() for score in scores],
        "variation": variation(repeats),
        # Filled by the operator: case id -> {"adherence": 0|1, "support": 0|1, "notes": ""}.
        "human_review": {score.case_id: {"adherence": None, "support": None} for score in scores},
    }
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        baseline_summary = baseline["summary"]
        if "reserved" not in baseline_summary:  # a report written before the splits
            baseline_summary = {"all": baseline_summary, "reserved": baseline_summary}
        report["baseline"] = str(args.baseline)
        report["baseline_summary"] = baseline_summary
        if baseline.get("cases_digest") not in (None, report["cases_digest"]):
            print("warning: the baseline graded a different set of cases")
        report["comparison"] = compare(summary["reserved"], baseline_summary["reserved"])
        report["switch_allowed"] = switch_allowed(report["comparison"])

    args.output.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9.-]+", "_", model + (f"-{args.label}" if args.label else ""))
    stem = f"{datetime.now(UTC):%Y-%m-%d}-{args.prompt}-{safe}"
    (args.output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / f"{stem}.md").write_text(_markdown(report), encoding="utf-8")
    print(f"wrote {args.output / stem}.json and .md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
