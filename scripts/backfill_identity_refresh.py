"""Let `normalize_pending` redo identity changes that were parked as `REVIEW_REQUIRED`.

Card F48-09: the same source `external_id` arriving with a different fingerprint used to end
`REVIEW_REQUIRED` (`EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`) without refreshing the
opportunity, so its derived fields stayed stale. Now that identity is refreshed in place,
the parked rows only need to be normalized again.

Affected rows are current-version results with that reason whose raw item is still the one
supplying the occurrence's content. The real run deletes exactly those result rows (the
opportunity and occurrence stay untouched, raw items are never touched), so the next
`normalize_pending` pass recreates them under the new rule. A row whose fingerprint is now
owned by another opportunity comes back as `REVIEW_REQUIRED` again, which is intended.
`--dry-run` lists the rows and writes nothing. Idempotent: a second run finds nothing left.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from opportunity_radar.platform.database import create_database_engine

_AFFECTED = """
FROM opportunities.normalization_result nr
JOIN acquisition.raw_item ri ON ri.id = nr.raw_item_id
JOIN acquisition.source_definition sd ON sd.id = ri.source_definition_id
JOIN opportunities.source_occurrence so ON so.raw_item_id = nr.raw_item_id
WHERE nr.status = 'REVIEW_REQUIRED'
  AND nr.normalizer_version = :normalizer_version
  AND nr.reasons @> CAST('[{"code": "EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED"}]' AS jsonb)
"""


def backfill(session: Session, *, dry_run: bool) -> dict[str, Any]:
    params = {"normalizer_version": NORMALIZER_VERSION}
    affected = [
        {
            "normalization_result_id": str(row.id),
            "raw_item_id": str(row.raw_item_id),
            "opportunity_id": str(row.opportunity_id),
            "source": row.source_name,
            "external_id": row.external_id,
        }
        for row in session.execute(
            text(
                "SELECT nr.id, nr.raw_item_id, nr.opportunity_id, "
                "sd.name AS source_name, ri.external_id "
                f"{_AFFECTED} ORDER BY sd.name, ri.external_id"
            ),
            params,
        )
    ]
    deleted = 0
    if not dry_run and affected:
        deleted = session.execute(
            text(
                "DELETE FROM opportunities.normalization_result "
                f"WHERE id IN (SELECT nr.id {_AFFECTED})"
            ),
            params,
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
