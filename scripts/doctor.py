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
from urllib.request import urlopen

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.analysis_metrics import analysis_metrics
from opportunity_radar.dashboard.metrics import METRIC_WINDOWS
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.health import database_health

OK = "ok"
WARN = "warn"
FAIL = "fail"

_SYMBOLS = {OK: "PASS", WARN: "WARN", FAIL: "FAIL"}

#: SPEC 36, section 3.2: p95 of a warm analysis on the reference GPU.
ANALYSIS_P95_TARGET_MS = 15_000


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
    expected = [
        name
        for name, switch in WORKER_JOB_SWITCHES.items()
        if getattr(settings, switch)
    ]
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
            state.last_success_at is None
            or state.last_failure_at > state.last_success_at
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


def check_ollama(settings: Settings) -> Check:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        with urlopen(url, timeout=settings.ollama_health_timeout_seconds) as response:
            models = json.load(response).get("models", [])
    except Exception:
        return Check(
            "ollama",
            WARN,
            "Ollama is unreachable; the semantic layer stays degraded",
            "start it with `make up`, or set OLLAMA_ANALYSIS_ENABLED=false",
        )
    names = {model.get("name") for model in models if isinstance(model, dict)}
    if settings.ollama_model_analysis not in names:
        return Check(
            "ollama",
            WARN,
            f"model {settings.ollama_model_analysis} is not installed",
            f"run `ollama pull {settings.ollama_model_analysis}`",
            {"installed": sorted(name for name in names if name)},
        )
    return Check("ollama", OK, f"model {settings.ollama_model_analysis} is installed")


def check_ollama_gpu(settings: Settings) -> Check:
    """Server version and whether the loaded models sit entirely in VRAM.

    A model with `size_vram < size` has part of it in system RAM: it answers, slowly,
    and competes with Postgres for memory. That is a warning, not a failure, because the
    CPU path is a supported fallback (compose.cpu.yaml).
    """
    base = settings.ollama_base_url.rstrip("/")
    try:
        timeout = settings.ollama_health_timeout_seconds
        with urlopen(f"{base}/api/version", timeout=timeout) as response:
            version = json.load(response).get("version")
        with urlopen(f"{base}/api/ps", timeout=timeout) as response:
            loaded = json.load(response).get("models", [])
    except Exception:
        return Check(
            "ollama gpu",
            WARN,
            "could not read the Ollama version or its loaded models",
            "check that the ollama service is up",
        )
    facts: dict[str, Any] = {"version": version, "loaded": []}
    spilled: list[str] = []
    for model in loaded if isinstance(loaded, list) else []:
        if not isinstance(model, dict):
            continue
        size, in_vram = model.get("size"), model.get("size_vram")
        facts["loaded"].append(
            {"name": model.get("name"), "size": size, "size_vram": in_vram}
        )
        if isinstance(size, int) and isinstance(in_vram, int) and in_vram < size:
            spilled.append(str(model.get("name")))
    if spilled:
        return Check(
            "ollama gpu",
            WARN,
            f"loaded partly outside VRAM: {', '.join(spilled)}",
            "reserve the GPU (docs/30-runbook.md) or use a smaller model or context",
            facts,
        )
    if not facts["loaded"]:
        return Check(
            "ollama gpu", OK, f"server {version}; no model loaded right now", None, facts
        )
    return Check("ollama gpu", OK, f"server {version}; loaded models are in VRAM", None, facts)


def check_analysis(settings: Settings) -> Check:
    """Backlog and 24-hour latency of the current model, against the SPEC target."""
    try:
        with Session(create_database_engine(settings.database_url)) as session:
            pending = MatchingService(session).count_pending_analysis(
                eligible_verdicts=settings.analysis_eligible_verdicts,
                cooldown=timedelta(seconds=settings.analysis_retry_cooldown_seconds),
                attempt_window=timedelta(
                    seconds=settings.analysis_retry_attempt_window_seconds
                ),
                max_attempts=settings.analysis_retry_max_attempts,
            )
            report = analysis_metrics(
                session,
                current_model=settings.ollama_model_analysis,
                pending=pending,
                windows={"24h": METRIC_WINDOWS["24h"]},
            )
    except Exception as error:  # pragma: no cover - depends on the local environment
        return Check("analysis", WARN, f"could not read analysis metrics: {error}")
    current = report.windows[0].for_model(settings.ollama_model_analysis)
    p95 = current.total_ms_p95 if current else None
    facts: dict[str, Any] = {
        "model": settings.ollama_model_analysis,
        "keep_alive": settings.ollama_keep_alive,
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
            "check `ollama gpu` above: a model outside VRAM is the usual cause",
            facts,
        )
    measured = "no analysis measured in 24 h" if p95 is None else f"p95 {p95 / 1000:.1f} s"
    return Check("analysis", OK, f"{measured}; {pending} pending", None, facts)


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
        checks.append(check_analysis(settings))
    checks.append(check_ollama(settings))
    checks.append(check_ollama_gpu(settings))
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
