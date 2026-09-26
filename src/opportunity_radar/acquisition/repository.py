"""Persistence queries for Acquisition."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.acquisition.models import (
    HostBudgetStateModel,
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.scheduling import (
    DEFAULT_HOST_BUDGET_WINDOW,
    SourceRunHistory,
)
from opportunity_radar.companies.models import CompanySource

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
            (source_type, external_key)
            for source_type, external_key in rows
            if external_key
        )

    def list_sources(
        self, *, offset: int, limit: int
    ) -> tuple[list[SourceDefinitionModel], int]:
        statement = select(SourceDefinitionModel).order_by(SourceDefinitionModel.name)
        sources = list(self.session.scalars(statement.offset(offset).limit(limit)))
        total = self.session.scalar(select(func.count(SourceDefinitionModel.id))) or 0
        return sources, total

    def get_run(self, run_id: UUID) -> SourceRunModel | None:
        return self.session.scalar(
            select(SourceRunModel)
            .where(SourceRunModel.id == run_id)
            .options(selectinload(SourceRunModel.source_definition))
        )

    def list_runs(
        self, *, offset: int, limit: int, source_id: UUID | None = None
    ) -> tuple[list[SourceRunModel], int]:
        filters = (
            []
            if source_id is None
            else [SourceRunModel.source_definition_id == source_id]
        )
        statement = (
            select(SourceRunModel)
            .where(*filters)
            .options(selectinload(SourceRunModel.source_definition))
            .order_by(SourceRunModel.started_at.desc(), SourceRunModel.id.desc())
        )
        runs = list(self.session.scalars(statement.offset(offset).limit(limit)))
        total = (
            self.session.scalar(select(func.count(SourceRunModel.id)).where(*filters))
            or 0
        )
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

    def identical_raw_item_exists(
        self, *, source_id: UUID, identity_key: str, payload_hash: str
    ) -> bool:
        return self.session.scalar(
            select(RawItemModel.id).where(
                RawItemModel.source_definition_id == source_id,
                RawItemModel.identity_key == identity_key,
                RawItemModel.payload_hash == payload_hash,
            )
        ) is not None

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
