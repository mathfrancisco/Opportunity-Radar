"""B7 measurement: how many opportunities are the same job posted in more than one source.

Read-only and counts only (no titles, companies or owner identity). A *residual* pair is
two root opportunities that satisfy the R55-E4 strong rule (same company, title and
location, published within 7 days) yet were not attached to one another, so every residual
row is a duplicate the auto-merge missed or that predates it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.duplicates import CROSS_SOURCE_WINDOW_DAYS

_COMPANY_KEY = "coalesce(o.canonical_company_id::text, o.normalized_company_name)"

_TOTALS = """
SELECT
  count(*) AS root_opportunities,
  count(*) FILTER (WHERE (
    SELECT count(DISTINCT s.source_definition_id)
    FROM opportunities.source_occurrence s WHERE s.opportunity_id = o.id) >= 2
  ) AS multi_source_opportunities
FROM opportunities.opportunity o
WHERE o.duplicate_of IS NULL
"""

# A row is redundant when an older-keyed root opportunity strongly matches it. Counting the
# redundant rows (not the pairs) is the number of opportunities a perfect merge would remove.
_RESIDUAL = f"""
SELECT count(*) AS residual_duplicate_rows FROM opportunities.opportunity b
WHERE b.duplicate_of IS NULL
  AND b.normalized_location IS NOT NULL AND b.published_at IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM opportunities.opportunity o
    WHERE o.duplicate_of IS NULL AND o.id < b.id
      AND {_COMPANY_KEY} = coalesce(b.canonical_company_id::text, b.normalized_company_name)
      AND o.normalized_title = b.normalized_title
      AND o.normalized_location = b.normalized_location
      AND o.published_at IS NOT NULL
      AND abs(extract(epoch FROM (o.published_at - b.published_at))) <= :window_seconds)
"""

_CANDIDATES = """
SELECT status, count(*) FROM opportunities.duplicate_candidate GROUP BY status
"""


@dataclass(frozen=True, slots=True)
class CrossSourceDuplicateReport:
    window_days: int
    root_opportunities: int
    multi_source_opportunities: int
    residual_duplicate_rows: int
    duplicate_candidates: dict[str, int]

    @property
    def residual_rate(self) -> float:
        """Share of root opportunities that are a missed duplicate of another one."""
        total = self.root_opportunities
        return round(self.residual_duplicate_rows / total, 4) if total else 0.0

    @property
    def merged_rate(self) -> float:
        """Share of root opportunities that already carry occurrences from 2+ sources."""
        total = self.root_opportunities
        return round(self.multi_source_opportunities / total, 4) if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        report = asdict(self)
        report["residual_rate"] = self.residual_rate
        report["merged_rate"] = self.merged_rate
        return report


def measure_cross_source_duplicates(session: Session) -> CrossSourceDuplicateReport:
    totals = session.execute(text(_TOTALS)).one()
    residual = session.execute(
        text(_RESIDUAL), {"window_seconds": CROSS_SOURCE_WINDOW_DAYS * 86400}
    ).scalar_one()
    candidates = {row[0]: int(row[1]) for row in session.execute(text(_CANDIDATES))}
    return CrossSourceDuplicateReport(
        window_days=CROSS_SOURCE_WINDOW_DAYS,
        root_opportunities=int(totals.root_opportunities),
        multi_source_opportunities=int(totals.multi_source_opportunities),
        residual_duplicate_rows=int(residual),
        duplicate_candidates=dict(sorted(candidates.items())),
    )
