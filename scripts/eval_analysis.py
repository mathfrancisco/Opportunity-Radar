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
from collections.abc import Awaitable, Callable, Sequence
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
from opportunity_radar.platform.ai.quota import (
    QuotaGuard,
    QuotaLimits,
    day_window,
    effective_ceiling,
)
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute, default_routes
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

CASES_DIR = prompts_root() / "opportunity_analysis" / "eval" / "cases"
OUTPUT_DIR = Path("data/evals")
# Soft limits allow 25 requests per minute. A 50-case baseline may exceed them.
# Waiting is an operator choice, never the default.


def _slug(model: str, label: str | None) -> str:
    """Filesystem-safe stem shared by the report files and the default checkpoint."""
    return re.sub(r"[^A-Za-z0-9.-]+", "_", model + (f"-{label}" if label else ""))


def default_checkpoint_path(output: Path, prompt: str, model: str, label: str | None) -> Path:
    """Where `--checkpoint` writes when the flag is not given.

    No date in the name (unlike the report): a checkpoint is meant to be found again by
    a later, possibly next-day, `--resume` of the same round.
    """
    return output / f"{prompt}-{_slug(model, label)}.checkpoint.jsonl"


def _checkpoint_record(
    case_id: str, score: CaseScore, repeat_scores: Sequence[CaseScore]
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "score": score.as_dict(),
        "repeat_scores": [item.as_dict() for item in repeat_scores] or None,
    }


def append_checkpoint(
    path: Path, case_id: str, score: CaseScore, repeat_scores: Sequence[CaseScore]
) -> None:
    """Append one finished case (its score and any repeats) and flush it to disk.

    Opening in append mode and closing right after (the `with` block) is what makes the
    write durable before the next case starts, so a quota stop or a crash never loses a
    case that already finished.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(_checkpoint_record(case_id, score, repeat_scores), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()


def load_checkpoint(path: Path) -> tuple[dict[str, CaseScore], dict[str, list[CaseScore]]]:
    """The finished cases a checkpoint already holds: `case_id -> score`, plus repeats.

    A later line for the same `case_id` replaces an earlier one, matching `append`'s own
    semantics if a case were ever written twice.
    """
    scores: dict[str, CaseScore] = {}
    repeats: dict[str, list[CaseScore]] = {}
    if not path.exists():
        return scores, repeats
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        case_id = record["case_id"]
        scores[case_id] = CaseScore(**record["score"])
        repeat_scores = record.get("repeat_scores")
        if repeat_scores:
            repeats[case_id] = [CaseScore(**item) for item in repeat_scores]
        else:
            repeats.pop(case_id, None)
    return scores, repeats


def _quota_limits(settings: Settings) -> QuotaLimits:
    return QuotaLimits(
        minute_requests=settings.ai_minute_requests_soft_limit,
        minute_tokens=settings.ai_minute_tokens_soft_limit,
        day_requests=settings.ai_daily_requests_soft_limit,
        day_tokens=settings.ai_daily_tokens_soft_limit,
    )


def _todays_usage(
    quota_guard: QuotaGuard, model: str
) -> tuple[int, int, int | None, int | None]:
    """requests, tokens spent today for `model`, and the ceilings Groq itself reported."""
    start = day_window(datetime.now(UTC))
    for row in quota_guard.snapshot():
        if row["model"] == model and row["window_kind"] == "day" and row["window_start"] == start:
            return row["requests"], row["tokens"], row["requests_ceiling"], row["tokens_ceiling"]
    return 0, 0, None, None


def estimate_round_tokens(
    adapter: GroqAnalysisAdapter, cases: Sequence[EvalCase], repeat: int
) -> int:
    """Prompt + max-output tokens each pending case (and its repeats) may still spend.

    Reuses `adapter.prepare()` — the same per-case token estimate the real call fits
    against — so the pre-flight number is not a second, independently-drifting guess.
    """
    total = 0
    for case in cases:
        prepared = adapter.prepare(case.request())
        max_output = prepared.inference.get("options", {}).get("max_completion_tokens") or 0
        per_call = (prepared.size.prompt_tokens_estimate or 0) + int(max_output)
        total += per_call * (repeat if case.critical else 1)
    return total


def preflight_check(
    adapter: GroqAnalysisAdapter,
    quota_guard: QuotaGuard,
    model: str,
    limits: QuotaLimits,
    cases: Sequence[EvalCase],
    repeat: int,
    *,
    allow_partial: bool,
) -> int | None:
    """`None` to proceed; a process exit code when the round will not fit today's budget."""
    used_requests, used_tokens, _requests_ceiling, tokens_ceiling = _todays_usage(
        quota_guard, model
    )
    round_tokens = estimate_round_tokens(adapter, cases, repeat)
    token_budget = effective_ceiling(limits.day_tokens, tokens_ceiling)
    remaining = max(0, token_budget - used_tokens)
    print(
        f"quota pre-flight for {model}: {used_tokens} tokens used today of {token_budget} "
        f"({used_requests} requests); this round is estimated at about {round_tokens} tokens "
        f"over {len(cases)} pending cases",
        flush=True,
    )
    if round_tokens > remaining and not allow_partial:
        print(
            f"aborting: the round's estimate ({round_tokens} tokens) does not fit the "
            f"remaining daily budget ({remaining} tokens); pass --allow-partial to run anyway",
            flush=True,
        )
        return 3
    return None


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
    quota_guard = QuotaGuard(engine, _quota_limits(settings))
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


