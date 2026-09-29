"""Diagnose a local environment and say what is wrong, not just that something is.

Every check answers three things: what was inspected, what was found, and what to do
about it. A check that cannot run is reported as unknown rather than as a failure, so a
missing optional dependency never looks like a broken install.

    python scripts/doctor.py           # human output, exit 1 when something is broken
    python scripts/doctor.py --json    # same checks, machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.analysis_metrics import analysis_metrics
from opportunity_radar.dashboard.funnel import FunnelReport, funnel_report
from opportunity_radar.dashboard.metrics import METRIC_WINDOWS
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.operations.collection_alarm import (
    CollectionGapReport,
    collection_gap_report,
)
from opportunity_radar.operations.service import recent_passes
from opportunity_radar.platform.ai.config import AIState, ai_status
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits, day_window
from opportunity_radar.platform.ai.telemetry import ai_call_record
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.health import database_health
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

OK = "ok"
WARN = "warn"
FAIL = "fail"

_SYMBOLS = {OK: "PASS", WARN: "WARN", FAIL: "FAIL"}

#: SPEC 43, section 4: target p95 latency of a Groq analysis call.
ANALYSIS_P95_TARGET_MS = 15_000

#: SPEC 43 §8.5, card F20-20: below this share of the daily quota left, alert.
AI_DAY_BALANCE_ALERT_RATIO = 0.10


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    remedy: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "remedy": self.remedy,
            "facts": self.facts,
        }


def check_environment() -> Check:
    missing = [name for name in ("DATABASE_URL",) if not os.environ.get(name)]
    if missing:
        return Check(
            "environment",
            FAIL,
            f"missing variables: {', '.join(missing)}",
            "copy .env.example to .env, or run inside docker compose",
        )
    return Check("environment", OK, "required variables are set")


def check_dotenv(root: Path) -> Check:
    example = root / ".env.example"
    env = root / ".env"
    if not env.is_file():
        return Check(
            "dotenv",
            WARN,
            ".env does not exist",
            "run `make bootstrap` to create it from .env.example",
        )
    if not example.is_file():
        return Check("dotenv", WARN, ".env.example is missing", "restore it from git")
    declared = _env_keys(example)
    present = _env_keys(env)
    missing = sorted(declared - present)
    if missing:
        return Check(
            "dotenv",
            WARN,
            f".env is missing {len(missing)} key(s) declared in .env.example",
            f"add: {', '.join(missing)}",
            {"missing": missing},
        )
    return Check("dotenv", OK, ".env covers every documented key")


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def check_database(settings: Settings) -> Check:
    try:
        engine = create_database_engine(settings.database_url)
        health = database_health(engine)
    except Exception as error:  # pragma: no cover - depends on the local environment
        return Check(
            "database",
            FAIL,
            f"could not connect: {error}",
            "start PostgreSQL with `make up`",
        )
    if health.status != "healthy":
        return Check(
            "database",
            FAIL,
            health.detail or "database is not healthy",
            "run `make migrate` to bring the schema to head",
        )
    return Check("database", OK, "connected and at the head migration")


def check_tables(settings: Settings) -> Check:
    """Counts of the rows the flow depends on. Empty is reported, never assumed broken."""
    queries = {
        "companies": "SELECT count(*) FROM company_radar.company",
        "sources": "SELECT count(*) FROM acquisition.source_definition",
        "raw_items": "SELECT count(*) FROM acquisition.raw_item",
        "opportunities": "SELECT count(*) FROM opportunities.opportunity",
        "assessments": "SELECT count(*) FROM matching.match_assessment",
        "applications": "SELECT count(*) FROM crm.application_process",
    }
    counts: dict[str, Any] = {}
    try:
        engine = create_database_engine(settings.database_url)
        with engine.connect() as connection:
            for label, query in queries.items():
                counts[label] = connection.execute(text(query)).scalar_one()
    except Exception as error:
        return Check(
            "catalogue",
            FAIL,
            f"could not read the catalogue: {error}",
            "confirm the migrations ran with `make migrate`",
        )
    if counts["companies"] == 0:
        return Check(
            "catalogue",
            WARN,
            "no companies imported yet",
            "run `make import-companies`",
            counts,
        )
    return Check("catalogue", OK, "catalogue is populated", facts=counts)


#: Each functional job and the kill switch that decides whether it should be running. A
#: job that is switched off is not missing, and must never be reported as broken.
WORKER_JOB_SWITCHES = {
    "collect_enabled_sources": "worker_collect_enabled",
    "normalize_opportunities": "worker_normalize_enabled",
    "evaluate_pending": "worker_match_enabled",
    "analyze_pending": "worker_analyze_enabled",
    "expire_raw_payloads": "worker_retention_enabled",
}


def check_worker_jobs(settings: Settings, *, now: datetime | None = None) -> Check:
    """Say which jobs are healthy, late, failing or absent, from persisted state alone.

    A scheduler that is up proves nothing about a job that never ran, so nothing here is
    read from the process: the worker writes what it did, and this reads it back.
    """
    moment = now or datetime.now(UTC)
    grace = timedelta(seconds=settings.doctor_job_grace_seconds)
    expected = [name for name, switch in WORKER_JOB_SWITCHES.items() if getattr(settings, switch)]
    try:
        engine = create_database_engine(settings.database_url)
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT job_name, last_success_at, last_failure_at, next_run_at, "
                    "last_error FROM platform.worker_job_state"
                )
            ).all()
    except Exception as error:
        return Check(
            "worker jobs",
            FAIL,
            f"could not read the job state: {error}",
            "confirm the migrations ran with `make migrate`",
        )

    states = {row.job_name: row for row in rows}
    if not states:
        return Check(
            "worker jobs",
            WARN,
            "no job has recorded a pass yet",
            "start the worker with `make up`, or wait for its first pass",
            {"expected": expected},
        )

    facts = classify_worker_jobs(states, expected, now=moment, grace=grace)
    facts["disabled"] = sorted(set(WORKER_JOB_SWITCHES) - set(expected))
    broken = facts["missing"] + facts["failing"] + facts["late"]
    if broken:
        return Check(
            "worker jobs",
            FAIL,
            f"{len(broken)} job(s) are not operating: {', '.join(sorted(broken))}",
            "read the worker logs for the named job, then restart it with `make restart`",
            facts,
        )
    return Check(
        "worker jobs",
        OK,
        f"{len(facts['healthy'])} job(s) ran on schedule",
        facts=facts,
    )


def classify_worker_jobs(
    states: Mapping[str, Any],
    expected: Sequence[str],
    *,
    now: datetime,
    grace: timedelta,
) -> dict[str, list[str]]:
    """Sort the expected jobs into the four states an operator can act on.

    Failure is decided before lateness on purpose: a job that failed its last pass is
    broken whether or not the next one is overdue, and reporting it as merely late would
    send the operator to the scheduler instead of to the error.

    A job that has recorded an attempt but neither an outcome is running its first pass,
    not failing it. Left as a failure, every worker would look broken for the length of one
    job on every start. It becomes late once its next run is overdue, which is the real
    symptom of a pass that never finishes.
    """
    missing: list[str] = []
    failing: list[str] = []
    late: list[str] = []
    healthy: list[str] = []
    for name in expected:
        state = states.get(name)
        if state is None:
            missing.append(name)
        elif state.last_failure_at is not None and (
            state.last_success_at is None or state.last_failure_at > state.last_success_at
        ):
            failing.append(name)
        elif state.next_run_at is not None and now > state.next_run_at + grace:
            late.append(name)
        else:
            healthy.append(name)
    return {
        "missing": sorted(missing),
        "failing": sorted(failing),
        "late": sorted(late),
        "healthy": sorted(healthy),
    }


def check_source_incidents(settings: Settings) -> Check:
    """Open source incidents, and whether anything would have been sent about them."""
    try:
        engine = create_database_engine(settings.database_url)
        with engine.connect() as connection:
            open_incidents = connection.execute(
                text(
                    "SELECT source.name AS name, incident.consecutive_failures AS "
                    "failures, incident.alert_delivery AS delivery "
                    "FROM acquisition.source_alert_incident AS incident "
                    "JOIN acquisition.source_definition AS source "
                    "ON source.id = incident.source_definition_id "
                    "WHERE incident.recovered_at IS NULL "
                    "ORDER BY incident.opened_at"
                )
            ).all()
    except Exception as error:
        return Check(
            "source incidents",
            FAIL,
            f"could not read source incidents: {error}",
            "confirm the migrations ran with `make migrate`",
        )

    webhook = bool(settings.source_alert_webhook_url.strip())
    facts: dict[str, Any] = {
        "webhook_configured": webhook,
        "open_incidents": [
            {
                "source": row.name,
                "consecutive_failures": row.failures,
                "alert_delivery": row.delivery,
            }
            for row in open_incidents
        ],
    }
    if not webhook and open_incidents:
        return Check(
            "source incidents",
            WARN,
            f"{len(open_incidents)} source(s) are down and no webhook is configured",
            "set SOURCE_ALERT_WEBHOOK_URL, or watch this check",
            facts,
        )
    if open_incidents:
        return Check(
            "source incidents",
            WARN,
            f"{len(open_incidents)} source(s) are down",
            "read the run history of the named source and fix or disable it",
            facts,
        )
    if not webhook:
        return Check(
            "source incidents",
            WARN,
            "no source is down, but an outage would only be reported here",
            "set SOURCE_ALERT_WEBHOOK_URL to be told without opening the doctor",
            facts,
        )
    return Check("source incidents", OK, "no source incident is open", facts=facts)


def check_prompts(root: Path) -> Check:
    directory = root / "prompts" / "opportunity_analysis" / "v1"
    required = ("system.md", "user.md.j2", "output.schema.json", "metadata.yaml")
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        return Check(
            "prompts",
            FAIL,
            f"missing prompt artifacts: {', '.join(missing)}",
            "restore prompts/opportunity_analysis/v1 from git",
        )
    return Check("prompts", OK, "versioned prompt artifacts are present")


def check_ai(settings: Settings) -> Check:
    """Whether the cloud AI is on, has a key, and which model runs each role.

    Never makes a network call — a doctor run should not spend Groq quota — and never
    prints the key itself, only whether one is present.
    """
    facts: dict[str, Any] = {
        "enabled": settings.ai_enabled,
        "provider": settings.ai_provider,
        "key_present": bool(settings.groq_api_key.get_secret_value()),
        "reasoning_model": settings.groq_reasoning_model,
        "fast_model": settings.groq_fast_model,
        "alt_model": settings.groq_alt_model,
    }
    if not settings.ai_enabled:
        return Check(
            "ai",
            WARN,
            "AI is disabled; the semantic layer stays degraded",
            "set AI_ENABLED=true and a real GROQ_API_KEY to turn it on",
            facts,
        )
    if not facts["key_present"]:
        return Check(
            "ai",
            WARN,
            "AI is enabled but GROQ_API_KEY is missing",
            "set GROQ_API_KEY in the untracked .env file",
            facts,
        )
    return Check(
        "ai", OK, f"Groq is on; reasoning model {settings.groq_reasoning_model}", None, facts
    )


def check_analysis(settings: Settings) -> Check:
    """Backlog and 24-hour latency of the current model, against the SPEC target."""
    try:
        with Session(create_database_engine(settings.database_url)) as session:
            pending = MatchingService(session).count_pending_analysis(
                eligible_verdicts=settings.analysis_eligible_verdicts,
                cooldown=timedelta(seconds=settings.analysis_retry_cooldown_seconds),
                attempt_window=timedelta(seconds=settings.analysis_retry_attempt_window_seconds),
                max_attempts=settings.analysis_retry_max_attempts,
            )
            report = analysis_metrics(
                session,
                current_model=settings.groq_reasoning_model,
                pending=pending,
                windows={"24h": METRIC_WINDOWS["24h"]},
            )
    except Exception as error:  # pragma: no cover - depends on the local environment
        return Check("analysis", WARN, f"could not read analysis metrics: {error}")
    current = report.windows[0].for_model(settings.groq_reasoning_model)
    p95 = current.total_ms_p95 if current else None
    facts: dict[str, Any] = {
        "model": settings.groq_reasoning_model,
        "pending": pending,
        "p50_ms_24h": current.total_ms_p50 if current else None,
        "p95_ms_24h": p95,
        "failure_rate_24h": current.failure_rate if current else None,
    }
    if p95 is not None and p95 > ANALYSIS_P95_TARGET_MS:
        return Check(
            "analysis",
            WARN,
            f"p95 over 24 h is {p95 / 1000:.1f} s, above the {ANALYSIS_P95_TARGET_MS // 1000} s"
            " target",
            "check `ai` above: quota, fallback, or a slower model in the chain is the usual cause",
            facts,
        )
    measured = "no analysis measured in 24 h" if p95 is None else f"p95 {p95 / 1000:.1f} s"
    return Check("analysis", OK, f"{measured}; {pending} pending", None, facts)


def _models_with_a_recent_failure_streak(session: Session, threshold: int) -> set[str]:
    """A same-process approximation of "breaker open" (card F20-20).

    `CircuitBreaker` (card F20-11) is in-memory inside the API and the worker; this
    script is a third process and has no way to read it live. A model whose last
    `threshold` non-cache calls (SPEC 43 §8.5 telemetry, card F20-19) all failed
    transiently is the same condition that opens the real breaker, read after the
    fact from `platform.ai_call_record` instead of from live process state.
    """
    models = session.execute(select(ai_call_record.c.model).distinct()).scalars().all()
    flagged: set[str] = set()
    for model in models:
        rows = session.execute(
            select(ai_call_record.c.success, ai_call_record.c.error_kind)
            .where(ai_call_record.c.model == model, ai_call_record.c.cache_hit.is_(False))
            .order_by(ai_call_record.c.created_at.desc())
            .limit(threshold)
        ).all()
        if len(rows) >= threshold and all(
            success is False and error_kind == "transient" for success, error_kind in rows
        ):
            flagged.add(model)
    return flagged


def _hours(seconds: float | None) -> str:
    return "n/a" if seconds is None else f"{seconds / 3600:.1f}h"


def describe_collection_gap(report: CollectionGapReport) -> Check:
    """F48-07: warn when no scheduled run happened in more than twice the cadence."""
    facts: dict[str, Any] = {
        "evaluated_sources": report.evaluated_sources,
        "global_cadence": _hours(report.global_cadence_seconds),
        "last_scheduled_run_at": (
            report.last_scheduled_run_at.isoformat() if report.last_scheduled_run_at else None
        ),
        "overdue_sources": len(report.overdue_sources),
    }
    if not report.alarming:
        return Check(
            "collection gap",
            OK,
            f"{report.evaluated_sources} scheduled source(s) ran within {report.factor:g}x "
            "their cadence",
            facts=facts,
        )
    parts: list[str] = []
    if report.global_overdue:
        parts.append(
            "no scheduled run anywhere in more than "
            f"{report.factor:g}x the fastest cadence ({_hours(report.global_cadence_seconds)})"
        )
    if report.overdue_sources:
        worst = "; ".join(
            f"{gap.name} ({_hours(gap.age_seconds)} since last run, cadence "
            f"{_hours(gap.cadence_seconds)})"
            for gap in report.overdue_sources[:5]
        )
        parts.append(f"{len(report.overdue_sources)} source(s) overdue, worst: {worst}")
    return Check(
        "collection gap",
        WARN,
        " | ".join(parts),
        "check that the worker is running (`make logs`) and the collect job is enabled",
        facts,
    )


def check_collection_gap(settings: Settings, *, now: datetime | None = None) -> Check:
    try:
        engine = create_database_engine(settings.database_url)
        with Session(engine) as session:
            report = collection_gap_report(session, now=now)
            passes = recent_passes(session, "collect_enabled_sources", limit=5)
    except Exception as error:  # pragma: no cover - depends on the local environment
        return Check("collection gap", WARN, f"could not read scheduled runs: {error}")
    check = describe_collection_gap(report)
    history = [
        f"{row.started_at:%H:%M:%S} {row.duration_ms}ms due={row.due_sources}"
        for row in passes
    ]
    if not history:
        return check
    return Check(
        check.name,
        check.status,
        check.detail,
        check.remedy,
        {**check.facts, "recent_collect_passes": history},
    )


def describe_funnel(report: FunnelReport) -> Check:
    """F48-06: the SPEC 48 stages, the north-star and the guards, one fact per line."""
    star = report.north_star
    facts: dict[str, Any] = {}
    for stage in report.stages:
        lost = "" if stage.lost is None else f" (lost {stage.lost})"
        facts[f"stage.{stage.key}"] = f"{stage.count}{lost}"
    facts["north_star.areas"] = (
        f"{', '.join(star.role_families)} (technical proxy)"
        if star.proxy
        else ", ".join(star.role_families)
    )
    facts["north_star.stock"] = star.stock
    facts[f"north_star.new_{star.window_hours}h"] = star.new_in_window
    facts["north_star.stack"] = ", ".join(f"{label}={count}" for label, count in star.stack)
    for name, value in report.guards.items():
        share = "n/a" if value.ratio is None else f"{value.ratio:.1%}"
        facts[f"guard.{name}"] = f"{value.count}/{value.total} ({share})"
    facts["guard.forbidden_hosts_touched"] = report.forbidden_hosts_touched
    facts["guard.not_measured"] = ", ".join(report.not_measured)
    detail = (
        f"useful visible stock {star.stock}, new in {star.window_hours}h {star.new_in_window}"
    )
    if report.forbidden_hosts_touched:
        return Check(
            "funnel",
            WARN,
            f"{detail}; {report.forbidden_hosts_touched} forbidden host reference(s)",
            "remove the source or item that touches a forbidden host (SPEC 48 section 1.2)",
            facts,
        )
    return Check("funnel", OK, detail, facts=facts)


def check_funnel(settings: Settings) -> Check:
    try:
        engine = create_database_engine(settings.database_url)
        with Session(engine) as session:
            try:
                active = ProfileService(session).get_active()
                families = tuple(active.snapshot.preferences.target_role_families)
            except ProfileNotFoundError:
                families = ()
            report = funnel_report(session, target_role_families=families)
    except Exception as error:  # pragma: no cover - depends on the local environment
        return Check("funnel", WARN, f"could not compute the funnel: {error}")
    return describe_funnel(report)


def check_ai_usage(settings: Settings) -> Check:
    """Daily Groq quota balance and a telemetry-based breaker alert (card F20-20)."""
    state = ai_status(settings)
    if state is not AIState.ENABLED:
        return Check("ai_usage", OK, f"AI is {state.value}; nothing to check")
    try:
        engine = create_database_engine(settings.database_url)
        guard = QuotaGuard(
            engine,
            QuotaLimits(
                minute_requests=settings.ai_minute_requests_soft_limit,
                minute_tokens=settings.ai_minute_tokens_soft_limit,
                day_requests=settings.ai_daily_requests_soft_limit,
                day_tokens=settings.ai_daily_tokens_soft_limit,
            ),
        )
        today = day_window(datetime.now(UTC))
        day_rows = {
            row["model"]: row
            for row in guard.snapshot()
            if row["window_kind"] == "day" and row["window_start"] == today
        }
        with Session(engine) as session:
            likely_open = _models_with_a_recent_failure_streak(
                session, settings.ai_breaker_failures
            )
    except Exception as error:  # pragma: no cover - depends on the local environment
        return Check("ai_usage", WARN, f"could not read AI quota or telemetry: {error}")

    alerts: list[str] = []
    facts: dict[str, Any] = {"models": {}}
    for model in (
        settings.groq_reasoning_model,
        settings.groq_fast_model,
        settings.groq_alt_model,
    ):
        used = day_rows.get(model, {}).get("requests", 0)
        limit = settings.ai_daily_requests_soft_limit
        remaining_ratio = 1 - used / limit if limit else 1.0
        breaker_alert = model in likely_open
        facts["models"][model] = {
            "day_requests_used": used,
            "day_requests_limit": limit,
            "remaining_ratio": remaining_ratio,
            "likely_breaker_open": breaker_alert,
        }
        if remaining_ratio < AI_DAY_BALANCE_ALERT_RATIO:
            alerts.append(f"{model} daily balance at {remaining_ratio:.0%}")
        if breaker_alert:
            alerts.append(f"{model} breaker likely open (recent calls all failed)")
    if alerts:
        return Check(
            "ai",
            WARN,
            "; ".join(alerts),
            "check Groq status and AI_DAILY_REQUESTS_SOFT_LIMIT",
            facts,
        )
    return Check("ai_usage", OK, "daily quota balance healthy; no breaker alert", None, facts)


def run_checks(root: Path) -> list[Check]:
    checks = [check_environment(), check_dotenv(root), check_prompts(root)]
    if checks[0].status == FAIL:
        # Without DATABASE_URL the remaining checks would fail for the same reason, which
        # would bury the one problem that actually needs fixing.
        return checks
    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    checks.append(check_database(settings))
    if checks[-1].status == OK:
        checks.append(check_tables(settings))
        checks.append(check_worker_jobs(settings))
        checks.append(check_source_incidents(settings))
        checks.append(check_collection_gap(settings))
        checks.append(check_funnel(settings))
        checks.append(check_analysis(settings))
        checks.append(check_ai_usage(settings))
    checks.append(check_ai(settings))
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    checks = run_checks(args.root)
    broken = [check for check in checks if check.status == FAIL]

    if args.json:
        print(
            json.dumps(
                {
                    "checked_at": datetime.now(UTC).isoformat(),
                    "status": FAIL if broken else OK,
                    "checks": [check.as_dict() for check in checks],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if broken else 0

    for check in checks:
        print(f"[{_SYMBOLS[check.status]}] {check.name}: {check.detail}")
        for key, value in check.facts.items():
            print(f"         {key}: {value}")
        if check.remedy and check.status != OK:
            print(f"         fix: {check.remedy}")
    print()
    print("environment is broken" if broken else "environment looks usable")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
