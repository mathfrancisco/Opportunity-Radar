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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from sqlalchemy import text

from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.health import database_health

OK = "ok"
WARN = "warn"
FAIL = "fail"

_SYMBOLS = {OK: "PASS", WARN: "WARN", FAIL: "FAIL"}


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
    checks.append(check_ollama(settings))
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
