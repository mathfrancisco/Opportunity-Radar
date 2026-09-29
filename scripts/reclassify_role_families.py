"""Retroactively classify the area (`role-family-v1`) of existing opportunities.

Card F17-02. Run after the `role_family` migration, and again whenever the rules change
version: it only touches rows whose `role_family_version` is not the current one, so it is
safe to re-run.
"""

from __future__ import annotations

import argparse
import json
import os

from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import reclassify_role_families
from opportunity_radar.platform.database import create_database_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = reclassify_role_families(session, batch_size=args.batch_size)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
