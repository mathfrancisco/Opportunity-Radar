"""Measure the cross-source duplicate rate (card R55-E4, measurement B7).

    python scripts/measure_cross_source_duplicates.py

Read-only. Prints JSON with counts and rates only: `multi_source_opportunities` are jobs
already attached to 2+ sources, `residual_duplicate_rows` are opportunities that still
match another one under the R55-E4 strong rule and should be zero after the merge ships.
"""

from __future__ import annotations

import json
import os

from sqlalchemy.orm import Session

from opportunity_radar.operations.cross_source_duplicates import measure_cross_source_duplicates
from opportunity_radar.platform.database import create_database_engine


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        print(json.dumps(measure_cross_source_duplicates(session).as_dict(), indent=2))


if __name__ == "__main__":
    main()
