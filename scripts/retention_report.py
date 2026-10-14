"""Report retention candidates, protected references, and relation sizes only."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text

from opportunity_radar.operations.assessment_retention import (
    DEFAULT_ASSESSMENT_RETENTION_DAYS,
    prune_superseded_assessments,
)
from opportunity_radar.platform.backup import FORMAT_VERSION, MANIFEST_QUERIES
from opportunity_radar.platform.database import create_database_engine

_RELATION_SIZES = """
SELECT schemaname, relname, pg_total_relation_size(relid)
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
"""


def _relation_sizes(connection: Any) -> list[dict[str, Any]]:
    return [
        {"schema": row[0], "relation": row[1], "bytes": int(row[2])}
        for row in connection.execute(text(_RELATION_SIZES)).fetchall()
    ]


def build_report(
    engine: Engine,
    *,
    retention_days: int = DEFAULT_ASSESSMENT_RETENTION_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    retention = prune_superseded_assessments(
        engine, retention_days=retention_days, dry_run=True, now=now
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
        sizes = _relation_sizes(connection)
    return {
        "dry_run": True,
        "retention": retention.as_dict(),
        "candidates": retention.candidates,
        "deletable": retention.deletable,
        "protected_references": {
            "analysis": retention.kept_with_analysis,
            "claim": retention.kept_with_claim,
            "application": retention.kept_with_application,
            "current": retention.kept_as_current,
        },
        "relation_sizes": sizes,
        "backup_manifest_format_version": FORMAT_VERSION,
        "backup_manifest_tables": sorted(MANIFEST_QUERIES),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_ASSESSMENT_RETENTION_DAYS)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    report = build_report(
        create_database_engine(os.environ["DATABASE_URL"]), retention_days=args.days
    )
    output = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if args.output is None:
        print(output, end="")
    else:
        args.output.write_text(output, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
