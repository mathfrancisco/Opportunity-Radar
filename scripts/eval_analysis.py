"""Run the evaluation set against the configured Groq model and compare it with a baseline.

    python scripts/eval_analysis.py --prompt v1
    python scripts/eval_analysis.py --prompt v2 \
        --baseline data/evals/2026-09-24-v1-openai_gpt-oss-120b.json

Cards F16-06, F20-06. Uses the production adapter (`build_analysis_adapter`) with the
production `Settings`, so it measures what will actually run against Groq. The default
policy is overridden so every case reaches the model, whatever verdict or eligibility
the production worker would otherwise skip. Critical cases run `--repeat` times, because
a fixed seed reduces variation and does not remove it.

The report (`data/evals/<date>-<prompt>-<model>[-<label>].json` and `.md`) records the
set's hash and the provider/model identity Groq reported. Nothing is estimated: a number
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

from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import AnalysisPolicy, SemanticAnalysisPort
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
from opportunity_radar.matching.prompts import prompts_root
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

CASES_DIR = prompts_root() / "opportunity_analysis" / "eval" / "cases"
OUTPUT_DIR = Path("data/evals")

#: Every case must reach the model, whatever the production policy would skip.
_EVAL_POLICY = AnalysisPolicy(skip_verdicts=frozenset(), skip_ineligible=False)


def _adapter(settings: Settings) -> SemanticAnalysisPort:
    engine = create_database_engine(settings.database_url)
    adapter = build_analysis_adapter(settings, engine, policy=_EVAL_POLICY)
    if adapter.__class__.__name__ == "NullAnalysisAdapter":
        raise SystemExit(
            "AI_ENABLED must be true and GROQ_API_KEY must be set to run the evaluation"
        )
    return adapter


async def _run(
    adapter: SemanticAnalysisPort, cases: list[EvalCase], repeat: int
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
        f"`{report['cases_digest'][:12]}`. Provedor {report['server'].get('provider', '—')}"
        f", cadeia {', '.join(report['server'].get('chain', ())) or '—'}.",
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
    parser.add_argument("--model", help="Groq model id; defaults to GROQ_REASONING_MODEL")
    parser.add_argument("--baseline", type=Path, help="a previous run's JSON report")
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--split", choices=("all", *SPLITS), default="all")
    parser.add_argument("--repeat", type=int, default=3, help="runs of each critical case")
    parser.add_argument("--label", help="run variant, e.g. reasoning-medium; goes in the name")
    args = parser.parse_args(argv)

    base_settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    overrides: dict[str, Any] = {"ai_analysis_prompt": args.prompt}
    if args.model:
        overrides["groq_reasoning_model"] = args.model
    settings = base_settings.model_copy(update=overrides)
    model = args.model or settings.groq_reasoning_model
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
        _run(_adapter(settings), cases, max(1, args.repeat))
    )
    summary = summarize_by_split(scores)
    report: dict[str, Any] = {
        "ran_at": datetime.now(UTC).isoformat(),
        "prompt": args.prompt,
        "model": model,
        "label": args.label,
        "cases_digest": cases_digest(cases),
        "server": identity["server"],
        "inference": identity["inference"],
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
