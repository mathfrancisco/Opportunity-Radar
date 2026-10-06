"""Recompute the seniority of existing opportunities with the current mapping (F52-02).

    # what would change (writes nothing)
    python scripts/retag_seniority.py
    # write it, 500 postings per transaction
    python scripts/retag_seniority.py --apply
    python scripts/retag_seniority.py --limit 1000

The mapping version is stored in the seniority evidence, so the postings normalized before a
mapping change keep the old level until this runs. Only the level, its evidence and the
posting's version change; a posting whose level changed is evaluated again by the worker. The
content rules enabled in the environment are honoured, so a level a description rule decided
is not undone. A second run reports zero changes. Run the dry-run first, on a copy.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import retag_seniority
from opportunity_radar.platform.config import get_settings
from opportunity_radar.platform.database import create_database_engine


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry-run")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int, default=None, help="at most N postings")
    args = parser.parse_args(argv)
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        report = retag_seniority(
            session,
            rules=get_settings().content_rules,
            batch_size=args.batch_size,
            limit=args.limit,
            apply=args.apply,
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
