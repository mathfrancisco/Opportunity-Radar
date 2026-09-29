"""One-off precision round for the assisted field suggestions (card F20-23).

    python scripts/eval_field_suggestions.py --used-today-tokens 20454 --max-tokens 90000

Runs the production `suggest_fields` (route `job_classification`, prompt
`job_classification/v1`) against the opportunities labelled in
`docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json` and scores every labelled
field as correct / wrong / abstained against the label. It never alters a deterministic
value: every call runs inside a SAVEPOINT of one outer transaction that is rolled back at
the end (the labelled fields are forced to `UNKNOWN` only inside that transaction so the
production trigger `unknown_fields` asks about them), and the script then re-reads the
labelled rows to prove the canonical columns are unchanged.

Run it against a COPY of the database, never the stack that owns the Groq quota:
`platform.ai_quota_usage` is per database, so the guard here only sees this round's own
spend. Pass what the real stack already spent today with `--used-today-tokens` (a `SELECT`
on the real database); the pre-flight aborts unless the round's estimate fits in the
remaining daily budget minus `--margin` (30% by default). `--max-tokens` stops the round
cleanly once cumulative tokens reach it; `--checkpoint`/`--resume` make a stopped round
continuable the next day without repeating a finished opportunity.

Scoring, per labelled field:

- label has a value: `correct` (same value), `wrong` (another value) or `abstained`
  (no suggestion, including one discarded for lacking a literal evidence excerpt);
- label is `manter UNKNOWN`: `correct_abstain` (no suggestion) or `false_positive`.

Precision = correct / (correct + wrong + false_positive): of the suggestions the model
made, how many an operator would rightly accept.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LABELS_PATH = Path("docs/44-roadmap-fase-20/rotulagem/f20-23-amostra-unknown.json")
OUTPUT_DIR = Path("data/evals")
FIELDS = ("role_family", "seniority", "work_mode")
MAX_OUTPUT_TOKENS = 300  # the job_classification route's completion budget


@dataclass(frozen=True, slots=True)
class LabelledField:
    opportunity_id: str
    field: str
    expected: str | None  # None = the label says keep UNKNOWN
    title: str = ""


@dataclass(frozen=True, slots=True)
class CaseResult:
    """What `suggest_fields` produced for one opportunity."""

    # field -> (value, evidence)
    created: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    discarded: frozenset[str] = frozenset()
    called: bool = False
    model: str | None = None


@dataclass(frozen=True, slots=True)
class FieldScore:
    opportunity_id: str
    field: str
    expected: str | None
    suggested: str | None
    evidence: str | None
    status: str  # correct | wrong | abstained | correct_abstain | false_positive | not_run
    discarded: bool = False


def load_labels(path: Path) -> dict[str, list[LabelledField]]:
    """`opportunity_id -> its labelled fields`, in file order."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cases: dict[str, list[LabelledField]] = {}
    for item in data["casos"]:
        expected = item.get("valor_recomendado")
        cases.setdefault(item["opportunity_id"], []).append(
            LabelledField(
                opportunity_id=item["opportunity_id"],
                field=item["field"],
                expected=str(expected).upper() if expected else None,
                title=item.get("title", ""),
            )
        )
    return cases


def score_field(
    labelled: LabelledField, result: CaseResult | None
) -> FieldScore:
    """Score one labelled field against what the model suggested (pure)."""
    if result is None or not result.called:
        return FieldScore(labelled.opportunity_id, labelled.field, labelled.expected, None, None,
                          "not_run")
    suggestion = result.created.get(labelled.field)
    suggested = suggestion[0].upper() if suggestion else None
    evidence = suggestion[1] if suggestion else None
    discarded = labelled.field in result.discarded
    if labelled.expected is None:
        status = "correct_abstain" if suggested is None else "false_positive"
    elif suggested is None:
        status = "abstained"
    else:
        status = "correct" if suggested == labelled.expected else "wrong"
    return FieldScore(
        labelled.opportunity_id, labelled.field, labelled.expected, suggested, evidence, status,
        discarded,
    )


