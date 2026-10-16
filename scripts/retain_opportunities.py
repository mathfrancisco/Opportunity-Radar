"""Delete opportunities older than N days, with their dependents (card R55-E2).

Dry run by default: it prints how many rows per table it would delete and deletes nothing.
Read that report before passing `--apply`, which is the only way this script deletes data.
Output is counts only; no posting content, no owner identity.

Always kept: opportunities with an application and opportunities marked relevant. Setting
`OPPORTUNITY_RETENTION_DAYS=0` disables the daily pipeline stage; this script ignores it and
uses `--days`.
"""

from __future__ import annotations

import argparse
import json
import os

from opportunity_radar.operations.opportunity_retention import (
    DEFAULT_AI_CALL_RECORD_RETENTION_DAYS,
    DEFAULT_OPPORTUNITY_RETENTION_DAYS,
    run_opportunity_retention,
)
from opportunity_radar.platform.database import create_database_engine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (the default)")
    mode.add_argument("--apply", action="store_true", help="delete for real")
    parser.add_argument("--days", type=int, default=DEFAULT_OPPORTUNITY_RETENTION_DAYS)
    parser.add_argument(
        "--ai-call-record-days", type=int, default=DEFAULT_AI_CALL_RECORD_RETENTION_DAYS
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=None)
    args = parser.parse_args(argv)
    if args.days <= 0:
        parser.error("--days must be positive")
    engine = create_database_engine(os.environ["DATABASE_URL"])
    report = run_opportunity_retention(
        engine,
        retention_days=args.days,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        ai_call_record_retention_days=args.ai_call_record_days,
        dry_run=not args.apply,
    )
    print(json.dumps(report.as_dict(), indent=2))


if __name__ == "__main__":
    main()
