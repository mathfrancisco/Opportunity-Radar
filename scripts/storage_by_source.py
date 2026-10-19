"""Per-source storage and off-target share of stored opportunities (card R55-B5).

Read-only: one `READ ONLY` transaction, counts and byte sizes only, no posting content and
no owner identity. For each source it prints the stored raw items and payload bytes, how many
opportunities came from it, how many of those are off-target for the active profile (the same
test the shorter retention uses: known area outside the target areas, or only countries
outside the profile's countries), and what the ingestion prefilter kept out in the last
`--days` days (`source_run.skipped_off_target`).

Usage: DATABASE_URL=... WORKER_OWNER_SUB=... python scripts/storage_by_source.py [--days 7]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.prefilter import owner_target_scope
from opportunity_radar.operations.opportunity_retention import off_target_predicate
from opportunity_radar.platform.database import create_database_engine

_STORAGE = """
SELECT sd.source_type, sd.name,
       count(r.id) AS raw_items,
       coalesce(sum(pg_column_size(p.payload)), 0)::bigint AS payload_bytes
FROM acquisition.source_definition sd
LEFT JOIN acquisition.raw_item r ON r.source_definition_id = sd.id
LEFT JOIN acquisition.raw_item_payload p ON p.raw_item_id = r.id
GROUP BY sd.id, sd.source_type, sd.name
"""

_OPPORTUNITIES = f"""
SELECT sd.source_type, sd.name,
       count(DISTINCT o.id) AS opportunities,
       count(DISTINCT o.id) FILTER (WHERE {off_target_predicate("o")}) AS off_target
FROM acquisition.source_definition sd
JOIN opportunities.source_occurrence s ON s.source_definition_id = sd.id
JOIN opportunities.opportunity o ON o.id = s.opportunity_id
GROUP BY sd.id, sd.source_type, sd.name
"""

_PREFILTERED = """
SELECT sd.source_type, sd.name,
       coalesce(sum(sr.items_seen), 0)::bigint AS items_seen,
       coalesce(sum(sr.skipped_off_target), 0)::bigint AS prefiltered
FROM acquisition.source_definition sd
JOIN acquisition.source_run sr ON sr.source_definition_id = sd.id
WHERE sr.started_at >= :since
GROUP BY sd.id, sd.source_type, sd.name
"""


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = os.environ.get("WORKER_OWNER_SUB", "").strip()
    if not owner_sub:
        raise SystemExit("WORKER_OWNER_SUB is not set: no profile defines off-target")
    try:
        families, countries = owner_target_scope(engine, owner_sub)
    except Exception as error:  # noqa: BLE001 - zero off-target would be misleading
        raise SystemExit(
            f"could not read the active profile ({type(error).__name__}): "
            "off-target counts would be wrong, aborting"
        ) from None
    since = datetime.now(UTC) - timedelta(days=args.days)
    sources: dict[tuple[str, str], dict[str, int | str]] = {}
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        queries = (
            (_STORAGE, {}),
            (_OPPORTUNITIES, {"families": list(families), "countries": list(countries)}),
            (_PREFILTERED, {"since": since}),
        )
        for sql, params in queries:
            for row in session.execute(text(sql), params).mappings():
                entry = sources.setdefault(
                    (row["source_type"], row["name"]),
                    {"source_type": row["source_type"], "source_name": row["name"]},
                )
                entry.update(
                    {
                        key: int(value)
                        for key, value in row.items()
                        if key not in {"source_type", "name"}
                    }
                )
    rows = sorted(sources.values(), key=lambda row: -int(row.get("payload_bytes", 0)))
    print(
        json.dumps(
            {
                "days": args.days,
                "target_role_family_count": len(families),
                "target_country_count": len(countries),
                "sources": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
