"""Let `normalize_pending` redo items that failed for a cause already corrected.

Card F48-03: the Remotive `publication_date` has no timezone, and the normalizer used to
reject the whole item for it (`INVALID_COLLECTED_ITEM_V1`, "must include a timezone").
`pending_raw_item_ids` only returns raw items without a result for the current normalizer
version, so the `FAILED` rows never retried on their own.

Affected items are those whose `FAILED` result is `INVALID_COLLECTED_ITEM_V1` with that
timezone error. The real run deletes exactly those result rows (a `FAILED` result owns no
opportunity or occurrence, so nothing else cascades) and never touches raw items, so the
next `normalize_pending` pass recreates them. `--dry-run` lists the items and writes
nothing. Idempotent: a second run finds nothing left to delete.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine

_AFFECTED = """
FROM opportunities.normalization_result nr
JOIN acquisition.raw_item ri ON ri.id = nr.raw_item_id
JOIN acquisition.source_definition sd ON sd.id = ri.source_definition_id
WHERE nr.status = 'FAILED'
  AND nr.reasons @> CAST('[{"code": "INVALID_COLLECTED_ITEM_V1"}]' AS jsonb)
  AND nr.error_summary LIKE '%must include a timezone%'
"""


def backfill(session: Session, *, dry_run: bool) -> dict[str, Any]:
    affected = [
        {
            "normalization_result_id": str(row.id),
            "raw_item_id": str(row.raw_item_id),
            "source": row.source_name,
            "external_id": row.external_id,
            "normalizer_version": row.normalizer_version,
        }
        for row in session.execute(
            text(
                "SELECT nr.id, nr.raw_item_id, nr.normalizer_version, "
                "sd.name AS source_name, ri.external_id "
                f"{_AFFECTED} ORDER BY sd.name, ri.external_id"
            )
        )
    ]
    deleted = 0
    if not dry_run and affected:
        deleted = session.execute(
            text(
                "DELETE FROM opportunities.normalization_result "
                f"WHERE id IN (SELECT nr.id {_AFFECTED})"
            )
        ).rowcount
        session.commit()
    return {"affected": len(affected), "deleted": deleted, "items": affected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        result = backfill(session, dry_run=args.dry_run)
    for item in result["items"]:
        print(f"{item['source']}\t{item['external_id']}\t{item['raw_item_id']}")
    print({key: value for key, value in result.items() if key != "items"})


if __name__ == "__main__":
    main()
