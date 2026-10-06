"""Create an immutable, read-only source/content baseline JSON artifact."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from opportunity_radar.acquisition.models import (  # noqa: E402
    HostBudgetStateModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.scheduling import HostBudgetState  # noqa: E402
from opportunity_radar.acquisition.service import _budget_host_for_source  # noqa: E402
from opportunity_radar.dashboard.source_baseline import (  # noqa: E402
    build_source_baseline,
    write_immutable_json,
)
from opportunity_radar.dashboard.source_quality import summarize_source_quality  # noqa: E402
from opportunity_radar.platform.database import create_database_engine  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, help="new path; existing artifacts are never overwritten"
    )
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--captured-at", help="ISO-8601 timestamp; defaults to current UTC")
    args = parser.parse_args()
    if args.window_days <= 0:
        parser.error("--window-days must be positive")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    captured_at = (
        datetime.fromisoformat(args.captured_at) if args.captured_at else datetime.now(timezone.utc)
    )
    window_start = captured_at - timedelta(days=args.window_days)
    engine = create_database_engine(database_url)
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        report = build_source_baseline(
            session, captured_at=captured_at, window_start=window_start, window_end=captured_at
        )
        report["snapshot_provenance"] = {
            "database_snapshot": session.execute(
                text("SELECT txid_current_snapshot()::text")
            ).scalar_one(),
            "isolation": "REPEATABLE READ READ ONLY",
        }
        sources = session.execute(
            select(
                SourceDefinitionModel.id,
                SourceDefinitionModel.enabled,
                SourceDefinitionModel.source_type,
                SourceDefinitionModel.configuration,
            ).order_by(SourceDefinitionModel.id)
        ).all()
        host_budgets = {
            row.host: row for row in session.execute(select(HostBudgetStateModel)).scalars().all()
        }
        runs = session.execute(
            select(
                SourceRunModel.id,
                SourceRunModel.source_definition_id,
                SourceRunModel.status,
                SourceRunModel.complete,
                SourceRunModel.started_at,
                SourceRunModel.finished_at,
                SourceRunModel.items_seen,
                SourceRunModel.items_persisted,
                SourceRunModel.items_invalid,
                SourceRunModel.items_target_area,
                SourceRunModel.items_off_target,
                SourceRunModel.error_code,
            )
            .where(SourceRunModel.started_at <= captured_at)
            .order_by(SourceRunModel.started_at.desc())
        ).all()
        source_rows = []
        for row in sources:
            host = _budget_host_for_source(row.source_type, row.configuration)
            budget_row = host_budgets.get(host)
            budget_exhausted = False
            cooldown_until = None
            if budget_row is not None:
                cooldown_until = budget_row.cooldown_until
                state = HostBudgetState(
                    host=budget_row.host,
                    window_start=budget_row.window_start,
                    requests_used=budget_row.requests_used,
                    requests_ceiling=budget_row.requests_ceiling,
                    cooldown_until=budget_row.cooldown_until,
                    exploration_reserve_ratio=budget_row.exploration_reserve_ratio,
                )
                # Low-yield capacity is the least restrictive gate. If even that has no
                # capacity, this is a temporary host-budget block for every source.
                budget_exhausted = not state.has_capacity(now=captured_at, is_low_yield=True)
            source_rows.append(
                {
                    "id": row.id,
                    "enabled": row.enabled,
                    # `enabled=False` removes this source from the active denominator, but
                    # does not establish whether its disablement is permanent.
                    "cooldown_until": cooldown_until,
                    "host_budget_exhausted": budget_exhausted,
                }
            )
        run_rows = [
            {
                "id": row.id,
                "source_definition_id": row.source_definition_id,
                "status": row.status,
                "complete": row.complete,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "items_seen": row.items_seen,
                "items_persisted": row.items_persisted,
                "items_invalid": row.items_invalid,
                "items_target_area": row.items_target_area,
                "items_off_target": row.items_off_target,
                "error_code": row.error_code,
            }
            for row in runs
        ]
        report["source_quality"] = summarize_source_quality(
            source_rows, run_rows, captured_at=captured_at
        )
    if args.output:
        write_immutable_json(str(args.output), report)
    else:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
