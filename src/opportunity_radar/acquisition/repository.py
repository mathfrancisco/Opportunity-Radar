"""Persistence queries for Acquisition."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.acquisition.models import (
    HostBudgetStateModel,
    RawItemModel,
    RawItemPayloadModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.scheduling import (
    DEFAULT_HOST_BUDGET_WINDOW,
    SourceRunHistory,
)
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.opportunities.models import (
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)

_UNFINISHED_RUN_STATUSES = ("PENDING", "RUNNING")


class AcquisitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_source(self, source_id: UUID) -> SourceDefinitionModel | None:
        return self.session.scalar(
            select(SourceDefinitionModel)
            .where(SourceDefinitionModel.id == source_id)
            .options(selectinload(SourceDefinitionModel.checkpoint))
        )

    def enabled_ats_boards(self) -> frozenset[tuple[str, str]]:
        rows = self.session.execute(
            select(CompanySource.source_type, CompanySource.external_key)
            .join(
                SourceDefinitionModel,
                SourceDefinitionModel.company_source_id == CompanySource.id,
            )
            .where(
                SourceDefinitionModel.enabled.is_(True),
                CompanySource.external_key.is_not(None),
                CompanySource.source_type.in_(("ashby", "greenhouse", "lever")),
            )
        )
        return frozenset(
            (source_type, external_key) for source_type, external_key in rows if external_key
        )

    def list_sources(self, *, offset: int, limit: int) -> tuple[list[SourceDefinitionModel], int]:
        statement = select(SourceDefinitionModel).order_by(SourceDefinitionModel.name)
        sources = list(self.session.scalars(statement.offset(offset).limit(limit)))
        total = self.session.scalar(select(func.count(SourceDefinitionModel.id))) or 0
        return sources, total

    def list_collectable_sources(self) -> list[SourceDefinitionModel]:
        """Every source the scheduled pass may run: enabled and not `manual`, no limit.

        Never-collected sources come first, so a freshly imported batch is not stuck
        behind slow ones; then the company's priority (high first, and a source with no
        company counts as normal), then name.
        """
        last_started_at = (
            select(func.max(SourceRunModel.started_at))
            .where(SourceRunModel.source_definition_id == SourceDefinitionModel.id)
            .correlate(SourceDefinitionModel)
            .scalar_subquery()
        )
        priority_rank = case(
            (Company.priority == "high", 0),
            (Company.priority == "low", 2),
            (Company.priority == "blocked", 3),
            else_=1,
        )
        statement = (
            select(SourceDefinitionModel)
            .outerjoin(CompanySource, CompanySource.id == SourceDefinitionModel.company_source_id)
            .outerjoin(Company, Company.id == CompanySource.company_id)
            .where(
                SourceDefinitionModel.enabled.is_(True),
                SourceDefinitionModel.source_type != "manual",
            )
            .order_by(
                last_started_at.asc().nulls_first(),
                priority_rank,
                SourceDefinitionModel.name,
            )
        )
        return list(self.session.scalars(statement))

    def get_run(self, run_id: UUID) -> SourceRunModel | None:
        return self.session.scalar(
            select(SourceRunModel)
            .where(SourceRunModel.id == run_id)
            .options(selectinload(SourceRunModel.source_definition))
        )

    def list_runs(
        self, *, offset: int, limit: int, source_id: UUID | None = None
    ) -> tuple[list[SourceRunModel], int]:
        filters = [] if source_id is None else [SourceRunModel.source_definition_id == source_id]
        statement = (
            select(SourceRunModel)
            .where(*filters)
            .options(selectinload(SourceRunModel.source_definition))
            .order_by(SourceRunModel.started_at.desc(), SourceRunModel.id.desc())
        )
        runs = list(self.session.scalars(statement.offset(offset).limit(limit)))
        total = self.session.scalar(select(func.count(SourceRunModel.id)).where(*filters)) or 0
        return runs, total

    def run_history(self, source_id: UUID, *, sample: int = 32) -> SourceRunHistory:
        """Reduce recent runs to the scheduling facts: last attempt and the failure streak.

        Derived from the runs themselves rather than kept in a counter column, so the
        streak cannot drift from the history an operator is reading, and a successful run
        clears the backoff by existing instead of by a separate write.
        """
        rows = self.session.execute(
            select(
                SourceRunModel.status,
                SourceRunModel.started_at,
                SourceRunModel.finished_at,
            )
            .where(SourceRunModel.source_definition_id == source_id)
            .order_by(SourceRunModel.started_at.desc(), SourceRunModel.id.desc())
            .limit(sample)
        ).all()
        if not rows:
            return SourceRunHistory()
        consecutive_failures = 0
        last_failure_at: datetime | None = None
        for status, started_at, finished_at in rows:
            if status in _UNFINISHED_RUN_STATUSES:
                # Still in flight: it has decided nothing yet, in either direction.
                continue
            if status != "FAILED":
                break
            consecutive_failures += 1
            if last_failure_at is None:
                last_failure_at = finished_at or started_at
        return SourceRunHistory(
            last_started_at=rows[0].started_at,
            consecutive_failures=consecutive_failures,
            last_failure_at=last_failure_at,
        )

    def target_area_share(self, source_id: UUID, *, runs: int = 3) -> float | None:
        """Share of items inside the target areas over the source's last complete runs.

        Only runs that read the whole board and carry both counters count; `None` when
        fewer than `runs` of them exist or none of them saw a classified item. `UNKNOWN`
        items are in neither counter, so they weigh on neither side.
        """
        rows = self.session.execute(
            select(SourceRunModel.items_target_area, SourceRunModel.items_off_target)
            .where(
                SourceRunModel.source_definition_id == source_id,
                SourceRunModel.complete.is_(True),
                SourceRunModel.items_target_area.is_not(None),
                SourceRunModel.items_off_target.is_not(None),
            )
            .order_by(SourceRunModel.started_at.desc(), SourceRunModel.id.desc())
            .limit(runs)
        ).all()
        if len(rows) < runs:
            return None
        target = sum(row.items_target_area for row in rows)
        total = target + sum(row.items_off_target for row in rows)
        return target / total if total else None

    def identical_raw_item_exists(
        self, *, source_id: UUID, identity_key: str, payload_hash: str
    ) -> RawItemModel | None:
        return self.session.scalar(
            select(RawItemModel).where(
                RawItemModel.source_definition_id == source_id,
                RawItemModel.identity_key == identity_key,
                RawItemModel.payload_hash == payload_hash,
            )
        )

    def raw_item_by_envelope(
        self,
        *,
        source_id: UUID,
        identity_key: str,
        payload_hash: str,
        semantic_hash: str,
        semantic_hash_version: str,
    ) -> RawItemModel | None:
        """Return only evidence with the same immutable parser interpretation."""
        return self.session.scalar(
            select(RawItemModel).where(
                RawItemModel.source_definition_id == source_id,
                RawItemModel.identity_key == identity_key,
                RawItemModel.payload_hash == payload_hash,
                RawItemModel.semantic_hash == semantic_hash,
                RawItemModel.semantic_hash_version == semantic_hash_version,
            )
        )

    def latest_raw_item_by_identity(
        self, *, source_id: UUID, identity_key: str
    ) -> RawItemModel | None:
        """The newest evidence of one posting, whatever its content was."""
        return self.session.scalar(
            select(RawItemModel)
            .where(
                RawItemModel.source_definition_id == source_id,
                RawItemModel.identity_key == identity_key,
            )
            .order_by(RawItemModel.fetched_at.desc(), RawItemModel.id.desc())
            .limit(1)
        )

    def latest_raw_payloads(self, source_id: UUID) -> dict[str, dict[str, Any]]:
        """`external_id -> payload` of each posting's newest evidence that still has a body."""
        rows = self.session.execute(
            select(RawItemModel.external_id, RawItemPayloadModel.payload)
            .join(RawItemPayloadModel, RawItemPayloadModel.raw_item_id == RawItemModel.id)
            .where(RawItemModel.source_definition_id == source_id)
            .order_by(
                RawItemModel.identity_key,
                RawItemModel.fetched_at.desc(),
                RawItemModel.id.desc(),
            )
            .distinct(RawItemModel.identity_key)
        )
        return {
            external_id: payload
            for external_id, payload in rows
            if external_id is not None and payload is not None
        }

    def record_presence_observation(
        self,
        *,
        raw_item: RawItemModel,
        source_run_id: UUID,
        observed_at: datetime,
        content_hash_matched: bool,
    ) -> None:
        occurrence = self.session.scalar(
            select(SourceOccurrenceModel).where(SourceOccurrenceModel.raw_item_id == raw_item.id)
        )
        if occurrence is None and raw_item.external_id:
            occurrence = self.session.scalar(
                select(SourceOccurrenceModel).where(
                    SourceOccurrenceModel.source_definition_id == raw_item.source_definition_id,
                    SourceOccurrenceModel.external_id == raw_item.external_id,
                )
            )
        if occurrence is None and raw_item.canonical_url:
            occurrence = self.session.scalar(
                select(SourceOccurrenceModel).where(
                    SourceOccurrenceModel.source_definition_id == raw_item.source_definition_id,
                    SourceOccurrenceModel.source_url == raw_item.canonical_url,
                )
            )
        if occurrence is not None and observed_at > occurrence.last_seen_at:
            occurrence.last_seen_at = observed_at
            occurrence.last_seen_run_id = source_run_id
        try:
            with self.session.begin_nested():
                self.session.add(
                    SourceOccurrenceObservationModel(
                        source_occurrence_id=occurrence.id if occurrence is not None else None,
                        source_run_id=source_run_id,
                        raw_item_id=raw_item.id,
                        observed_at=observed_at,
                        content_hash_matched=content_hash_matched,
                    )
                )
                self.session.flush()
        except IntegrityError:
            pass

    def resumable_run(self, run_id: UUID, *, source_id: UUID) -> SourceRunModel | None:
        """A named run of this source whose persisted prefix a caller may resume.

        Only a run that stopped short (`PARTIAL`/`FAILED`) while still persisting some
        evidence qualifies (F20-39 "retomada da mesma execução"); a `SUCCEEDED` run has
        nothing left to continue, and a run with no persisted items has no prefix at all.
        """
        return self.session.scalar(
            select(SourceRunModel).where(
                SourceRunModel.id == run_id,
                SourceRunModel.source_definition_id == source_id,
                SourceRunModel.status.in_(("PARTIAL", "FAILED")),
                SourceRunModel.items_persisted > 0,
            )
        )

    def has_completed_run(self, source_id: UUID, *, exclude_run_id: UUID) -> bool:
        """Whether some other run for this source ever proved the board fully read.

        Used only to let a fully-revalidated 304 manifest (F20-39) reuse that persisted
        complete inventory; `exclude_run_id` keeps the current in-flight run (already
        flushed, not yet committed) from counting as its own prior proof.
        """
        return (
            self.session.scalar(
                select(SourceRunModel.id)
                .where(
                    SourceRunModel.source_definition_id == source_id,
                    SourceRunModel.id != exclude_run_id,
                    SourceRunModel.complete.is_(True),
                )
                .limit(1)
            )
            is not None
        )

    def checkpoint(self, source_id: UUID) -> SourceCheckpointModel | None:
        return self.session.get(SourceCheckpointModel, source_id)

    def get_host_budget(self, host: str) -> HostBudgetStateModel | None:
        return self.session.get(HostBudgetStateModel, host)

    def record_host_budget_usage(
        self,
        host: str,
        *,
        now: datetime,
        requests: int,
        default_ceiling: int,
        cooldown_until: datetime | None = None,
    ) -> None:
        """Persist this run's spend against `host`'s shared budget (F20-38).

        Read-modify-write on the same row every source of this host shares: two sources
        collected in the same pass each call this once, so the second one to commit sees
        the first one's spend already counted, not a stale ceiling. `cooldown_until` is set
        unconditionally when given — the caller (a fresh `Retry-After`) always wins over
        whatever cooldown was there before, never the other way round.
        """
        row = self.session.get(HostBudgetStateModel, host)
        if row is None:
            row = HostBudgetStateModel(
                host=host,
                window_start=now,
                requests_used=0,
                requests_ceiling=default_ceiling,
            )
            self.session.add(row)
        elif now - row.window_start >= DEFAULT_HOST_BUDGET_WINDOW:
            row.window_start = now
            row.requests_used = 0
        row.requests_used += requests
        if cooldown_until is not None:
            row.cooldown_until = cooldown_until
        self.session.flush()
