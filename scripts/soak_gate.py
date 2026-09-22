"""Prove the system operates unattended for 72 hours, against a controlled clock.

    python scripts/soak_gate.py            # accelerated 72-hour window, exit 1 on failure
    python scripts/soak_gate.py --json     # same gate, machine-readable

Nothing here pokes the pipeline: after the bootstrap the only things that run are the
worker jobs themselves, on the simulated schedule. A gate that needed a terminal command
halfway through would be proving the opposite of what it claims.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from opportunity_radar.operations.soak import SOAK_HOURS, SOAK_STEP_MINUTES, run_soak
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.platform.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=int, default=SOAK_HOURS)
    parser.add_argument("--step-minutes", type=int, default=SOAK_STEP_MINUTES)
    parser.add_argument("--retention-days", type=int, default=365)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    configure_logging(settings.log_level)
    engine = create_database_engine(settings.database_url)
    result = run_soak(
        engine,
        settings,
        hours=args.hours,
        step_minutes=args.step_minutes,
        start=datetime.now(UTC),
        retention_days=args.retention_days,
    )

    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.passed else 1

    print(f"soak window: {result.hours}h in {result.steps} simulated passes")
    for check in result.checks:
        print(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
    print()
    print("the window held" if result.passed else "the window did not hold")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