def summarize(scores: Sequence[FieldScore]) -> dict[str, dict[str, Any]]:
    """Per field and `all`: counts by status, `precision` and `coverage` (pure)."""
    summary: dict[str, dict[str, Any]] = {}
    for name in (*FIELDS, "all"):
        rows = [s for s in scores if name == "all" or s.field == name]
        counts = Counter(s.status for s in rows)
        run = [s for s in rows if s.status != "not_run"]
        made = counts["correct"] + counts["wrong"] + counts["false_positive"]
        valued = [s for s in run if s.expected is not None]
        summary[name] = {
            "labelled": len(rows),
            "not_run": counts["not_run"],
            "correct": counts["correct"],
            "wrong": counts["wrong"],
            "abstained": counts["abstained"],
            "correct_abstain": counts["correct_abstain"],
            "false_positive": counts["false_positive"],
            "discarded_no_evidence": sum(1 for s in run if s.discarded),
            "precision": counts["correct"] / made if made else None,
            "coverage": (
                sum(1 for s in valued if s.suggested is not None) / len(valued) if valued else None
            ),
        }
    return summary


def estimate_case_tokens(user_chars: int, system_chars: int, *, max_input: int) -> int:
    """Prompt + max-output tokens one call may spend (the router's own `len // 3`)."""
    return min((system_chars + user_chars) // 3, max_input) + MAX_OUTPUT_TOKENS


def preflight(
    *,
    estimate: int,
    used_tokens: int,
    day_ceiling: int,
    margin: float,
    allow_partial: bool,
) -> tuple[bool, str]:
    """`(proceed, message)`: the round must fit `(ceiling - used) * (1 - margin)`."""
    remaining = max(0, day_ceiling - used_tokens)
    usable = int(remaining * (1 - margin))
    message = (
        f"quota pre-flight: {used_tokens} tokens used today of {day_ceiling}; "
        f"{remaining} remaining, {usable} usable after a {margin:.0%} margin; "
        f"this round is estimated at about {estimate} tokens"
    )
    if estimate > usable and not allow_partial:
        return False, message + "; aborting (pass --allow-partial to run anyway)"
    return True, message


def _record(opportunity_id: str, scores: Sequence[FieldScore], tokens: int, model: str | None,
            called: bool) -> dict[str, Any]:
    return {
        "opportunity_id": opportunity_id,
        "called": called,
        "model": model,
        "tokens": tokens,
        "scores": [asdict(score) for score in scores],
    }


def append_checkpoint(path: Path, record: Mapping[str, Any]) -> None:
    """Append one finished opportunity and flush it before the next call starts."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()


def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    """`opportunity_id -> record`; a later line replaces an earlier one."""
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            records[record["opportunity_id"]] = record
    return records


@dataclass(slots=True)
class RoundOutcome:
    records: dict[str, dict[str, Any]]
    tokens_spent: int = 0
    stopped_for_tokens: bool = False
    stopped_for_quota: bool = False


async def run_round(
    cases: Mapping[str, Sequence[LabelledField]],
    suggest: Callable[[str, Sequence[str]], Awaitable[CaseResult]],
    tokens_used: Callable[[], int],
    estimate: Callable[[str], int],
    *,
    max_tokens: int | None = None,
    skip: frozenset[str] = frozenset(),
    checkpoint_writer: Callable[[Mapping[str, Any]], None] | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retry_wait_seconds: float = 65.0,
    pace_tokens_per_minute: int | None = None,
) -> RoundOutcome:
    """Run every opportunity not in `skip`, one `suggest` call each.

    `tokens_used` is the cumulative spend the quota guard has settled; the round stops
    before a call whose estimate would carry the total past `max_tokens`. A call that
    did not reach the model (`called=False`: quota block, provider failure) is retried
    once after `retry_wait_seconds`; if it still did not run it is recorded `not_run`,
    never as an abstention, and is NOT checkpointed so `--resume` retries it.
    """
    outcome = RoundOutcome(records={})
    start = tokens_used()
    for opportunity_id, labelled in cases.items():
        if opportunity_id in skip:
            print(f"{opportunity_id}: skipped, already in the checkpoint", flush=True)
            continue
        spent = tokens_used() - start
        if max_tokens is not None and spent + estimate(opportunity_id) > max_tokens:
            outcome.stopped_for_tokens = True
            print(f"stopping: {spent} tokens spent, next call may exceed {max_tokens}", flush=True)
            break
        fields = [item.field for item in labelled]
        before = tokens_used()
        result = await suggest(opportunity_id, fields)
        if not result.called:
            await sleeper(retry_wait_seconds)
            result = await suggest(opportunity_id, fields)
        call_tokens = tokens_used() - before
        scores = [score_field(item, result) for item in labelled]
        record = _record(opportunity_id, scores, call_tokens, result.model, result.called)
        outcome.records[opportunity_id] = record
        print(
            f"{opportunity_id}: {', '.join(f'{s.field}={s.status}' for s in scores)} "
            f"({call_tokens} tokens)",
            flush=True,
        )
        if not result.called:
            outcome.stopped_for_quota = True
            break
        if checkpoint_writer is not None:
            checkpoint_writer(record)
        if pace_tokens_per_minute and call_tokens:
            await sleeper(call_tokens * 60 / pace_tokens_per_minute)
    outcome.tokens_spent = tokens_used() - start
    return outcome


def merge_scores(
    cases: Mapping[str, Sequence[LabelledField]],
    checkpoint: Mapping[str, Mapping[str, Any]],
    fresh: Mapping[str, Mapping[str, Any]],
) -> list[FieldScore]:
    """Every field's score in label order; an opportunity never run is `not_run`."""
    merged = {**checkpoint, **fresh}
    scores: list[FieldScore] = []
    for opportunity_id, labelled in cases.items():
        record = merged.get(opportunity_id)
        if record is None:
            scores.extend(score_field(item, None) for item in labelled)
        else:
            scores.extend(FieldScore(**item) for item in record["scores"])
    return scores


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Precisão F20-23 — {report['model']} × {report['prompt_version']}",
        "",
        f"Rodada em {report['ran_at']}; {report['tokens_spent']} tokens gastos nesta execução"
        f" ({report['tokens_total']} incluindo checkpoint).",
        "",
        "| Campo | Rotulados | Corretos | Errados | Abstenções | Manter UNKNOWN ok | "
        "Falso positivo | Precisão | Cobertura |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, row in report["summary"].items():
        lines.append(
            f"| {name} | {row['labelled']} | {row['correct']} | {row['wrong']} | "
            f"{row['abstained']} | {row['correct_abstain']} | {row['false_positive']} | "
            f"{_fmt(row['precision'])} | {_fmt(row['coverage'])} |"
        )
    lines += [
        "",
        "| Oportunidade | Campo | Rótulo | Sugerido | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for score in report["scores"]:
        lines.append(
            f"| {score['opportunity_id'][:8]} | {score['field']} | {score['expected'] or '—'} | "
            f"{score['suggested'] or '—'} | {score['status']} |"
        )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------
# Database-bound part: not unit-tested (needs Postgres and the real Groq key).
# --------------------------------------------------------------------------------------


def _snapshot_canonical(session: Any, ids: Sequence[str]) -> dict[str, tuple[Any, ...]]:
    from uuid import UUID

    from opportunity_radar.opportunities.models import OpportunityModel

    rows = {}
    for opportunity_id in ids:
        row = session.get(OpportunityModel, UUID(opportunity_id))
        if row is not None:
            rows[opportunity_id] = (
                row.role_family, row.seniority, row.work_mode, row.role_family_evidence,
                row.version,
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=LABELS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--model", help="pins the job_classification chain to this one model")
    parser.add_argument("--checkpoint", type=Path, help="JSONL of finished opportunities")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-tokens", type=int, help="stop cleanly at this cumulative spend")
    parser.add_argument(
        "--used-today-tokens", type=int, default=0,
        help="tokens the real stack already spent today (read from its ai_quota_usage)",
    )
    parser.add_argument("--margin", type=float, default=0.30)
    parser.add_argument("--limit", type=int, help="only the first N opportunities")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="pre-flight only, no Groq call")
    args = parser.parse_args(argv)

    from uuid import UUID

    from sqlalchemy.orm import Session

    # Register the mappers `OpportunityModel`'s foreign keys point at, so a flush resolves.
    import opportunity_radar.acquisition.models  # noqa: F401
    import opportunity_radar.companies.models  # noqa: F401
    from opportunity_radar.opportunities.domain import RoleFamily, Seniority, WorkMode
    from opportunity_radar.opportunities.models import OpportunityModel
    from opportunity_radar.opportunities.suggestions import (
        SuggestibleField,
        _render_user_content,
        load_classification_prompt,
        suggest_fields,
    )
    from opportunity_radar.platform.ai.breaker import CircuitBreaker
    from opportunity_radar.platform.ai.providers.groq import GroqProvider
    from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits, day_window
    from opportunity_radar.platform.ai.router import AIRouter
    from opportunity_radar.platform.ai.sanitizer import sanitize_for_llm
    from opportunity_radar.platform.ai.tasks import AITask, default_routes
    from opportunity_radar.platform.config import Settings
    from opportunity_radar.platform.database import create_database_engine

    class _ShowProviderErrors(logging.Handler):
        """The suggestion code logs a provider failure's summary in `extra`; print it."""

        def emit(self, record: logging.LogRecord) -> None:
            print(f"  provider: {record.getMessage()} | {getattr(record, 'error', '')}", flush=True)

    logging.getLogger("opportunity_radar.opportunities.suggestions").addHandler(
        _ShowProviderErrors(level=logging.WARNING)
    )

    settings = Settings()  # type: ignore[call-arg]
    cases = load_labels(args.labels)
    if args.limit:
        cases = dict(list(cases.items())[: args.limit])
    routes = default_routes(settings)
    if args.model:
        routes[AITask.JOB_CLASSIFICATION] = replace(
            routes[AITask.JOB_CLASSIFICATION], chain=(args.model,)
        )
    route = routes[AITask.JOB_CLASSIFICATION]
    model = route.chain[0]
    prompt = load_classification_prompt()

    checkpoint_path = args.checkpoint or args.output / f"f20-23-{model.replace('/', '_')}.jsonl"
    checkpoint: dict[str, dict[str, Any]] = {}
    if args.resume:
        checkpoint = load_checkpoint(checkpoint_path)
    elif checkpoint_path.exists():
        checkpoint_path.unlink()

    engine = create_database_engine(settings.database_url)
    limits = QuotaLimits(
        minute_requests=settings.ai_minute_requests_soft_limit,
        minute_tokens=settings.ai_minute_tokens_soft_limit,
        day_requests=settings.ai_daily_requests_soft_limit,
        day_tokens=settings.ai_daily_tokens_soft_limit,
    )
    quota_guard = QuotaGuard(engine, limits)

    def tokens_used() -> int:
        start = day_window(datetime.now(UTC))
        for row in quota_guard.snapshot():
            if (
                row["model"] == model
                and row["window_kind"] == "day"
                and row["window_start"] == start
            ):
                return int(row["tokens"])
        return 0

    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        ids = list(cases)
        before = _snapshot_canonical(session, ids)
        missing = [i for i in ids if i not in before]
        if missing:
            print(f"{len(missing)} labelled opportunities are not in this database: {missing[:3]}")
            return 2

        pending_ids = [i for i in ids if i not in checkpoint]

        def estimate(opportunity_id: str) -> int:
            row = session.get(OpportunityModel, UUID(opportunity_id))
            assert row is not None
            sanitized = sanitize_for_llm(
                {"title": row.canonical_title or "", "description": row.description or ""}
            )
            user = _render_user_content(
                prompt,
                pending_fields=[SuggestibleField(item.field) for item in cases[opportunity_id]],
                title=str(sanitized.get("title") or ""),
                description=str(sanitized.get("description") or ""),
            )
            return estimate_case_tokens(
                len(user), len(prompt.system), max_input=route.budget.max_input_tokens
            )

        round_estimate = sum(estimate(i) for i in pending_ids)
        used = max(args.used_today_tokens, tokens_used())
        proceed, message = preflight(
            estimate=round_estimate,
            used_tokens=used,
            day_ceiling=settings.ai_daily_tokens_soft_limit,
            margin=args.margin,
            allow_partial=args.allow_partial,
        )
        print(f"{message} over {len(pending_ids)} opportunities (model {model})", flush=True)
        if not proceed:
            return 3
        if args.dry_run:
            return 0

        provider = GroqProvider(
            api_key=settings.groq_api_key.get_secret_value(),
            base_url=settings.groq_base_url,
            timeout_seconds=settings.ai_timeout_seconds,
            connect_timeout_seconds=settings.ai_connect_timeout_seconds,
        )
        router = AIRouter(
            provider,
            routes,
            fallback_enabled=False,  # a measurement is pinned to one model
            max_retries=settings.ai_max_retries,
            breaker=CircuitBreaker(
                failures=settings.ai_breaker_failures,
                cooldown_seconds=settings.ai_breaker_cooldown_seconds,
            ),
            quota_guard=quota_guard,
        )
        forced = {
            "role_family": ("role_family", RoleFamily.UNKNOWN.value),
            "seniority": ("seniority", Seniority.UNKNOWN.value),
            "work_mode": ("work_mode", WorkMode.UNKNOWN.value),
        }

        async def suggest(opportunity_id: str, fields: Sequence[str]) -> CaseResult:
            row = session.get(OpportunityModel, UUID(opportunity_id))
            assert row is not None
            # In-transaction only (rolled back below): ask about the labelled fields
            # even where a newer rule already resolved them, and forget any earlier try.
            for name in fields:
                setattr(row, forced[name][0], forced[name][1])
            from sqlalchemy import delete

            from opportunity_radar.opportunities.suggestions import OpportunitySuggestionModel

            session.execute(
                delete(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id == row.id
                )
            )
            session.flush()
            outcome = await suggest_fields(session, router, row, prompt=prompt)
            return CaseResult(
                created={s.field: (s.value, s.evidence) for s in outcome.created},
                discarded=frozenset(outcome.discarded_fields),
                called=outcome.called,
                model=outcome.created[0].model if outcome.created else model,
            )

        outcome = asyncio.run(
            run_round(
                {i: cases[i] for i in ids},
                suggest,
                tokens_used,
                estimate,
                max_tokens=args.max_tokens,
                skip=frozenset(checkpoint),
                checkpoint_writer=lambda record: append_checkpoint(checkpoint_path, record),
                pace_tokens_per_minute=settings.ai_minute_tokens_soft_limit,
            )
        )
    finally:
        session.close()
        outer.rollback()  # nothing this round did to the database survives
        connection.close()

    with Session(engine) as verify:
        unchanged = _snapshot_canonical(verify, list(cases)) == before
    scores = merge_scores(cases, checkpoint, outcome.records)
    tokens_total = outcome.tokens_spent + sum(r.get("tokens", 0) for r in checkpoint.values())
    report = {
        "ran_at": datetime.now(UTC).isoformat(),
        "model": model,
        "prompt_version": prompt.version,
        "tokens_spent": outcome.tokens_spent,
        "tokens_total": tokens_total,
        "canonical_values_unchanged": unchanged,
        "partial": outcome.stopped_for_tokens or outcome.stopped_for_quota,
        "summary": summarize(scores),
        "scores": [asdict(score) for score in scores],
    }
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"{datetime.now(UTC):%Y-%m-%d}-f20-23-{model.replace('/', '_')}"
    (args.output / f"{stem}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output / f"{stem}.md").write_text(markdown(report), encoding="utf-8")
    print(f"wrote {args.output / stem}.json and .md; canonical values unchanged: {unchanged}")
    return 1 if report["partial"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
