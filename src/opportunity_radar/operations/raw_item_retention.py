"""Shrink superseded raw items once a newer one carries the posting (card R55-E6).

A posting that changes at its source yields a new `raw_item` (new payload or semantic hash);
the occurrence then points at the newer one and the older item is only history. Each item
carries the whole `collected_item_v1` snapshot (title, description, source metadata) in its
`metadata`, which is the bulk of the envelope. Once the item is superseded and its
normalization finished, nothing reads that snapshot any more: normalization, department
re-classification and content re-classification all read the raw item of the occurrence's
*current* evidence.

What is done: the snapshot is dropped and the metadata keeps only `parser_version`,
`content_type` and a `lean` marker. The row itself stays (identity, hashes, FKs, funnel
counts, observations, normalization results), so the dedup of an unchanged re-collection and
every foreign key behave exactly as before, and nothing is deleted. The body goes through the
ordinary payload expiry (`operations/retention.py`), which also covers these items.

Never touched: an item the occurrence still points at (the latest of an open posting), an item
without a SUCCEEDED / REVIEW_REQUIRED result at the current normalizer version (pending or
failed work needs its snapshot), a source-proposal candidate, and anything younger than the
payload retention. `pending_raw_item_ids` skips lean items so that a normalizer bump does not
turn history into failures.

`RawItemModel` has an ORM `before_update` listener that refuses updates ("RawItem is
immutable"). This module intentionally bypasses it with a raw SQL UPDATE of `metadata` only;
there is no database trigger. The UPDATE re-asserts "no occurrence points at it" so an
occurrence that moved onto the item between the lock and the write keeps its snapshot.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Engine, text
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from opportunity_radar.platform.logging import get_logger

LEAN_KEY = "lean"
LEAN_MARKER = "e6-v1"
SNAPSHOT_KEY = "collected_item_v1"

logger = get_logger("opportunity_radar.operations.raw_item_retention")

_ELIGIBLE = f"""
r.fetched_at <= :cutoff
AND r.metadata -> '{LEAN_KEY}' IS NULL
AND r.metadata -> '{SNAPSHOT_KEY}' IS NOT NULL
AND (r.metadata ->> 'source_proposal_candidate') IS DISTINCT FROM 'true'
AND NOT EXISTS (
  SELECT 1 FROM opportunities.source_occurrence s WHERE s.raw_item_id = r.id)
AND EXISTS (
  SELECT 1 FROM opportunities.normalization_result n
  JOIN opportunities.source_occurrence so ON so.id = n.source_occurrence_id
  WHERE n.raw_item_id = r.id AND n.normalizer_version = :version
    AND n.status IN ('SUCCEEDED', 'REVIEW_REQUIRED'))
"""

_LOCK = f"""
SELECT r.id FROM acquisition.raw_item r
WHERE {_ELIGIBLE}
ORDER BY r.fetched_at, r.id
LIMIT :batch_size
FOR UPDATE OF r SKIP LOCKED
"""

_SHRINK = f"""
UPDATE acquisition.raw_item r
SET metadata = jsonb_strip_nulls(jsonb_build_object(
  'parser_version', r.metadata -> 'parser_version',
  'content_type', r.metadata -> 'content_type',
  '{LEAN_KEY}', CAST(:marker AS text)))
WHERE r.id = ANY(:ids)
  AND r.metadata -> '{LEAN_KEY}' IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM opportunities.source_occurrence s WHERE s.raw_item_id = r.id)
"""


@dataclass(frozen=True, slots=True)
class LeanOutcome:
    #: Shrunk by this run, or (dry run) how many a run would shrink now.
    raw_items: int
    batches: int
    complete: bool


def lean_superseded_raw_items(
    engine: Engine,
    *,
    retention_days: int,
    batch_size: int = 500,
    max_batches: int = 50,
    dry_run: bool = True,
    should_stop: Callable[[], bool] | None = None,
    now: datetime | None = None,
) -> LeanOutcome:
    """Drop the snapshot of superseded, normalized raw items older than `retention_days`."""
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    batch_size = max(1, batch_size)
    stop = should_stop or (lambda: False)
    params: dict[str, Any] = {
        "cutoff": (now or datetime.now(UTC)) - timedelta(days=retention_days),
        "version": NORMALIZER_VERSION,
    }
    if dry_run:
        with Session(engine) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            counted = session.execute(
                text(f"SELECT count(*) FROM acquisition.raw_item r WHERE {_ELIGIBLE}"), params
            ).scalar_one()
        return LeanOutcome(raw_items=int(counted), batches=0, complete=True)

    total = 0
    batches = 0
    while batches < max_batches:
        if stop():
            return LeanOutcome(total, batches, complete=False)
        with Session(engine) as session, session.begin():
            ids = [
                row[0]
                for row in session.execute(text(_LOCK), {**params, "batch_size": batch_size})
            ]
            if not ids:
                return LeanOutcome(total, batches, complete=True)
            result = cast(
                CursorResult[Any],
                session.execute(text(_SHRINK), {"ids": ids, "marker": LEAN_MARKER}),
            )
            total += result.rowcount or 0
        batches += 1
        if len(ids) < batch_size:
            return LeanOutcome(total, batches, complete=True)
    return LeanOutcome(total, batches, complete=False)


__all__ = ["LEAN_KEY", "LEAN_MARKER", "LeanOutcome", "lean_superseded_raw_items"]
