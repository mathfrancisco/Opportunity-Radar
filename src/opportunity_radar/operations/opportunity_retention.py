"""Daily retention of old opportunities and everything that hangs off them (card R55-E2).

An opportunity is old when `coalesce(published_at, first_seen_at)` is earlier than the
cutoff (`now - retention_days`). Old opportunities are deleted together with their
dependents, oldest first, in batches; each batch is its own short transaction and locks its
opportunities with `FOR UPDATE SKIP LOCKED`, so a concurrent writer is skipped instead of
raced and a stopped run loses at most the batch in flight.

Kept regardless of age:

  * an opportunity with any `crm.application_process` (FK RESTRICT; the candidacy is the
    person's own record);
  * an opportunity with any `relevance_mark` where `relevant` is true: the owner said this
    posting mattered, and a later "not relevant" mark does not undo that for retention.

Deleted with an old opportunity, explicitly where an FK is RESTRICT, by cascade otherwise:
`current_assessment`, `match_assessment` (+ `match_factor`, `match_analysis`,
`match_analysis_claim`), `source_occurrence`, `source_occurrence_observation` of those
occurrences, `duplicate_candidate`, embeddings, `relevance_mark` (only not-relevant ones can
exist at that point), `normalization_result`, and the compensation, skill, suggestion and
defer rows. A `raw_item` (and its `raw_item_payload`) goes only when nothing else still
references it: no remaining occurrence, normalization result or compensation row.

Nothing else is touched. Raw items that were never linked to an old opportunity (for
example a collection that failed to normalise) are out of scope here. Rows are tenanted by
`owner_sub`, but age is global: the delete never reads or writes `owner_sub`.

The same pass also purges `platform.ai_call_record` older than its own window and expired
`acquisition.tavily_extract_cache` rows.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import CursorResult, Engine, text
from sqlalchemy.orm import Session

from opportunity_radar.platform.logging import get_logger

DEFAULT_OPPORTUNITY_RETENTION_DAYS = 7
DEFAULT_AI_CALL_RECORD_RETENTION_DAYS = 7
JOB_NAME = "opportunity_retention"
#: Tracks the once-a-day *dry run* the pipeline does while applying is not enabled, apart
#: from the applied runs so that one never counts as the other.
DRY_RUN_JOB_NAME = "opportunity_retention_dry_run"

logger = get_logger("opportunity_radar.operations.opportunity_retention")



def _age(a: str) -> str:
    return f"coalesce({a}.published_at, {a}.first_seen_at)"


def _has_application(a: str) -> str:
    return f"EXISTS (SELECT 1 FROM crm.application_process p WHERE p.opportunity_id = {a}.id)"


def _has_relevant_mark(a: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM opportunities.relevance_mark m "
        f"WHERE m.opportunity_id = {a}.id AND m.relevant)"
    )


def _protected(a: str) -> str:
    return f"{_has_application(a)} OR {_has_relevant_mark(a)}"


_AGE = _age("o")
_HAS_APPLICATION = _has_application("o")
_HAS_RELEVANT_MARK = _has_relevant_mark("o")
# `duplicate_of` is SET NULL: deleting a survivor would silently orphan a duplicate that
# stays. A survivor is kept while any opportunity pointing at it is itself kept.
_HAS_KEPT_DUPLICATE = (
    "EXISTS (SELECT 1 FROM opportunities.opportunity k WHERE k.duplicate_of = o.id AND ("
    f"{_age('k')} >= :cutoff OR {_protected('k')}))"
)
_ELIGIBLE = (
    f"{_AGE} < :cutoff AND NOT ({_protected('o')}) AND NOT {_HAS_KEPT_DUPLICATE}"
)

_LOCK_BATCH = f"""
SELECT o.id FROM opportunities.opportunity o
WHERE {_ELIGIBLE}
ORDER BY {_AGE}, o.id
LIMIT :batch_size
FOR UPDATE OF o SKIP LOCKED
"""

# Second statement of a batch: a fresh snapshot of the rows the lock statement returned, so
# an application or mark committed between the two is honoured.
_RECHECK = f"""
SELECT o.id FROM opportunities.opportunity o
WHERE o.id = ANY(:ids) AND NOT ({_protected("o")}) AND NOT {_HAS_KEPT_DUPLICATE}
"""

# Tables that reference the opportunity directly and go away with it (cascade or explicit).
_BY_OPPORTUNITY: tuple[tuple[str, str], ...] = (
    ("opportunity_embedding", "opportunities.opportunity_embedding"),
    ("opportunity_embedding_failure", "opportunities.opportunity_embedding_failure"),
    ("opportunity_compensation", "opportunities.opportunity_compensation"),
    ("opportunity_skill", "opportunities.opportunity_skill"),
    ("field_suggestion", "opportunities.field_suggestion"),
    ("ai_suggestion_defer", "platform.ai_suggestion_defer"),
    ("relevance_mark", "opportunities.relevance_mark"),
    ("source_occurrence", "opportunities.source_occurrence"),
    ("normalization_result", "opportunities.normalization_result"),
    ("current_assessment", "matching.current_assessment"),
    ("match_assessment", "matching.match_assessment"),
)

_STILL_REFERENCED = """
EXISTS (SELECT 1 FROM opportunities.source_occurrence s WHERE s.raw_item_id = r.id)
OR EXISTS (SELECT 1 FROM opportunities.normalization_result n WHERE n.raw_item_id = r.id)
OR EXISTS (SELECT 1 FROM opportunities.opportunity_compensation c WHERE c.raw_item_id = r.id)
"""


@dataclass(slots=True)
class OpportunityRetentionReport:
    dry_run: bool
    retention_days: int
    cutoff: datetime | None
    #: Opportunities older than the cutoff that an exception protects.
    kept_with_application: int = 0
    kept_with_relevant_mark: int = 0
    #: Rows deleted per table (or, on a dry run, that an unbounded run would delete).
    rows: dict[str, int] = field(default_factory=dict)
    batches: int = 0
    #: True when the run reached the end of what was eligible; False when a bound
    #: (`max_batches`, the stop callback) ended it first. Only a complete run counts as
    #: "done today" for the pipeline stage.
    complete: bool = True
    stopped: bool = False
    #: Step name -> exception class name, for steps that raised (no messages, no content).
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def opportunities(self) -> int:
        return self.rows.get("opportunity", 0)

    def as_dict(self) -> dict[str, Any]:
        report = asdict(self)
        report["cutoff"] = self.cutoff.isoformat() if self.cutoff else None
        report["rows"] = dict(sorted(self.rows.items()))
        return report


def run_opportunity_retention(
    engine: Engine,
    *,
    retention_days: int = DEFAULT_OPPORTUNITY_RETENTION_DAYS,
    batch_size: int = 500,
    max_batches: int | None = None,
    ai_call_record_retention_days: int | None = None,
    purge_tavily_cache: bool = True,
    dry_run: bool = True,
    should_stop: Callable[[], bool] | None = None,
    now: datetime | None = None,
) -> OpportunityRetentionReport:
    """Delete (or, by default, only count) old opportunities, then the two cache-like tables.

    `retention_days <= 0` skips the opportunity part (the operator's off switch).
    `max_batches=None` runs until nothing eligible is left or `should_stop()` turns true.
    """
    batch_size = max(1, batch_size)
    moment = now or datetime.now(UTC)
    stop = should_stop or (lambda: False)
    cutoff = moment - timedelta(days=retention_days) if retention_days > 0 else None
    report = OpportunityRetentionReport(
        dry_run=dry_run, retention_days=retention_days, cutoff=cutoff
    )
    if cutoff is not None:
        try:
            if dry_run:
                _count_all(engine, cutoff, report)
            else:
                _delete_all(engine, cutoff, batch_size, max_batches, stop, report)
        except Exception as error:
            _fail(report, "opportunities", error)
    # The two purges do not depend on how the opportunity delete went, only on nobody
    # having asked to stop; each captures its own error.
    if not report.stopped:
        _housekeeping(
            engine,
            report,
            ai_days=ai_call_record_retention_days,
            tavily=purge_tavily_cache,
            batch_size=batch_size,
            stop=stop,
            now=moment,
        )
    if not dry_run:
        logger.info(
            "opportunity retention finished",
            extra={
                "job": JOB_NAME,
                "retention_days": retention_days,
                "opportunities_deleted": report.opportunities,
                "batches": report.batches,
                "complete": report.complete,
            },
        )
    return report


def _fail(report: OpportunityRetentionReport, step: str, error: Exception) -> None:
    report.errors[step] = type(error).__name__
    report.complete = False
    logger.warning(
        "opportunity retention step failed",
        extra={"job": JOB_NAME, "step": step, "error": type(error).__name__},
    )


def _delete_all(
    engine: Engine,
    cutoff: datetime,
    batch_size: int,
    max_batches: int | None,
    stop: Callable[[], bool],
    report: OpportunityRetentionReport,
) -> None:
    while True:
        if max_batches is not None and report.batches >= max_batches:
            report.complete = False
            return
        if stop():
            report.complete = False
            report.stopped = True
            return
        locked, counts = _delete_batch(engine, cutoff, batch_size)
        if not locked:
            return
        report.batches += 1
        for table, number in counts.items():
            report.rows[table] = report.rows.get(table, 0) + number


def _delete_batch(
    engine: Engine, cutoff: datetime, batch_size: int
) -> tuple[int, dict[str, int]]:
    """One transaction: lock a batch of old opportunities and delete them with dependents."""
    with Session(engine) as session, session.begin():
        ids = [
            row[0]
            for row in session.execute(
                text(_LOCK_BATCH), {"cutoff": cutoff, "batch_size": batch_size}
            )
        ]
        if not ids:
            return 0, {}
        locked = len(ids)
        ids = [
            row[0]
            for row in session.execute(text(_RECHECK), {"ids": ids, "cutoff": cutoff})
        ]
        if not ids:
            return locked, {}
        params = {"ids": ids}
        counts: dict[str, int] = {}

        def count(label: str, sql: str) -> int:
            number = session.execute(text(sql), params).scalar_one()
            counts[label] = number
            return number

        raw_ids = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT raw_item_id FROM opportunities.source_occurrence "
                    "WHERE opportunity_id = ANY(:ids) "
                    "UNION SELECT raw_item_id FROM opportunities.normalization_result "
                    "WHERE opportunity_id = ANY(:ids)"
                ),
                params,
            )
        ]
        # Pre-count what cascades or is deleted next, so the report names every table.
        for label, table in _BY_OPPORTUNITY:
            if label not in ("match_assessment", "current_assessment"):
                count(label, f"SELECT count(*) FROM {table} WHERE opportunity_id = ANY(:ids)")
        count(
            "duplicate_candidate",
            "SELECT count(*) FROM opportunities.duplicate_candidate "
            "WHERE opportunity_id = ANY(:ids) OR duplicate_opportunity_id = ANY(:ids)",
        )
        counts["match_analysis"] = session.execute(
            text(
                "SELECT count(*) FROM matching.match_analysis x JOIN matching.match_assessment a "
                "ON a.id = x.assessment_id WHERE a.opportunity_id = ANY(:ids)"
            ),
            params,
        ).scalar_one()
        counts["match_analysis_claim"] = session.execute(
            text(
                "SELECT count(*) FROM matching.match_analysis_claim x JOIN "
                "matching.match_assessment a ON a.id = x.assessment_id "
                "WHERE a.opportunity_id = ANY(:ids)"
            ),
            params,
        ).scalar_one()

        counts["current_assessment"] = _rowcount(
            session,
            "DELETE FROM matching.current_assessment WHERE opportunity_id = ANY(:ids)",
            params,
        )
        # The assessment tables carry an immutability trigger on DELETE; this setting,
        # scoped to the transaction, is what lets a delete through (migration 0064).
        session.execute(text("SELECT set_config('matching.allow_prune', 'on', true)"))
        counts["match_factor"] = _rowcount(
            session,
            "DELETE FROM matching.match_factor f USING matching.match_assessment a "
            "WHERE f.assessment_id = a.id AND a.opportunity_id = ANY(:ids)",
            params,
        )
        counts["match_assessment"] = _rowcount(
            session,
            "DELETE FROM matching.match_assessment WHERE opportunity_id = ANY(:ids)",
            params,
        )
        # Observations first, by occurrence: their FK to the occurrence is SET NULL, which
        # would orphan them instead of deleting them.
        counts["source_occurrence_observation"] = _rowcount(
            session,
            "DELETE FROM opportunities.source_occurrence_observation "
            "WHERE source_occurrence_id IN (SELECT id FROM opportunities.source_occurrence "
            "WHERE opportunity_id = ANY(:ids))",
            params,
        )
        # RESTRICT toward raw_item, so it has to go before the raw item does.
        _rowcount(
            session,
            "DELETE FROM opportunities.normalization_result WHERE opportunity_id = ANY(:ids)",
            params,
        )
        counts["opportunity"] = _rowcount(
            session,
            "DELETE FROM opportunities.opportunity WHERE id = ANY(:ids)",
            params,
        )
        for table, number in _delete_unreferenced_raw_items(session, raw_ids).items():
            counts[table] = counts.get(table, 0) + number
        return locked, {table: number for table, number in counts.items() if number}


def _delete_unreferenced_raw_items(session: Session, raw_ids: list[Any]) -> dict[str, int]:
    if not raw_ids:
        return {}
    free = [
        row[0]
        for row in session.execute(
            text(
                "SELECT r.id FROM acquisition.raw_item r WHERE r.id = ANY(:raw_ids) "
                f"AND NOT ({_STILL_REFERENCED}) FOR UPDATE OF r SKIP LOCKED"
            ),
            {"raw_ids": raw_ids},
        )
    ]
    if free:
        # Fresh snapshot after the lock: a row that gained a reference meanwhile stays.
        free = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT r.id FROM acquisition.raw_item r WHERE r.id = ANY(:free) "
                    f"AND NOT ({_STILL_REFERENCED})"
                ),
                {"free": free},
            )
        ]
    if not free:
        return {}
    params = {"free": free}
    payloads = session.execute(
        text("SELECT count(*) FROM acquisition.raw_item_payload WHERE raw_item_id = ANY(:free)"),
        params,
    ).scalar_one()
    observations = session.execute(
        text(
            "SELECT count(*) FROM opportunities.source_occurrence_observation "
            "WHERE raw_item_id = ANY(:free)"
        ),
        params,
    ).scalar_one()
    deleted = _rowcount(
        session, "DELETE FROM acquisition.raw_item WHERE id = ANY(:free)", params
    )
    return {
        "raw_item": deleted,
        "raw_item_payload": payloads,
        "source_occurrence_observation": observations,
    }


def _rowcount(session: Session, sql: str, params: dict[str, Any]) -> int:
    return cast(CursorResult[Any], session.execute(text(sql), params)).rowcount or 0


def _count_all(engine: Engine, cutoff: datetime, report: OpportunityRetentionReport) -> None:
    """Dry run: what an unbounded run would delete, in one read-only transaction."""
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        params = {"cutoff": cutoff}
        report.kept_with_application, report.kept_with_relevant_mark = session.execute(
            text(
                f"SELECT count(*) FILTER (WHERE {_HAS_APPLICATION}), "
                f"count(*) FILTER (WHERE {_HAS_RELEVANT_MARK}) "
                f"FROM opportunities.opportunity o WHERE {_AGE} < :cutoff"
            ),
            params,
        ).one()
        elig = f"(SELECT o.id FROM opportunities.opportunity o WHERE {_ELIGIBLE})"
        counts = {
            "opportunity": f"SELECT count(*) FROM {elig} e",
            "duplicate_candidate": (
                "SELECT count(*) FROM opportunities.duplicate_candidate d WHERE "
                f"d.opportunity_id IN {elig} OR d.duplicate_opportunity_id IN {elig}"
            ),
            "match_factor": (
                "SELECT count(*) FROM matching.match_factor f JOIN matching.match_assessment a "
                f"ON a.id = f.assessment_id WHERE a.opportunity_id IN {elig}"
            ),
            "match_analysis": (
                "SELECT count(*) FROM matching.match_analysis x JOIN matching.match_assessment a "
                f"ON a.id = x.assessment_id WHERE a.opportunity_id IN {elig}"
            ),
            "match_analysis_claim": (
                "SELECT count(*) FROM matching.match_analysis_claim x JOIN "
                "matching.match_assessment a ON a.id = x.assessment_id "
                f"WHERE a.opportunity_id IN {elig}"
            ),
            "source_occurrence_observation": (
                "SELECT count(*) FROM opportunities.source_occurrence_observation b WHERE "
                "b.source_occurrence_id IN (SELECT s.id FROM opportunities.source_occurrence s "
                f"WHERE s.opportunity_id IN {elig})"
            ),
        }
        for label, table in _BY_OPPORTUNITY:
            counts[label] = f"SELECT count(*) FROM {table} t WHERE t.opportunity_id IN {elig}"
        # Raw items reachable from an old opportunity, with nothing left once they are gone.
        candidate_raw = (
            "SELECT s.raw_item_id AS id FROM opportunities.source_occurrence s "
            f"WHERE s.opportunity_id IN {elig} "
            "UNION SELECT n.raw_item_id FROM opportunities.normalization_result n "
            f"WHERE n.opportunity_id IN {elig}"
        )
        free_raw = (
            f"SELECT r.id FROM acquisition.raw_item r WHERE r.id IN ({candidate_raw}) "
            "AND NOT (EXISTS (SELECT 1 FROM opportunities.source_occurrence s "
            f"WHERE s.raw_item_id = r.id AND s.opportunity_id NOT IN {elig}) "
            "OR EXISTS (SELECT 1 FROM opportunities.normalization_result n "
            f"WHERE n.raw_item_id = r.id AND (n.opportunity_id IS NULL "
            f"OR n.opportunity_id NOT IN {elig})) "
            "OR EXISTS (SELECT 1 FROM opportunities.opportunity_compensation c "
            f"WHERE c.raw_item_id = r.id AND c.opportunity_id NOT IN {elig}))"
        )
        counts["raw_item"] = f"SELECT count(*) FROM ({free_raw}) x"
        counts["raw_item_payload"] = (
            "SELECT count(*) FROM acquisition.raw_item_payload p "
            f"WHERE p.raw_item_id IN ({free_raw})"
        )
        for label, sql in counts.items():
            report.rows[label] = session.execute(text(sql), params).scalar_one()
        report.rows = {label: number for label, number in report.rows.items() if number}


def _housekeeping(
    engine: Engine,
    report: OpportunityRetentionReport,
    *,
    ai_days: int | None,
    tavily: bool,
    batch_size: int,
    stop: Callable[[], bool],
    now: datetime,
) -> None:
    if ai_days is not None and ai_days > 0:
        try:
            _purge_ai_call_records(engine, report, ai_days, batch_size, stop, now)
        except Exception as error:
            _fail(report, "ai_call_record", error)
    if tavily:
        try:
            _purge_tavily_cache(engine, report, batch_size, stop, now)
        except Exception as error:
            _fail(report, "tavily_extract_cache", error)


def _purge_ai_call_records(
    engine: Engine,
    report: OpportunityRetentionReport,
    days: int,
    batch_size: int,
    stop: Callable[[], bool],
    now: datetime,
) -> None:
    cutoff = now - timedelta(days=days)
    if report.dry_run:
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            number = session.execute(
                text("SELECT count(*) FROM platform.ai_call_record WHERE created_at < :c"),
                {"c": cutoff},
            ).scalar_one()
    else:
        number = _delete_in_batches(
            engine,
            "DELETE FROM platform.ai_call_record WHERE id IN (SELECT id FROM "
            "platform.ai_call_record WHERE created_at < :c ORDER BY created_at "
            "LIMIT :n FOR UPDATE SKIP LOCKED)",
            {"c": cutoff},
            batch_size,
            stop,
            report,
        )
    if number:
        report.rows["ai_call_record"] = number


def _purge_tavily_cache(
    engine: Engine,
    report: OpportunityRetentionReport,
    batch_size: int,
    stop: Callable[[], bool],
    now: datetime,
) -> None:
    if report.dry_run:
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            number = session.execute(
                text(
                    "SELECT count(*) FROM acquisition.tavily_extract_cache "
                    "WHERE expires_at <= :now"
                ),
                {"now": now},
            ).scalar_one()
    else:
        number = _delete_in_batches(
            engine,
            "DELETE FROM acquisition.tavily_extract_cache WHERE url_hash IN (SELECT "
            "url_hash FROM acquisition.tavily_extract_cache WHERE expires_at <= :now "
            "ORDER BY expires_at LIMIT :n FOR UPDATE SKIP LOCKED)",
            {"now": now},
            batch_size,
            stop,
            report,
        )
    if number:
        report.rows["tavily_extract_cache"] = number


def _delete_in_batches(
    engine: Engine,
    sql: str,
    params: dict[str, Any],
    batch_size: int,
    stop: Callable[[], bool],
    report: OpportunityRetentionReport,
) -> int:
    total = 0
    while True:
        if stop():
            report.complete = False
            report.stopped = True
            return total
        with Session(engine) as session, session.begin():
            result = cast(
                CursorResult[Any], session.execute(text(sql), {**params, "n": batch_size})
            )
            deleted = result.rowcount or 0
        total += deleted
        if deleted < batch_size:
            return total


# --- Once per UTC day ---------------------------------------------------------------------


def retention_due(
    engine: Engine, *, now: datetime | None = None, job_name: str = JOB_NAME
) -> bool:
    """True unless a complete retention run already finished on today's UTC date."""
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    with Session(engine) as session:
        last = session.execute(
            text("SELECT last_success_at FROM platform.worker_job_state WHERE job_name = :j"),
            {"j": job_name},
        ).scalar_one_or_none()
    return last is None or last.astimezone(UTC).date() < moment.date()


def record_retention_attempt(
    engine: Engine,
    *,
    success: bool,
    error: str | None = None,
    now: datetime | None = None,
    job_name: str = JOB_NAME,
) -> None:
    """Remember the attempt in `platform.worker_job_state`; only a complete run is a success."""
    moment = now or datetime.now(UTC)
    with Session(engine) as session, session.begin():
        session.execute(
            text(
                "INSERT INTO platform.worker_job_state (job_name, last_attempt_at, "
                "last_success_at, last_failure_at, next_run_at, last_correlation_id, last_error) "
                "VALUES (:j, :t, :ok, :bad, :t, :cid, :err) "
                "ON CONFLICT (job_name) DO UPDATE SET last_attempt_at = :t, "
                "last_success_at = coalesce(:ok, platform.worker_job_state.last_success_at), "
                "last_failure_at = coalesce(:bad, platform.worker_job_state.last_failure_at), "
                "next_run_at = :t, last_correlation_id = :cid, last_error = :err"
            ),
            {
                "j": job_name,
                "t": moment,
                "ok": moment if success else None,
                "bad": None if success else moment,
                "cid": uuid4().hex,
                "err": error,
            },
        )


__all__ = [
    "DEFAULT_AI_CALL_RECORD_RETENTION_DAYS",
    "DEFAULT_OPPORTUNITY_RETENTION_DAYS",
    "DRY_RUN_JOB_NAME",
    "JOB_NAME",
    "OpportunityRetentionReport",
    "record_retention_attempt",
    "retention_due",
    "run_opportunity_retention",
]