async def _run(
    adapter: GroqAnalysisAdapter,
    cases: list[EvalCase],
    repeat: int,
    *,
    quota_wait_seconds: float = 0.0,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
    max_tokens: int | None = None,
    skip_case_ids: frozenset[str] = frozenset(),
    checkpoint_writer: Callable[[str, CaseScore, list[CaseScore]], None] | None = None,
) -> tuple[list[CaseScore], dict[str, list[CaseScore]], dict[str, Any], str | None, bool]:
    """Runs every case not in `skip_case_ids` (the `--resume` skip set).

    Returns `(scores, repeats, identity, quota_blocked_case, stopped_for_tokens)`. A
    finished case — including all of its repeats — is handed to `checkpoint_writer`
    (the `--resume` checkpoint) exactly once, only once it has run to completion: a case
    cut short by a quota block or by `max_tokens` is not checkpointed, so a later
    `--resume` reruns it whole rather than trusting a partial repeat set.
    """
    if sleeper is None:
        sleeper = asyncio.sleep
    await adapter.warm_up()
    server = dict(await adapter.describe())
    scores: list[CaseScore] = []
    repeats: dict[str, list[CaseScore]] = defaultdict(list)
    settings_seen: dict[str, Any] = {}
    quota_blocked_case: str | None = None
    stopped_for_tokens = False
    cumulative_tokens = 0
    for case in cases:
        if case.case_id in skip_case_ids:
            print(f"{case.case_id}: skipped, already in the checkpoint", flush=True)
            continue
        request = case.request()
        prepared = adapter.prepare(request)
        settings_seen = dict(prepared.inference)
        runs = repeat if case.critical else 1
        case_complete = False
        for attempt in range(runs):
            outcome = await adapter.analyze(request, prepared=prepared, use_cache=False)
            quota_blocked = (
                outcome.status is AnalysisStatus.AI_FAILED
                and outcome.failure_code is AnalysisFailureCode.QUOTA_EXHAUSTED
            )
            if quota_blocked and quota_wait_seconds > 0:
                wait_seconds = quota_wait_seconds
                quota_guard = adapter.quota_guard
                if quota_guard is not None:
                    next_available = await asyncio.to_thread(
                        quota_guard.next_available_at, adapter.model
                    )
                    seconds_until_available = (
                        next_available - datetime.now(UTC)
                    ).total_seconds()
                    wait_seconds = max(wait_seconds, seconds_until_available)
                print(
                    f"{case.case_id}: quota exhausted; waiting {wait_seconds:.0f}s "
                    "before one retry",
                    flush=True,
                )
                await sleeper(wait_seconds)
                outcome = await adapter.analyze(request, prepared=prepared, use_cache=False)
                quota_blocked = (
                    outcome.status is AnalysisStatus.AI_FAILED
                    and outcome.failure_code is AnalysisFailureCode.QUOTA_EXHAUSTED
                )
            score = score_case(case, outcome, evidence_sources=prepared.evidence_sources)
            if quota_blocked:
                score = replace(score, status="QUOTA_BLOCKED")
                quota_blocked_case = case.case_id
            if attempt == 0:
                scores.append(score)
            if runs > 1:
                repeats[case.case_id].append(score)
            cumulative_tokens += (score.prompt_tokens or 0) + (score.output_tokens or 0)
            status = "QUOTA_BLOCKED" if quota_blocked else outcome.status.value
            print(f"{case.case_id} [{attempt + 1}/{runs}]: {status}", flush=True)
            if quota_blocked:
                break
            if max_tokens is not None and cumulative_tokens >= max_tokens:
                stopped_for_tokens = True
                if attempt < runs - 1:
                    break
        else:
            case_complete = True
        if case_complete and checkpoint_writer is not None:
            checkpoint_writer(case.case_id, scores[-1], list(repeats.get(case.case_id, ())))
        if quota_blocked_case is not None or stopped_for_tokens:
            break
    return (
        scores,
        repeats,
        {"server": server, "inference": settings_seen},
        quota_blocked_case,
        stopped_for_tokens,
    )


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
        default=0.0,
        help="wait at least this long and retry once after quota exhaustion; 0 stops immediately",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="JSONL file of finished cases; defaults to a name derived from --output",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip cases already in the checkpoint and merge them into the report",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="stop cleanly once this round's cumulative tokens reach this",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="run even when the pre-flight estimate does not fit today's remaining budget",
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

    checkpoint_path = args.checkpoint or default_checkpoint_path(
        args.output, args.prompt, model, args.label
    )
    checkpoint_scores: dict[str, CaseScore] = {}
    checkpoint_repeats: dict[str, list[CaseScore]] = {}
    if args.resume:
        checkpoint_scores, checkpoint_repeats = load_checkpoint(checkpoint_path)
    elif checkpoint_path.exists():
        # A fresh (non-resumed) round starts its own checkpoint; an old file at the same
        # derived path is not this round's progress.
        checkpoint_path.unlink()
    pending_cases = [case for case in cases if case.case_id not in checkpoint_scores]

    engine = create_database_engine(settings.database_url)
    adapter = _adapter(settings, args, engine)
    quota_guard = adapter.quota_guard
    if quota_guard is not None:
        abort_code = preflight_check(
            adapter,
            quota_guard,
            model,
            _quota_limits(settings),
            pending_cases,
            max(1, args.repeat),
            allow_partial=args.allow_partial,
        )
        if abort_code is not None:
            return abort_code

    def _write_checkpoint(case_id: str, score: CaseScore, repeat_scores: list[CaseScore]) -> None:
        append_checkpoint(checkpoint_path, case_id, score, repeat_scores)

    new_scores, new_repeats, identity, quota_blocked_case, stopped_for_tokens = asyncio.run(
        _run(
            adapter,
            pending_cases,
            max(1, args.repeat),
            quota_wait_seconds=args.quota_wait_seconds,
            max_tokens=args.max_tokens,
            checkpoint_writer=_write_checkpoint,
        )
    )

    scores_by_id = {**checkpoint_scores, **{score.case_id: score for score in new_scores}}
    repeats_by_id = {**checkpoint_repeats, **new_repeats}
    scores = [scores_by_id[case.case_id] for case in cases if case.case_id in scores_by_id]
    repeats = {
        case.case_id: repeats_by_id[case.case_id]
        for case in cases
        if case.case_id in repeats_by_id
    }

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
        "quota_blocked_case": quota_blocked_case,
        "partial": quota_blocked_case is not None or stopped_for_tokens,
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
    stem = f"{datetime.now(UTC):%Y-%m-%d}-{args.prompt}-{_slug(model, args.label)}"
    (args.output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / f"{stem}.md").write_text(_markdown(report), encoding="utf-8")
    print(f"wrote {args.output / stem}.json and .md")
    if quota_blocked_case is not None:
        print(f"quota guard blocked case {quota_blocked_case}; stopping evaluation", flush=True)
        return 1
    if stopped_for_tokens:
        print(f"stopped: cumulative tokens reached --max-tokens {args.max_tokens}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
