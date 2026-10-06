"""Persistence queries for Acquisition."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.acquisition.models import (
    HostBudgetStateModel,
    RawItemModel,
    RawItemPayloadModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceExecutionClaimModel,
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
SOURCE_CLAIM_LEASE = timedelta(minutes=3)


class SourceClaimUnavailable(RuntimeError):
    """Another unexpired execution currently owns this source."""


class FencedWriteRejected(RuntimeError):
    """This execution's fencing generation is no longer current."""


@dataclass(frozen=True, slots=True)
class SourceExecutionClaim:
    source_id: UUID
    run_id: UUID
    owner_id: UUID
    fencing_token: int
    task_key: str = "collect"


class AcquisitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def claim_source_execution(
        self,
        *,
        source_id: UUID,
        run_id: UUID,
        task_key: str = "collect",
        now: datetime | None = None,
    ) -> SourceExecutionClaim:
        """Acquire/steal an expired source lease in a short committed transaction."""
        now = now or datetime.now(UTC)
        owner_id = uuid4()
        bind = self.session.get_bind()
        with Session(bind=bind) as claim_session, claim_session.begin():
            claim_session.execute(
                pg_insert(SourceExecutionClaimModel)
                .values(
                    source_definition_id=source_id,
                    task_key=task_key,
                    fencing_token=0,
                    owner_id=None,
                    lease_expires_at=None,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        SourceExecutionClaimModel.source_definition_id,
                        SourceExecutionClaimModel.task_key,
                    ]
                )
            )
            claim = claim_session.scalar(
                select(SourceExecutionClaimModel)
                .where(
                    SourceExecutionClaimModel.source_definition_id == source_id,
                    SourceExecutionClaimModel.task_key == task_key,
                )
                .with_for_update()
            )
            if claim is None:  # pragma: no cover - the insert/select share a transaction
                raise RuntimeError("source execution claim row disappeared")
            if claim.owner_id is not None and claim.lease_expires_at is not None:
                expires_at = claim.lease_expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if expires_at > now:
                    raise SourceClaimUnavailable(f"source {source_id} is already claimed")
            previous_run_id = claim.run_id
            if previous_run_id is not None:
                old_run = claim_session.get(SourceRunModel, previous_run_id)
                if old_run is not None and old_run.status in _UNFINISHED_RUN_STATUSES:
                    old_run.status = "PARTIAL"
                    old_run.finished_at = now
                    old_run.complete = False
                    old_run.error_code = "FENCE_REJECTED"
                    old_run.error_summary = "execution lease expired and was recovered"
            claim.fencing_token += 1
            claim.owner_id = owner_id
            claim.lease_expires_at = now + SOURCE_CLAIM_LEASE
            # The run is inserted only after this independent lease transaction commits.
            # Keeping this FK null here avoids a second session seeing an uncommitted run.
            claim.run_id = None
            claim.updated_at = now
            token = claim.fencing_token
        return SourceExecutionClaim(source_id, run_id, owner_id, token, task_key)

    def attach_source_execution_run(self, claim: SourceExecutionClaim) -> bool:
        """Bind a committed RUNNING row to its already-acquired lease."""
        with Session(bind=self.session.get_bind()) as claim_session, claim_session.begin():
            result = claim_session.execute(
                update(SourceExecutionClaimModel)
                .where(
                    SourceExecutionClaimModel.source_definition_id == claim.source_id,
                    SourceExecutionClaimModel.task_key == claim.task_key,
                    SourceExecutionClaimModel.fencing_token == claim.fencing_token,
                    SourceExecutionClaimModel.owner_id == claim.owner_id,
                    SourceExecutionClaimModel.lease_expires_at > datetime.now(UTC),
                )
                .values(run_id=claim.run_id, updated_at=datetime.now(UTC))
            )
            return cast(CursorResult[Any], result).rowcount == 1

    def renew_source_execution_claim(
        self, claim: SourceExecutionClaim, *, now: datetime | None = None
    ) -> bool:
        now = now or datetime.now(UTC)
        with Session(bind=self.session.get_bind()) as claim_session, claim_session.begin():
            row = claim_session.scalar(
                select(SourceExecutionClaimModel)
                .where(
                    SourceExecutionClaimModel.source_definition_id == claim.source_id,
                    SourceExecutionClaimModel.task_key == claim.task_key,
                )
                .with_for_update()
            )
            if (
                row is None
                or row.fencing_token != claim.fencing_token
                or row.owner_id != claim.owner_id
                or row.lease_expires_at is None
                or row.lease_expires_at <= now
            ):
                return False
            row.lease_expires_at = now + SOURCE_CLAIM_LEASE
            row.updated_at = now
            return True

    def release_source_execution_claim(self, claim: SourceExecutionClaim) -> bool:
        with Session(bind=self.session.get_bind()) as claim_session, claim_session.begin():
            result = claim_session.execute(
                update(SourceExecutionClaimModel)
                .where(
                    SourceExecutionClaimModel.source_definition_id == claim.source_id,
                    SourceExecutionClaimModel.task_key == claim.task_key,
                    SourceExecutionClaimModel.fencing_token == claim.fencing_token,
                    SourceExecutionClaimModel.owner_id == claim.owner_id,
                )
                .values(owner_id=None, lease_expires_at=None, updated_at=datetime.now(UTC))
            )
            return cast(CursorResult[Any], result).rowcount == 1

    @staticmethod
    def assert_current_fence(
        session: Session,
        *,
        source_id: UUID,
        fencing_token: int,
        owner_id: UUID,
        task_key: str = "collect",
    ) -> None:
        """Lock the claim only until the caller commits its one mutation unit."""
        claim = session.scalar(
            select(SourceExecutionClaimModel)
            .where(
                SourceExecutionClaimModel.source_definition_id == source_id,
                SourceExecutionClaimModel.task_key == task_key,
            )
            .with_for_update()
        )
        now = datetime.now(UTC)
        expires_at = claim.lease_expires_at if claim is not None else None
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (
            claim is None
            or claim.fencing_token != fencing_token
            or claim.owner_id != owner_id
            or expires_at is None
            or expires_at <= now
        ):
            raise FencedWriteRejected(
                f"source {source_id} fencing token {fencing_token} is no longer current"
            )

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
        if cooldown_until is not None and (
            row.cooldown_until is None or row.cooldown_until < cooldown_until
        ):
            row.cooldown_until = cooldown_until
        self.session.flush()

    def reserve_host_request(
        self,
        host: str,
        *,
        now: datetime,
        default_ceiling: int,
        run_id: UUID,
        detail: bool = False,
    ) -> str | None:
        """Atomically consume one unit and commit it before its HTTP transport starts."""
        if default_ceiling <= 0:
            return "quota"
        model = HostBudgetStateModel
        rollover = model.window_start <= now - DEFAULT_HOST_BUDGET_WINDOW
        statement = pg_insert(model).values(
            host=host,
            window_start=now,
            requests_used=1,
            requests_ceiling=default_ceiling,
            exploration_reserve_ratio=0.10,
        ).on_conflict_do_update(
            index_elements=[model.host],
            set_={
                "window_start": case((rollover, now), else_=model.window_start),
                "requests_used": case((rollover, 1), else_=model.requests_used + 1),
                "updated_at": now,
            },
            where=(
                (model.cooldown_until.is_(None) | (model.cooldown_until <= now))
                & case(
                    (rollover, model.requests_ceiling > 0),
                    else_=(model.requests_used < model.requests_ceiling),
                )
            ),
        ).returning(model.host)
        accepted = self.session.execute(statement).scalar_one_or_none()
        if accepted is None:
            current = self.session.get(model, host)
            if (
                current is not None
                and current.cooldown_until is not None
                and current.cooldown_until > now
            ):
                return "cooldown"
            return "quota"
        counters = {"http_requests": SourceRunModel.http_requests + 1}
        if detail:
            counters["detail_requests"] = func.coalesce(SourceRunModel.detail_requests, 0) + 1
        self.session.execute(
            update(SourceRunModel).where(SourceRunModel.id == run_id).values(**counters)
        )
        self.session.commit()
        return None

    def persist_host_cooldown(self, host: str, until: datetime) -> None:
        """Extend, never shorten, the host cooldown from a provider response."""
        self.session.execute(
            update(HostBudgetStateModel)
            .where(HostBudgetStateModel.host == host)
            .values(
                cooldown_until=case(
                    (HostBudgetStateModel.cooldown_until.is_(None), until),
                    (HostBudgetStateModel.cooldown_until < until, until),
                    else_=HostBudgetStateModel.cooldown_until,
                ),
                updated_at=func.now(),
            )
        )
        self.session.commit()

    def persist_detail_counters(self, run_id: UUID, telemetry: Any) -> None:
        self.session.execute(
            update(SourceRunModel)
            .where(SourceRunModel.id == run_id)
            .values(
                detail_failures=telemetry.detail_failures,
                detail_skipped=telemetry.detail_skipped,
                detail_skip_reasons=telemetry.detail_skip_reasons,
            )
        )
        self.session.commit()
