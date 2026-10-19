"""Trim `opportunities.opportunity.description` already stored beyond the R55-E6 cap.

New and refreshed postings are trimmed on write (`STORED_DESCRIPTION_MAX_CHARS`, default
4000). This one-off script applies the same rule to rows written earlier. It rewrites only
`description` (the generated `search_document` follows) and does NOT bump `version`: the
posting did not change, so no reanalysis wave is started. Skills, seniority and country were
extracted from the full text before and are left as they are. `--dry-run` writes nothing.
Idempotent: a second run finds no row over the cap. Reclaim the space afterwards with a
table rewrite (VACUUM FULL or pg_repack).
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from opportunity_radar.matching.text import trim_stored_description
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import get_settings
from opportunity_radar.platform.database import create_database_engine


def trim_all(
    session: Session, *, max_chars: int, batch_size: int = 200, dry_run: bool
) -> dict[str, Any]:
    rows = chars_before = chars_after = 0
    if max_chars <= 0:
        return {"rows": rows, "chars_before": chars_before, "chars_after": chars_after}
    last_id = None
    while True:
        query = (
            select(OpportunityModel.id, OpportunityModel.description)
            .where(func.length(OpportunityModel.description) > max_chars)
            .order_by(OpportunityModel.id)
            .limit(batch_size)
        )
        if last_id is not None:
            query = query.where(OpportunityModel.id > last_id)
        batch = session.execute(query).all()
        if not batch:
            break
        for opportunity_id, description in batch:
            trimmed = trim_stored_description(description, max_chars)
            rows += 1
            chars_before += len(description)
            chars_after += len(trimmed or "")
            if not dry_run:
                session.execute(
                    update(OpportunityModel)
                    .where(OpportunityModel.id == opportunity_id)
                    .values(description=trimmed)
                )
        last_id = batch[-1][0]
        if dry_run:
            session.rollback()
        else:
            session.commit()
    return {"rows": rows, "chars_before": chars_before, "chars_after": chars_after}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        print(
            trim_all(
                session,
                max_chars=get_settings().stored_description_max_chars,
                dry_run=args.dry_run,
            )
        )


if __name__ == "__main__":
    main()
