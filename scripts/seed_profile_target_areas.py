"""Seed the active profile's target areas with the technical proxy (card F48-13, decision 1).

Writes `target_role_families` = SOFTWARE_ENGINEERING, DATA, INFRASTRUCTURE, SECURITY as a new
active profile version, and only when the active profile has none. An area list the user has
already edited is never touched, and skills and target titles are never invented: the profile
screen asks the user for them.

    python scripts/seed_profile_target_areas.py --dry-run   # report, write nothing
    python scripts/seed_profile_target_areas.py             # write when the field is empty
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace

from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import ProfileNotFoundError, ProfileSnapshot
from opportunity_radar.profile.service import ProfileService

SEED_ROLE_FAMILIES: tuple[str, ...] = (
    "SOFTWARE_ENGINEERING",
    "DATA",
    "INFRASTRUCTURE",
    "SECURITY",
)


def seeded_snapshot(snapshot: ProfileSnapshot) -> ProfileSnapshot | None:
    """The snapshot with the seed areas, or None when the user already has areas."""
    if snapshot.preferences.target_role_families:
        return None
    return replace(
        snapshot,
        preferences=replace(snapshot.preferences, target_role_families=SEED_ROLE_FAMILIES),
    )


def seed(session: Session, *, dry_run: bool) -> dict[str, object]:
    service = ProfileService(session)
    try:
        active = service.get_active()
    except ProfileNotFoundError:
        return {"result": "skipped: no active profile"}
    updated = seeded_snapshot(active.snapshot)
    if updated is None:
        return {
            "result": "skipped: target areas already set",
            "target_role_families": list(active.snapshot.preferences.target_role_families),
        }
    if dry_run:
        return {"result": "would write", "target_role_families": list(SEED_ROLE_FAMILIES)}
    created = service.create_active_version(updated, active.profile_lock_version)
    return {
        "result": "written",
        "profile_version_id": str(created.id),
        "target_role_families": list(SEED_ROLE_FAMILIES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = seed(session, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
