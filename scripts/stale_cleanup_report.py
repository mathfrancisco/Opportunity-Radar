"""Per-source count of stored opportunities older than the ingestion window (card R55-A5).

Read-only by default: it prints, per source, how many stored opportunities are older than
`--days` (by `published_at`, else the source's `updated_at`, else first seen), how many an
application or a relevant mark protects, and how many a cleanup would delete. The owner reads
that report before approving `--apply`, which deletes through the existing retention path
(`run_opportunity_retention`, same age, same protections). Output is counts only: no posting
content, no owner identity.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict

from opportunity_radar.operations.opportunity_retention import (
    DEFAULT_OPPORTUNITY_RETENTION_DAYS,
    run_opportunity_retention,
    stale_by_source,
)
from opportunity_radar.platform.database import create_database_engine


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_OPPORTUNITY_RETENTION_DAYS)
    parser.add_argument("--apply", action="store_true", help="delete for real after reporting")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.days <= 0:
        parser.error("--days must be positive")
    engine = create_database_engine(os.environ["DATABASE_URL"])
    rows = stale_by_source(engine, retention_days=args.days)
    output: dict[str, object] = {
        "days": args.days,
        "applied": args.apply,
        "sources": [asdict(row) for row in rows],
        "totals": {
            key: sum(getattr(row, key) for row in rows)
            for key in (
                "stale_opportunities",
                "kept_with_application",
                "kept_with_relevant_mark",
                "eligible_opportunities",
                "linked_raw_items",
            )
        },
    }
    if args.apply:
        report = run_opportunity_retention(
            engine,
            retention_days=args.days,
            batch_size=args.batch_size,
            purge_tavily_cache=False,
            ai_call_record_retention_days=None,
            dry_run=False,
        )
        output["deleted_rows"] = dict(sorted(report.rows.items()))
        output["complete"] = report.complete
        output["errors"] = report.errors
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
