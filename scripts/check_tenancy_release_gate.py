"""Release gate for databases at migration 0069 and later.

The pipeline variable is intentionally unset until Package 3 has integrated and proven
owner-scoped API routes. This gate blocks GHCR image publication through pipeline.yml;
it cannot prevent operators from deploying an older image through an unrelated path.
"""

from __future__ import annotations

import os
import sys


def owner_scoped_api_is_proven(value: str | None) -> bool:
    """Require an explicit repository-level release signal; unset is blocked."""
    return value is not None and value.strip().lower() == "true"


def main() -> int:
    if not owner_scoped_api_is_proven(os.environ.get("TENANCY_OWNER_API_READY")):
        print(
            "BLOCKED: owner-scoped API evidence is required before publishing images "
            "for databases at migration 0069 or later. Complete Package 3, review its "
            "two-user authorization tests, then set TENANCY_OWNER_API_READY=true "
            "in repository Actions variables."
        )
        return 1
    print("Owner-scoped API release gate: ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
