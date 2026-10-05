"""Prune match assessments that a newer one superseded long enough ago.

Every re-evaluation inserts a new `match_assessment` (plus its factor rows) instead of
updating, so the table grows by roughly one row per open posting per currency change. An
assessment is superseded when a newer one exists for the same posting and profile version
(the key the matching code scopes currency to); it is eligible once that newer one is itself
older than the retention window.

The latest assessment per posting and profile version is never superseded, so it is always
kept. Beyond that, the assessments a person or the model did work on are kept regardless of
age. References to `matching.match_assessment`:

  * `match_factor` (FK, CASCADE): a pure derivative, deleted with its assessment.
  * `match_analysis` (FK, CASCADE): AI analysis history, keeps the assessment.
  * `match_analysis_claim` (FK, CASCADE): a live lease over an analysis, keeps the assessment.
  * `matching.current_assessment` (FK, RESTRICT): the pointer to the newest assessment per
    posting and profile version, chosen by `(opportunity_version, assessed_at, id)`. A
    pointed assessment is never selected, so the RESTRICT can never abort a batch. That
    ordering can differ from the `created_at` ordering used for "superseded" (a backfill
    written late); then the pointed row is kept as well as the `created_at`-latest one,
    which leaves a posting with an extra row, never a failing batch.
  * `crm.application_process`: no FK, linked by (opportunity, profile version), keeps
    the assessments of that pair because the candidacy was decided on them.

Each batch is its own short transaction and locks its rows with SKIP LOCKED, so a concurrent
analysis (which takes a share lock on the assessment) is skipped instead of raced.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from opportunity_radar.platform.logging import get_logger

DEFAULT_ASSESSMENT_RETENTION_DAYS = 7

logger = get_logger("opportunity_radar.operations.assessment_retention")

_HAS_ANALYSIS = (
    "EXISTS (SELECT 1 FROM matching.match_analysis x WHERE x.assessment_id = a.id)"
)
_HAS_CLAIM = (
    "EXISTS (SELECT 1 FROM matching.match_analysis_claim c WHERE c.assessment_id = a.id)"
)
_IS_CURRENT = (
    "EXISTS (SELECT 1 FROM matching.current_assessment w WHERE w.assessment_id = a.id)"
)
_HAS_APPLICATION = (
    "EXISTS (SELECT 1 FROM crm.application_process p "
    "WHERE p.opportunity_id = a.opportunity_id "
    "AND p.profile_version_id = a.profile_version_id)"
)
# A newer assessment of the same posting and profile version, itself older than the cutoff.
_SUPERSEDED = (
    "EXISTS (SELECT 1 FROM matching.match_assessment n "
    "WHERE n.opportunity_id = a.opportunity_id "
    "AND n.profile_version_id = a.profile_version_id "
    "AND n.created_at > a.created_at AND n.created_at < :cutoff)"
)
_UNPROTECTED = (
    f"NOT {_HAS_ANALYSIS} AND NOT {_HAS_CLAIM} AND NOT {_HAS_APPLICATION} "
    f"AND NOT {_IS_CURRENT}"
)

_COUNT_CANDIDATES = f"""
SELECT count(*),
       count(*) FILTER (WHERE {_HAS_ANALYSIS}),
       count(*) FILTER (WHERE {_HAS_CLAIM}),
       count(*) FILTER (WHERE {_HAS_APPLICATION}),
       count(*) FILTER (WHERE {_IS_CURRENT}),
       count(*) FILTER (WHERE {_UNPROTECTED})
