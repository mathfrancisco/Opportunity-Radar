"""Link opportunities that lost their company to a proposed (CompanySource-less) source.

Sources proposed by F20-53/60/71 have no `CompanySource`, so normalization stored
`canonical_company_id = NULL`. New items now resolve the company by the source's
configured `company_name`; this script repairs the rows written before that fix.

Only exact matches are linked: the opportunity's `normalized_company_name` must equal
the (unique) `Company.normalized_name`. Rows that already have a company are never
touched, so the script is idempotent. `--dry-run` reports without writing.
"""

from __future__ import annotations

import argparse
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine

_CANDIDATES = """
FROM opportunities.opportunity o
JOIN company_radar.company c ON c.normalized_name = o.normalized_company_name
WHERE o.canonical_company_id IS NULL
"""


def backfill(session: Session, *, dry_run: bool) -> dict[str, int]:
    before = session.execute(
        text("SELECT count(*) FROM opportunities.opportunity WHERE canonical_company_id IS NULL")
    ).scalar_one()
    linkable = session.execute(text(f"SELECT count(*) {_CANDIDATES}")).scalar_one()
    updated = 0
    if not dry_run:
        updated = session.execute(
            text(
                "UPDATE opportunities.opportunity o SET canonical_company_id = c.id "
                "FROM company_radar.company c "
                "WHERE o.canonical_company_id IS NULL "
                "AND c.normalized_name = o.normalized_company_name"
            )
        ).rowcount
        session.commit()
    return {"null_before": before, "linkable": linkable, "updated": updated}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        print(backfill(session, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
