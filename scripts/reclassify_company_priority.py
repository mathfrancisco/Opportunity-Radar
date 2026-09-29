"""Move companies that are `low` only because of research maturity back to `normal`.

Card F48-14. The research importer used to write `priority = low` for every company whose
ATS was not identified yet, so priority meant "how mature is our research" instead of "how
much does the user care". Priority is now the user's interest and maturity lives in
`company.research_confidence`.

A company is reclassified only when all of these hold:

* `priority = low` and `research_confidence = low` (the importer's own output);
* `version = 1`: `CompanyRegistration.update` bumps `version` on every edit by the user, and
  the importer never does, so this is the reliable "nobody touched it" marker. `updated_at`
  is not usable, because the importer moves it too.

Companies the user edited (`version > 1`) are counted and left alone, as are `high` and
`blocked` ones. Use `--dry-run` first: it reports what would change and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

_ELIGIBLE = (
    Company.priority == "low",
    Company.research_confidence == "low",
    Company.version == 1,
)


def reclassify_company_priority(session: Session, *, dry_run: bool) -> dict[str, Any]:
    eligible = session.scalar(select(func.count()).select_from(Company).where(*_ELIGIBLE))
    kept_user_edited = session.scalar(
        select(func.count())
        .select_from(Company)
        .where(Company.priority == "low", Company.version > 1)
    )
    changed = 0
    if not dry_run:
        changed = session.execute(
            update(Company).where(*_ELIGIBLE).values(priority="normal")
        ).rowcount
    return {
        "dry_run": dry_run,
        "eligible": eligible,
        "reclassified": changed,
        "kept_low_user_edited": kept_user_edited,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = reclassify_company_priority(session, dry_run=args.dry_run)
        if not args.dry_run:
            session.commit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