FROM matching.match_assessment a
WHERE {_SUPERSEDED}
"""

_LOCK_BATCH = f"""
SELECT a.id FROM matching.match_assessment a
WHERE {_SUPERSEDED} AND {_UNPROTECTED}
ORDER BY a.created_at
LIMIT :batch_size
FOR UPDATE OF a SKIP LOCKED
"""

# Open postings are the ones the Inbox can still show; the spec's average is over them.
_OPEN_AVERAGE = """
SELECT count(a.id), count(DISTINCT a.opportunity_id)
FROM matching.match_assessment a
JOIN opportunities.opportunity o ON o.id = a.opportunity_id
WHERE o.lifecycle_status NOT IN ('CLOSED', 'ARCHIVED', 'REJECTED')
"""


@dataclass(frozen=True, slots=True)
class AssessmentPruneReport:
    dry_run: bool
    retention_days: int
    cutoff: datetime
    #: Superseded for longer than the window, before any exception. The `kept_*` counts
    #: overlap: an assessment with an analysis and an application counts in both.
    candidates: int
    kept_with_analysis: int
    kept_with_claim: int
    kept_with_application: int
    kept_as_current: int
    #: Candidates no exception protects; what an unbounded run would delete.
    deletable: int
    #: Deleted by this run, or what this run would delete under the batch bound on a dry run.
    deleted: int
    rows_before: int
    rows_remaining: int
    avg_per_open_posting_before: float | None
    avg_per_open_posting_after: float | None

    def as_dict(self) -> dict[str, Any]:
        report = asdict(self)
        report["cutoff"] = self.cutoff.isoformat()
        return report


def prune_superseded_assessments(
    engine: Engine,
    *,
    retention_days: int = DEFAULT_ASSESSMENT_RETENTION_DAYS,
    batch_size: int = 500,
    max_batches: int | None = None,
    dry_run: bool = True,
    now: datetime | None = None,
) -> AssessmentPruneReport:
    """Delete up to `batch_size * max_batches` prunable assessments, one transaction per batch.

    `dry_run` (the default) counts without deleting. `max_batches=None` runs until nothing
    prunable is left.
    """
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    batch_size = max(1, batch_size)
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    with Session(engine) as session:
        candidates, with_analysis, with_claim, with_application, as_current, deletable = (
            session.execute(text(_COUNT_CANDIDATES), {"cutoff": cutoff}).one()
        )
        rows_before, avg_before = _table_state(session)
    bound = None if max_batches is None else batch_size * max_batches
    deleted = deletable if bound is None else min(deletable, bound)
    if not dry_run:
        deleted = 0
        batches = 0
        while max_batches is None or batches < max_batches:
            removed = _delete_batch(engine, cutoff, batch_size)
            if not removed:
                break
            deleted += removed
            batches += 1
    with Session(engine) as session:
        rows_remaining, avg_after = _table_state(session)
    if not dry_run:
        logger.info(
            "match assessments pruned",
            extra={
                "job": "prune-match-assessments",
                "deleted": deleted,
                "retention_days": retention_days,
                "cutoff": cutoff.isoformat(),
            },
        )
    return AssessmentPruneReport(
        dry_run=dry_run,
        retention_days=retention_days,
        cutoff=cutoff,
        candidates=candidates,
        kept_with_analysis=with_analysis,
        kept_with_claim=with_claim,
        kept_with_application=with_application,
        kept_as_current=as_current,
        deletable=deletable,
        deleted=deleted,
        rows_before=rows_before,
        rows_remaining=rows_remaining,
        avg_per_open_posting_before=avg_before,
        avg_per_open_posting_after=None if dry_run else avg_after,
    )


def _delete_batch(engine: Engine, cutoff: datetime, batch_size: int) -> int:
    with Session(engine) as session, session.begin():
        ids = [
            row[0]
            for row in session.execute(
                text(_LOCK_BATCH), {"cutoff": cutoff, "batch_size": batch_size}
            )
        ]
        if not ids:
            return 0
        # Both tables carry an immutability trigger on DELETE; this setting, scoped to the
        # transaction, is the only thing that lets a delete through it.
        session.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
        # Factors first, explicitly, rather than leaning on the FK cascade.
        session.execute(
            text("DELETE FROM matching.match_factor WHERE assessment_id = ANY(:ids)"),
            {"ids": ids},
        )
        session.execute(
            text("DELETE FROM matching.match_assessment WHERE id = ANY(:ids)"),
            {"ids": ids},
        )
        return len(ids)


def _table_state(session: Session) -> tuple[int, float | None]:
    total = session.execute(
        text("SELECT count(*) FROM matching.match_assessment")
    ).scalar_one()
    open_rows, open_postings = session.execute(text(_OPEN_AVERAGE)).one()
    average = round(open_rows / open_postings, 2) if open_postings else None
    return total, average


__all__ = [
    "DEFAULT_ASSESSMENT_RETENTION_DAYS",
    "AssessmentPruneReport",
    "prune_superseded_assessments",
]
