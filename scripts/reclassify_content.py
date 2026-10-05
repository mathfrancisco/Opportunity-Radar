"""Reclassify seniority, work mode and allowed countries of existing opportunities (F50-02).

    # what would change with the rules enabled in the environment (writes nothing)
    python scripts/reclassify_content.py
    # write it, 500 postings per transaction
    python scripts/reclassify_content.py --apply
    # explicit areas, or every posting
    python scripts/reclassify_content.py --role-families DATA,SOFTWARE_ENGINEERING
    python scripts/reclassify_content.py --all --limit 1000

The rules come from `CONTENT_CLASSIFICATION_ENABLED_RULES` / `CONTENT_CLASSIFICATION_V4_ENABLED`;
with none enabled the script refuses to run, because recomputing with every rule off would
undo values a previous run wrote. A posting's version goes up once per run, and only when a
value changed, so a second run reports zero changes. Run the dry-run first, on a copy.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from sqlalchemy.orm import Session

from opportunity_radar.acquisition.service import active_profile_target_role_families
from opportunity_radar.opportunities.role_family import RoleFamily
from opportunity_radar.opportunities.service import reclassify_content
from opportunity_radar.platform.config import get_settings
from opportunity_radar.platform.database import create_database_engine


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry-run")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None, help="at most N postings")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--role-families",
        help="comma separated; default: the active profile's target role families",
    )
    scope.add_argument("--all", action="store_true", help="every posting with a description")
    args = parser.parse_args(argv)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")
    rules = get_settings().content_rules
    if not rules:
        parser.error(
            "no content rule is enabled: set CONTENT_CLASSIFICATION_ENABLED_RULES "
            "(or CONTENT_CLASSIFICATION_V4_ENABLED)."
        )

    with Session(create_database_engine(database_url)) as session:
        role_families: tuple[str, ...] | None
        if args.all:
            role_families = None
        elif args.role_families:
            role_families = tuple(
                item.strip().upper() for item in args.role_families.split(",") if item.strip()
            )
            unknown = sorted(set(role_families) - {family.value for family in RoleFamily})
            if unknown:
                parser.error(f"unknown role family: {', '.join(unknown)}")
        else:
            role_families = active_profile_target_role_families(session)()
            if not role_families:
                parser.error(
                    "the active profile has no target role families: "
                    "pass --role-families or --all."
                )
        report = reclassify_content(
            session,
            rules=rules,
            role_families=role_families,
            batch_size=args.batch_size,
            limit=args.limit,
            apply=args.apply,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
