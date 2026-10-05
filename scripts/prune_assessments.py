"""Prune match assessments superseded for more than N days (card F50-08).

Dry run by default: it reports what would be deleted and deletes nothing. Read that report
before passing `--apply`, which is the only way this script deletes data.

Always kept: the latest assessment per posting and profile version, and any assessment with
an AI analysis, an analysis lease or a candidacy linked to it.
"""

from __future__ import annotations

import argparse
import json
import os

from opportunity_radar.operations.assessment_retention import (
    DEFAULT_ASSESSMENT_RETENTION_DAYS,
    prune_superseded_assessments,
)
from opportunity_radar.platform.database import create_database_engine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (the default)")
    mode.add_argument("--apply", action="store_true", help="delete for real")
    parser.add_argument("--days", type=int, default=DEFAULT_ASSESSMENT_RETENTION_DAYS)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=None)
    args = parser.parse_args(argv)
    engine = create_database_engine(os.environ["DATABASE_URL"])
    report = prune_superseded_assessments(
        engine,
        retention_days=args.days,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        dry_run=not args.apply,
    )
    print(json.dumps(report.as_dict(), indent=2))


if __name__ == "__main__":
    main()
