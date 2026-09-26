"""Run the evaluation set against Groq and compare it with a baseline.

    python scripts/eval_analysis.py --prompt v1
    python scripts/eval_analysis.py --prompt v1 --model openai/gpt-oss-120b \
        --baseline data/evals/2026-09-26-v1-openai_gpt-oss-120b.json

Cards F16-06, F20-21. Uses the production `GroqAnalysisAdapter` behind the shared
`AIRouter`, with the production `Settings`, so it measures what will actually run: the
Quota Guard reserves real budget before every call (`platform.ai_quota_usage`) and the
circuit breaker behaves as it would in the worker. `--model` overrides the first model of
the `job_match` route and turns fallback off, so a baseline run is pinned to exactly one
model rather than silently drifting onto the chain's next one. Critical cases run
`--repeat` times, because a fixed seed reduces variation and does not remove it.

The report (`data/evals/<date>-<prompt>-<model>[-<label>].json` and `.md`) records the
set's hash, the effective inference settings and the provider's chain. Nothing is
estimated: a number the server did not give is written as absent. Verdict adherence and
whether each quoted passage supports its claim are blank columns for the operator; no
model judges another.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from opportunity_radar.matching.analysis import AnalysisFailureCode, AnalysisPolicy, AnalysisStatus
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
from opportunity_radar.matching.groq import GroqAnalysisAdapter
from opportunity_radar.matching.prompts import load_prompt, prompts_root
from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute, default_routes
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

CASES_DIR = prompts_root() / "opportunity_analysis" / "eval" / "cases"
OUTPUT_DIR = Path("data/evals")


def resolve_routes(settings: Settings, model: str | None) -> dict[AITask, ModelRoute]:
    """The task routes `_adapter` uses, with `job_match` pinned to `model` when given.

    Pure and separately tested: no Groq call, no engine, so `--model` can be checked
    without a database or `GROQ_API_KEY`.
    """
    routes = default_routes(settings)
    if model:
        routes[AITask.JOB_MATCH] = replace(routes[AITask.JOB_MATCH], chain=(model,))
    return routes


def _adapter(settings: Settings, args: argparse.Namespace, engine: Engine) -> GroqAnalysisAdapter:
    routes = resolve_routes(settings, args.model)
    provider = GroqProvider(
        api_key=settings.groq_api_key.get_secret_value(),
        base_url=settings.groq_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        connect_timeout_seconds=settings.ai_connect_timeout_seconds,
    )
    quota_guard = QuotaGuard(
        engine,
        QuotaLimits(
            minute_requests=settings.ai_minute_requests_soft_limit,
            minute_tokens=settings.ai_minute_tokens_soft_limit,
            day_requests=settings.ai_daily_requests_soft_limit,
            day_tokens=settings.ai_daily_tokens_soft_limit,
        ),
    )
    breaker = CircuitBreaker(
        failures=settings.ai_breaker_failures,
        cooldown_seconds=settings.ai_breaker_cooldown_seconds,
    )
    router = AIRouter(
        provider,
        routes,
        # A baseline is pinned to one model: `--model` overrides the chain to a single
        # entry, and fallback is off so a quota hiccup never silently answers with the
        # alt model instead of failing the case.
        fallback_enabled=False if args.model else settings.ai_fallback_enabled,
        max_retries=settings.ai_max_retries,
        breaker=breaker,
        quota_guard=quota_guard,
    )
    return GroqAnalysisAdapter(
        router=router,
        prompt=load_prompt(args.prompt),
        # Every case must reach the model, whatever the production policy would skip.
        policy=AnalysisPolicy(skip_verdicts=frozenset(), skip_ineligible=False),
    )


#: The free-tier per-minute token budget is small enough that a 50-case run outruns it
#: in seconds; a quota failure is retried after a wait rather than recorded immediately,
#: so the reported completed_rate reflects the model, not the eval loop's pace.
_QUOTA_RETRY_WAIT_SECONDS = 20.0
_QUOTA_RETRY_ATTEMPTS = 3


async def _analyze_with_quota_retry(
    adapter: GroqAnalysisAdapter,
    request: Any,
    prepared: Any,
    *,
    wait_seconds: float,
    sleeper: Any = asyncio.sleep,
) -> Any:
    for attempt in range(_QUOTA_RETRY_ATTEMPTS + 1):
        outcome = await adapter.analyze(request, prepared=prepared, use_cache=False)
        quota_blocked = (
            outcome.status is AnalysisStatus.AI_FAILED
            and outcome.failure_code is AnalysisFailureCode.QUOTA_EXHAUSTED
        )
        if not quota_blocked or attempt == _QUOTA_RETRY_ATTEMPTS or wait_seconds <= 0:
            return outcome
        print(
            f"  quota exhausted, waiting {wait_seconds:.0f}s before retry "
            f"{attempt + 1}/{_QUOTA_RETRY_ATTEMPTS}",
            flush=True,
        )
        await sleeper(wait_seconds)
    return outcome  # pragma: no cover - loop always returns above


async def _run(
    adapter: GroqAnalysisAdapter,
    cases: list[EvalCase],
    repeat: int,
    *,
    quota_wait_seconds: float = _QUOTA_RETRY_WAIT_SECONDS,
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
            outcome = await _analyze_with_quota_retry(
                adapter, request, prepared, wait_seconds=quota_wait_seconds
            )
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
        f", cadeia {', '.join(report['server'].get('chain', ()) or ('—',))}.",
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
    parser.add_argument(
        "--model",
        help="overrides the first model of the job_match route; disables fallback",
    )
    parser.add_argument("--baseline", type=Path, help="a previous run's JSON report")
    parser.add_argument("--cases", type=Path, default=CASES_DIR)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--split", choices=("all", *SPLITS), default="all")
    parser.add_argument("--repeat", type=int, default=3, help="runs of each critical case")
    parser.add_argument("--label", help="goes in the report file name, e.g. baseline")
    parser.add_argument(
        "--quota-wait-seconds",
        type=float,
        default=_QUOTA_RETRY_WAIT_SECONDS,
        help="wait this long and retry (up to 3 times) on a quota-exhausted case; 0 disables",
    )
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
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

    engine = create_database_engine(settings.database_url)
    scores, repeats, identity = asyncio.run(
        _run(
            _adapter(settings, args, engine),
            cases,
            max(1, args.repeat),
            quota_wait_seconds=args.quota_wait_seconds,
        )
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
        "loaded_models": [],
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
