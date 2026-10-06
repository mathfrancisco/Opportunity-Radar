"""Re-extract the skills of opportunities still tagged by an older skill taxonomy.

    # what would change (writes nothing)
    python scripts/retag_skills.py
    # write it, 500 postings per transaction
    python scripts/retag_skills.py --apply
    python scripts/retag_skills.py --limit 1000
    # also the postings with no skill at all (a taxonomy that gained entries)
    python scripts/retag_skills.py --include-untagged

The taxonomy version is stored with each skill, so the postings normalized before a taxonomy
change keep the old skills until this runs. Only skills, `search_skills` and the posting's
version change; a changed posting is evaluated again by the worker. A second run reports zero
changes. Run the dry-run first, on a copy.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import retag_skills
from opportunity_radar.platform.database import create_database_engine


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry-run")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None, help="at most N postings")
    parser.add_argument(
        "--include-untagged",
        action="store_true",
        help="also read the postings that have no skill row",
    )
    args = parser.parse_args(argv)
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        report = retag_skills(
            session,
            batch_size=args.batch_size,
            limit=args.limit,
            apply=args.apply,
            include_untagged=args.include_untagged,
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
