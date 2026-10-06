"""Application service that turns collector output into immutable raw evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from contextlib import aclosing, contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from math import ceil, isfinite
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.alerts import (
    SourceAlertNotifier,
    SourceAlertService,
)
from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.collectors import CollectorRegistry, ManualCollector
from opportunity_radar.acquisition.concurrency import source_host_key
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionNetworkPolicy,
    CollectionRequest,
    CollectionTelemetry,
    SourceRun,
    SourceRunStatus,
    content_hashes,
    evaluate_completeness,
    item_payload_bytes,
    newest_item_age_seconds,
)
from opportunity_radar.acquisition.forbidden import (
    forbidden_platform_for_url,
    refuse_forbidden,
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.hacker_news import DISCOVERY_VIA as HN_DISCOVERY_VIA
from opportunity_radar.acquisition.inhire import InhireCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceProbeModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.probing import (
    PROBE_TYPES,
    ProbeOutcome,
    collector_test_audit,
    run_probe,
)
from opportunity_radar.acquisition.proposals import (
    IDENTIFIER_KEYS,
    follow_inert_correction,
)
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.acquisition.repository import (
    SOURCE_CLAIM_LEASE,
    AcquisitionRepository,
    FencedWriteRejected,
    SourceClaimUnavailable,
    SourceExecutionClaim,
)
from opportunity_radar.acquisition.scheduling import (
    DEFAULT_HOST_REQUESTS_CEILING,
    ConditionalRequestHeaders,
    HostBudgetState,
    SourceSchedulingState,
    default_schedule_for_priority,
    validate_cron_schedule,
)
from opportunity_radar.acquisition.tavily import (
    TavilyClient,
    TavilyCreditBudget,
    TavilyExtractionCache,
    TavilyExtractionSettings,
    apply_extracted_description,
    detect_ats_board,
    extract_missing_descriptions,
)
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.opportunities.role_family import (
    RoleFamily,
    classify_role_family,
    departments_from_metadata,
)
from opportunity_radar.platform.logging import get_logger
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

COLLECTED_ITEM_V1_KEY = "collected_item_v1"

logger = get_logger("opportunity_radar.acquisition.service")

# The host/provider each source_type shares its request budget with (F20-38). A
# source_type not listed here (including a collector added after this mapping was
# written) still gets an isolated budget bucket keyed by its own source_type — see
# `_host_for_source_type` — rather than being silently left out of budgeting.
_PROVIDER_HOST_BY_SOURCE_TYPE: dict[str, str] = {
    "greenhouse": "boards.greenhouse.io",
    "ashby": "api.ashbyhq.com",
    "lever": "api.lever.co",
    "remotive": "remotive.com",
    "hacker_news": "hacker-news.firebaseio.com",
    "tavily_search": "api.tavily.com",
    # One API host for every tenant, so tenants share one budget bucket (terms review).
    "inhire": "api.inhire.app",
}


#: Source types whose provider host is one tenant/site among many (F48-08): their budget is
#: keyed per tenant via `source_host_key`, so fifteen Workday tenants are fifteen buckets,
#: not one shared row that a single run can exhaust for everybody.
_TENANT_BUDGET_TYPES = frozenset({"workday", "teamtailor", "factorial", "jobposting"})

_HOST_KEY_MAX_LENGTH = 255

#: Request ceiling a new host budget row gets, per source_type (F48-08). A Workday tenant
#: needs ~1 request per 20 postings, so one large board fits its own bucket. Overridable
#: through `Settings.host_request_ceilings`; a persisted row keeps the ceiling it has.
DEFAULT_HOST_CEILING_BY_SOURCE_TYPE: dict[str, int] = {
    "workday": 500,
    "hacker_news": 500,
    "inhire": 1200,
}

#: Rate-limit policy a source type gets when its own `rate_limit_policy` sets neither
#: `minimum_interval_seconds` nor `requests_per_second`. inHire: at most one request per second
#: (docs/pesquisas/termos-inhire.md, "Condições para operar").
DEFAULT_RATE_LIMIT_POLICY_BY_SOURCE_TYPE: dict[str, dict[str, Any]] = {
    "inhire": {"requests_per_second": 1}
}


def _host_for_source_type(source_type: str) -> str:
    return _PROVIDER_HOST_BY_SOURCE_TYPE.get(source_type, source_type)


def _budget_host_for_source(source_type: str, configuration: dict[str, Any] | None) -> str:
    """Persisted budget key of one source: the tenant for per-tenant types (F48-08), the
    physical provider host for shared-host types, `source_type` for anything else."""
    if source_type in _TENANT_BUDGET_TYPES:
        return source_host_key(source_type, configuration)[:_HOST_KEY_MAX_LENGTH]
    return _host_for_source_type(source_type)


def _conditional_headers_for(
    source: SourceDefinitionModel,
) -> ConditionalRequestHeaders | None:
    """Validators for the next request, only when the checkpoint is the same scope.

    A checkpoint promoted while rotating keywords (`checkpoint_type == "keyword_rotation"`)
    describes a different representation than a plain incremental cursor, so its etag/
    last-modified — if it ever had any — must never condition a request for that other
    scope (SPEC 39 §7). `None` here means "send an unconditional request", not "the
    representation is unchanged".
    """
    checkpoint = source.checkpoint
    if checkpoint is None or checkpoint.checkpoint_type != "cursor":
        return None
    if checkpoint.etag is None and checkpoint.last_modified is None:
        return None
    return ConditionalRequestHeaders(
        if_none_match=checkpoint.etag,
        if_modified_since=checkpoint.last_modified,
    )


@dataclass(frozen=True, slots=True)
class TavilyProposalOutcome:
    url: str
    outcome: Literal[
        "created",
        "already_proposed",
        "unmatched_pattern",
        "company_not_found",
        "forbidden_platform",
    ]
    proposal_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TavilyProposalReport:
    outcomes: tuple[TavilyProposalOutcome, ...]


class SourceNotFoundError(AcquisitionError):
    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"source not found: {source_id}",
        )


class SourceVersionConflictError(AcquisitionError):
    """The source changed after the caller read it.

    A conflict, not a configuration error: the recovery is to read the source again and
    decide, never to resend the same payload over someone else's change.
    """

    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            "source definition was changed; refresh it before updating",
        )
        self.source_id = source_id


class SourceLinkConflictError(AcquisitionError):
    """Linking would make the source/company-source pairing ambiguous.

    `conflict_code` is the stable HTTP code: `source_already_linked` (the source already
    has a company source) or `company_source_already_linked` (another source of the same
    type already reads that board).
    """

    def __init__(self, conflict_code: str, summary: str) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            summary,
            field="company_source_id",
        )
        self.conflict_code = conflict_code


class SourceProbeTooSoonError(AcquisitionError):
    """A probe asked for before the source's spacing allows another request."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            AcquisitionErrorCode.SOURCE_RATE_LIMITED,
            f"this source was probed or collected too recently; retry in "
            f"{retry_after_seconds} seconds",
            retryable=True,
        )
        self.retry_after_seconds = retry_after_seconds


# A double click must not become two requests to someone else's board, and an impatient
# operator must not be able to hammer one either.
PROBE_MIN_INTERVAL_SECONDS = 60
PROBE_MAX_ITEMS = 1


class SourceClaimedElsewhereError(AcquisitionError):
    """Another execution (worker, CLI or API) holds this source's unexpired claim.

    Retryable and HTTP-free by construction: the claim is taken before the collector runs.
    """

    outcome = "claimed_elsewhere"

    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"source is claimed by another execution: {source_id}",
            retryable=True,
        )
        self.source_id = source_id


class _ClaimScope:
    """One execution's claim on its source: acquire, keep the lease alive, fence, release.

    The renewal task and every fenced write run on the event loop's thread, and a fenced
    write holds the claim row lock only between `fence` and the caller's commit with no
    `await` in between, so the renewal can never wait on a lock this same thread holds.
    """

    def __init__(self, repository: AcquisitionRepository, renew_interval: float) -> None:
        self._repository = repository
        self._renew_interval = renew_interval
        self.claim: SourceExecutionClaim | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._lost = False

    def acquire(self, source_id: UUID, run_id: UUID) -> SourceExecutionClaim:
        try:
            claim = self._repository.claim_source_execution(source_id=source_id, run_id=run_id)
        except SourceClaimUnavailable as unavailable:
            self._log("claim_contended", source_id=source_id, run_id=run_id)
            raise SourceClaimedElsewhereError(source_id) from unavailable
        self.claim = claim
        self._log("claim_acquired", claim=claim)
        if claim.recovered:
            self._log("claim_recovered", claim=claim, recovered_run_id=claim.recovered_run_id)
        self._heartbeat = asyncio.create_task(self._renew_loop(claim))
        return claim

    def attach(self) -> bool:
        """Bind the committed RUNNING row to the claim; False when the lease is already lost."""
        assert self.claim is not None
        return self._repository.attach_source_execution_run(self.claim)

    def fence(self, session: Session) -> None:
        """Reject the write about to happen unless this execution still owns the claim."""
        claim = self.claim
        assert claim is not None
        try:
            if self._lost:
                raise FencedWriteRejected(f"source {claim.source_id} lease was lost")
            self._repository.assert_current_fence(
                session,
                source_id=claim.source_id,
                fencing_token=claim.fencing_token,
                owner_id=claim.owner_id,
                task_key=claim.task_key,
            )
        except FencedWriteRejected:
            session.rollback()
            self._log("fence_rejected", claim=claim)
            raise

    async def _renew_loop(self, claim: SourceExecutionClaim) -> None:
        while True:
            await asyncio.sleep(self._renew_interval)
            try:
                renewed = self._repository.renew_source_execution_claim(claim)
            except Exception:  # noqa: BLE001 - the next tick retries; the lease still runs
                logger.exception("source claim renewal failed", extra={"job": "collect"})
                continue
            if not renewed:
                self._lost = True
                self._log("fence_rejected", claim=claim, reason="lease_lost")
                return
            self._log("lease_renewed", claim=claim)

    async def stop_renewal(self) -> None:
        heartbeat, self._heartbeat = self._heartbeat, None
        if heartbeat is not None:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def close(self) -> None:
        await self.stop_renewal()
        if self.claim is not None:
            # Conditional on token and owner: a no-op for a lease someone else recovered.
            self._repository.release_source_execution_claim(self.claim)

    @staticmethod
    def _log(
        event: str,
        *,
        claim: SourceExecutionClaim | None = None,
        source_id: UUID | None = None,
        run_id: UUID | None = None,
        **extra: object,
    ) -> None:
        # The fencing token is a per-source ordinal, safe to audit; the owner id is not logged.
        logger.info(
            f"source claim {event}",
            extra={
                "job": "collect",
                "event": event,
                "source_id": str(claim.source_id if claim is not None else source_id),
                "run_id": str(claim.run_id if claim is not None else run_id),
                "fencing_token": claim.fencing_token if claim is not None else None,
                **{key: str(value) for key, value in extra.items()},
            },
        )


class SourceDisabledError(AcquisitionError):
    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"source is disabled: {source_id}",
        )


def active_profile_target_role_families(session: Session) -> Callable[[], tuple[str, ...]]:
    """Read the active profile's target areas on demand; empty when none is active (F50-04)."""

    def read() -> tuple[str, ...]:
        try:
            profile = ProfileService(session).get_active()
        except ProfileNotFoundError:
            return ()
        return tuple(profile.snapshot.preferences.target_role_families)

    return read


class AcquisitionService:
    def __init__(
        self,
        session: Session,
        registry: CollectorRegistry | None = None,
        repository: AcquisitionRepository | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        alert_notifier: SourceAlertNotifier | None = None,
        alerts: SourceAlertService | None = None,
        tavily_extraction: TavilyExtractionSettings | None = None,
        host_request_ceilings: Mapping[str, int] | None = None,
        target_role_families: Callable[[], tuple[str, ...]] | None = None,
        target_area_floor: float = 0.0,
        claims_enabled: bool = False,
        claim_renew_interval_seconds: float | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or AcquisitionRepository(session)
        self.alerts = alerts or SourceAlertService(session, notifier=alert_notifier)
        self.registry = registry or CollectorRegistry(
            (
                ManualCollector(),
                AshbyCollector(),
                LeverCollector(),
                GreenhouseCollector(),
                RemotiveCollector(),
            )
        )
        self._sleeper = sleeper
        # F20-45: fills in a missing description via Tavily `/extract` after discovery,
        # for any collector's items, not only tavily_search's own. `None` (the default)
        # disables it — the same "absent is a supported deployment" treatment
        # `tavily_api_key` gets elsewhere.
        self._tavily_extraction = tavily_extraction
        # F48-08: request ceiling per source_type for a host budget row created by this
        # service (an existing row keeps the ceiling it was persisted with).
        self._host_request_ceilings: Mapping[str, int] = (
            DEFAULT_HOST_CEILING_BY_SOURCE_TYPE
            if host_request_ceilings is None
            else host_request_ceilings
        )
        # F50-04: areas of the active profile (read per run, so a profile change applies
        # at once) and the share below which a source stops persisting new off-target
        # items. No callable or a zero floor leaves the filter off.
        self._target_role_families = target_role_families
        self._target_area_floor = target_area_floor
        # F51-07: off keeps the unclaimed behaviour (the active-run unique index stays the
        # only single-flight); on needs a repository that can claim, i.e. a real database.
        self._claims_enabled = claims_enabled
        self._claim_renew_interval = (
            claim_renew_interval_seconds
            if claim_renew_interval_seconds is not None
            else SOURCE_CLAIM_LEASE.total_seconds() / 3
        )

    def create_source(
        self,
        *,
        source_type: str,
        name: str,
        company_source_id: UUID | None = None,
        enabled: bool = False,
        schedule: str | None = None,
        priority: int = 100,
        rate_limit_policy: Mapping[str, Any] | None = None,
        configuration: Mapping[str, Any] | None = None,
        evidence_status: str = "unverified",
        reviewed_at: datetime | None = None,
        terms_reviewed: bool = False,
        collector_local_tested: bool = False,
        commit: bool = True,
    ) -> SourceDefinitionModel:
        normalized_type = source_type.strip().casefold()
        normalized_name = name.strip()
        if not normalized_name:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source name cannot be empty",
                field="name",
            )
        with _refusing_field("source_type"):
            self.registry.resolve(normalized_type)
        source_configuration = dict(configuration or {})
        with _refusing_field("configuration"):
            _reject_secret_configuration(source_configuration)
            # F48-19: the central forbidden-platform list, whatever route created the source.
            refuse_forbidden(source_configuration)
        source_rate_limit_policy = dict(rate_limit_policy or {})
        with _refusing_field("rate_limit_policy"):
            resolved_network_policy = _source_network_policy(
                normalized_type, source_rate_limit_policy
            )
        if schedule is None and company_source_id is not None:
            schedule = self._default_schedule(company_source_id, resolved_network_policy)
        if normalized_type == "ashby":
            with _refusing_field("configuration.board_identifier"):
                AshbyCollector.validate_board_identifier(
                    _required_string(source_configuration, "board_identifier")
                )
        if normalized_type == "lever":
            with _refusing_field("configuration.site_identifier"):
                LeverCollector.validate_site_slug(
                    _required_string(source_configuration, "site_identifier")
                )
            with _refusing_field("configuration.api_region"):
                LeverCollector.validate_instance(
                    _required_string(source_configuration, "api_region")
                    if "api_region" in source_configuration
                    else "global"
                )
        if normalized_type == "greenhouse":
            with _refusing_field("configuration.board_token"):
                GreenhouseCollector.validate_board_token(
                    _required_string(source_configuration, "board_token")
                )
        if normalized_type == "workday":
            with _refusing_field("configuration"):
                _detail_settings(source_configuration, "workday")
        if normalized_type == "inhire":
            with _refusing_field("configuration.tenant_identifier"):
                InhireCollector.validate_tenant_identifier(
                    _required_string(source_configuration, "tenant_identifier")
                )
            with _refusing_field("configuration"):
                _detail_settings(source_configuration, "inhire", default_fetch_detail=True)
        if (
            enabled
            and normalized_type != "manual"
            and (
                evidence_status != "confirmed"
                or reviewed_at is None
                or not terms_reviewed
                or not collector_local_tested
            )
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "external sources require confirmed evidence, a review date, "
                "reviewed terms, and a locally tested collector",
            )
        source = SourceDefinitionModel(
            source_type=normalized_type,
            name=normalized_name,
            company_source_id=company_source_id,
            enabled=enabled,
            schedule=schedule,
            priority=priority,
            rate_limit_policy=source_rate_limit_policy,
            configuration=source_configuration,
            evidence_status=evidence_status,
            reviewed_at=reviewed_at,
            terms_reviewed=terms_reviewed,
            collector_local_tested=collector_local_tested,
        )
        self.session.add(source)
        try:
            if commit:
                self.session.commit()
            else:
                self.session.flush()
        except IntegrityError as error:
            # Always roll back, even when `commit=False`: a failed flush leaves the
            # session's transaction unusable until something rolls it back (to the
            # active SAVEPOINT when the caller is inside `begin_nested()`, otherwise
            # to the outer transaction). Skipping this when `commit` is False left the
            # session poisoned for whoever called us with `commit=False` directly
            # (card F20-46 flush-failure regression test).
            self.session.rollback()
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source definition conflicts with an existing record",
            ) from error
        if commit:
            self.session.refresh(source)
        return source

    def _default_schedule(
        self, company_source_id: UUID, network_policy: CollectionNetworkPolicy
    ) -> str | None:
        priority = self.session.scalar(
            select(Company.priority)
            .join(CompanySource, CompanySource.company_id == Company.id)
            .where(CompanySource.id == company_source_id)
        )
        if priority is None:
            return None
        return default_schedule_for_priority(
            priority,
            minimum_run_interval_seconds=network_policy.minimum_run_interval_seconds,
        )

    def list_sources(self, *, offset: int, limit: int) -> tuple[list[SourceDefinitionModel], int]:
        return self.repository.list_sources(offset=offset, limit=limit)

    def list_collectable_sources(self) -> list[SourceDefinitionModel]:
        return self.repository.list_collectable_sources()

    def get_source(self, source_id: UUID) -> SourceDefinitionModel | None:
        return self.repository.get_source(source_id)

    def propose_company_source(self, company_id: UUID) -> tuple[SourceDefinitionModel | None, str]:
        """Turn one researched ATS record into an inert, auditable proposal.

        Discovery records evidence; it never crosses the terms/test/enable gate.
        """
        company = self.session.get(Company, company_id)
        if company is None:
            raise SourceNotFoundError(company_id)
        candidate = self.session.scalar(
            select(CompanySource)
            .where(
                CompanySource.company_id == company_id,
                CompanySource.source_type.in_(PROPOSABLE_SOURCE_TYPES),
                CompanySource.external_key.is_not(None),
            )
            .order_by(CompanySource.id)
        )
        if candidate is None:
            return None, "not_detected"
        if forbidden_platform_for_url(candidate.endpoint or "") is not None:
            return None, "forbidden_platform"
        existing = self.session.scalar(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.company_source_id == candidate.id,
                SourceDefinitionModel.source_type == candidate.source_type,
            )
        )
        if existing is not None:
            return existing, "already_proposed"
        identifier = _proposal_identifier(candidate)
        if identifier is None:
            return None, "not_detected"
        proposal = self.create_source(
            source_type=candidate.source_type,
            name=f"Proposed {company.canonical_name} {candidate.source_type}",
            company_source_id=candidate.id,
            configuration={
                "company_name": company.canonical_name,
                **identifier,
                "discovery_evidence": candidate.evidence_note or candidate.endpoint,
            },
            evidence_status="ats_identified",
        )
        return proposal, "proposed"

    def propose_from_tavily_evidence(
        self,
        items: Iterable[CollectedItem],
        *,
        commit: bool = True,
        discovery_via: str = "tavily_search",
    ) -> TavilyProposalReport:
        """Turn marked, persisted Tavily results into inert ATS source proposals.

        Company names intentionally use exact canonical-name equality.  A Tavily search
        result is evidence of a board, not authority to guess which company owns it.
        `discovery_via` names the route that produced the evidence (`tavily_search` for the
        general search, `tavily_startup_search` for F20-53); a proposal is only refreshed
        by the route that created it.
        """
        outcomes: list[TavilyProposalOutcome] = []
        for item in items:
            if item.metadata.get("source_proposal_candidate") is not True:
                continue
            url = item.url or ""
            if forbidden_platform_for_url(url) is not None:
                outcomes.append(TavilyProposalOutcome(url, "forbidden_platform"))
                continue
            detected = detect_ats_board(url)
            if detected is None:
                outcomes.append(TavilyProposalOutcome(url, "unmatched_pattern"))
                continue
            source_type, board_key = detected
            companies = (
                self.session.scalars(
                    select(Company).where(Company.canonical_name == item.company_name).limit(2)
                ).all()
                if item.company_name
                else []
            )
            catalog_sources = self.session.scalars(
                select(CompanySource)
                .where(
                    CompanySource.source_type == source_type,
                    CompanySource.external_key == board_key,
                )
                .limit(2)
            ).all()
            if not companies and len(catalog_sources) == 1:
                company = self.session.get(Company, catalog_sources[0].company_id)
                companies = [company] if company is not None else []
            if len(companies) != 1 or (
                item.company_name
                and catalog_sources
                and any(source.company_id != companies[0].id for source in catalog_sources)
            ):
                outcomes.append(TavilyProposalOutcome(url, "company_not_found"))
                continue
            company = companies[0]
            company_source_id = catalog_sources[0].id if len(catalog_sources) == 1 else None
            configuration = _tavily_proposal_configuration(
                company=company,
                source_type=source_type,
                board_key=board_key,
                item=item,
                discovery_via=discovery_via,
            )

            identifier_key = IDENTIFIER_KEYS[source_type]
            by_board = self.session.scalar(
                select(SourceDefinitionModel).where(
                    SourceDefinitionModel.source_type == source_type,
                    SourceDefinitionModel.configuration[identifier_key].as_string() == board_key,
                )
            )
            if by_board is not None:
                if by_board.configuration.get("discovery_via") == discovery_via:
                    follow_inert_correction(
                        self.session,
                        by_board,
                        source_type=source_type,
                        board_key=board_key,
                        discovery_evidence=url,
                        configuration_updates=configuration,
                    )
                outcomes.append(TavilyProposalOutcome(url, "already_proposed", by_board.id))
                continue

            by_company = self.session.scalar(
                select(SourceDefinitionModel)
                .where(
                    SourceDefinitionModel.source_type == source_type,
                    SourceDefinitionModel.configuration["company_name"].as_string()
                    == company.canonical_name,
                    SourceDefinitionModel.configuration["discovery_via"].as_string()
                    == discovery_via,
                )
                .order_by(SourceDefinitionModel.created_at)
            )
            if by_company is not None:
                follow_up = follow_inert_correction(
                    self.session,
                    by_company,
                    source_type=source_type,
                    board_key=board_key,
                    discovery_evidence=url,
                    configuration_updates=configuration,
                )
                proposal = follow_up.proposal
                outcomes.append(
                    TavilyProposalOutcome(
                        url,
                        "already_proposed",
                        proposal.id if proposal is not None else by_company.id,
                    )
                )
                continue

            proposal = self.create_source(
                source_type=source_type,
                name=f"Proposed {company.canonical_name} {source_type}",
                company_source_id=company_source_id,
                configuration=configuration,
                evidence_status="ats_identified",
                commit=False,
            )
            outcomes.append(TavilyProposalOutcome(url, "created", proposal.id))

        report = TavilyProposalReport(tuple(outcomes))
        if commit:
            self.session.commit()
        for outcome in report.outcomes:
            logger.info(
                "tavily source proposal evaluated",
                extra={
                    "job": "tavily_source_proposal",
                    "url": outcome.url,
                    "outcome": outcome.outcome,
                    "proposal_id": str(outcome.proposal_id)
                    if outcome.proposal_id is not None
                    else None,
                },
            )
        return report

    def update_source_controls(
        self,
        source_id: UUID,
        *,
        enabled: bool,
        terms_reviewed: bool,
        collector_local_tested: bool,
        reviewed_at: datetime | None,
        expected_version: int,
    ) -> SourceDefinitionModel:
        source = self.repository.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        if source.version != expected_version:
            raise SourceVersionConflictError(source_id)
        effective_reviewed_at = reviewed_at or source.reviewed_at
        if (
            enabled
            and source.source_type != "manual"
            and (
                source.evidence_status != "confirmed"
                or effective_reviewed_at is None
                or not terms_reviewed
                or not collector_local_tested
            )
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "external sources require confirmed evidence, a review date, "
                "reviewed terms, and a locally tested collector",
            )
        updated_id = self.session.scalar(
            update(SourceDefinitionModel)
            .where(
                SourceDefinitionModel.id == source_id,
                SourceDefinitionModel.version == expected_version,
            )
            .values(
                enabled=enabled,
                terms_reviewed=terms_reviewed,
                collector_local_tested=collector_local_tested,
                reviewed_at=effective_reviewed_at,
                version=SourceDefinitionModel.version + 1,
            )
            .returning(SourceDefinitionModel.id)
        )
        if updated_id is None:
            self.session.rollback()
            raise SourceVersionConflictError(source_id)
        self.session.commit()
        self.session.refresh(source)
        return source

    def update_source_schedule(
        self,
        source_id: UUID,
        *,
        schedule: str | None,
        expected_version: int,
    ) -> SourceDefinitionModel:
        """Changes when the clock may collect this source. `None` means unscheduled —
        the source still runs on demand, but the scheduler skips it entirely.
        """
        source = self.repository.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        if source.version != expected_version:
            raise SourceVersionConflictError(source_id)
        if schedule is not None:
            try:
                validate_cron_schedule(schedule)
            except ValueError as error:
                raise AcquisitionError(
                    AcquisitionErrorCode.INVALID_CONFIGURATION,
                    f"schedule is not a valid cron expression: {error}",
                    field="schedule",
                ) from error
        updated_id = self.session.scalar(
            update(SourceDefinitionModel)
            .where(
                SourceDefinitionModel.id == source_id,
                SourceDefinitionModel.version == expected_version,
            )
            .values(
                schedule=schedule,
                version=SourceDefinitionModel.version + 1,
            )
            .returning(SourceDefinitionModel.id)
        )
        if updated_id is None:
            self.session.rollback()
            raise SourceVersionConflictError(source_id)
        self.session.commit()
        self.session.refresh(source)
        return source

    def link_company_source(
        self,
        source_id: UUID,
        *,
        company_source_id: UUID,
        expected_version: int,
    ) -> SourceDefinitionModel:
        """Point an unlinked source at the company source that carries its board.

        Only `company_source_id` and `version` change: the source keeps its enabled flag,
        schedule, checkpoint and runs. The company source must be of the source's type and
        carry exactly the source's board identifier (the comparison proposals use), and no
        other source of that type may already read that company source. Unlinking is not
        offered.
        """
        source = self.repository.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        if source.version != expected_version:
            raise SourceVersionConflictError(source_id)
        if source.company_source_id == company_source_id:
            return source
        if source.company_source_id is not None:
            raise SourceLinkConflictError(
                "source_already_linked", "the source is already linked to another company source"
            )
        record = self.session.get(CompanySource, company_source_id)
        if record is None:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"company source not found: {company_source_id}",
                field="company_source_id",
            )
        if record.source_type != source.source_type:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"the company source is {record.source_type}, the source is {source.source_type}",
                field="company_source_id",
            )
        identifier_key = IDENTIFIER_KEYS[source.source_type]
        expected = _proposal_identifier(record)
        configured = _optional_string(source.configuration or {}, identifier_key)
        if expected is None or configured is None or expected[identifier_key] != configured:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"the company source board key {record.external_key!r} does not equal the "
                f"source's {identifier_key} {configured!r}",
                field="company_source_id",
            )
        other = self.session.scalar(
            select(SourceDefinitionModel.id).where(
                SourceDefinitionModel.company_source_id == record.id,
                SourceDefinitionModel.source_type == source.source_type,
                SourceDefinitionModel.id != source.id,
            )
        )
        if other is not None:
            raise SourceLinkConflictError(
                "company_source_already_linked",
                f"another {source.source_type} source already reads this company source: {other}",
            )
        updated_id = self.session.scalar(
            update(SourceDefinitionModel)
            .where(
                SourceDefinitionModel.id == source_id,
                SourceDefinitionModel.version == expected_version,
                SourceDefinitionModel.company_source_id.is_(None),
            )
            .values(
                company_source_id=record.id,
                version=SourceDefinitionModel.version + 1,
            )
            .returning(SourceDefinitionModel.id)
        )
        if updated_id is None:
            self.session.rollback()
            raise SourceVersionConflictError(source_id)
        self.session.commit()
        self.session.refresh(source)
        return source

    def reopen_homologation(
        self, source_id: UUID, *, expected_version: int
    ) -> SourceDefinitionModel:
        """Point a proposal back at its corrected ATS record and start its gate over.

        Everything the gate held was about the board the source used to read: the evidence,
        the reviewed terms, the tested collector and the review date. They are cleared
        together with the key change, in one versioned write, and the audit that proved the
        old board is kept aside rather than deleted. The source stops collecting.
        """
        source = self.repository.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        if source.version != expected_version:
            raise SourceVersionConflictError(source_id)
        record = (
            self.session.get(CompanySource, source.company_source_id)
            if source.company_source_id is not None
            else None
        )
        if record is None:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "only a source proposed from a company ATS record can be reopened",
                field="company_source_id",
            )
        if record.source_type != source.source_type:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"the record now names {record.source_type}, and a {source.source_type} "
                "source cannot change collector",
                field="source_type",
            )
        configuration = dict(source.configuration or {})
        previous = configuration.pop("homologation_audit", None)
        history = configuration.get("reopened_homologations")
        configuration["reopened_homologations"] = [
            *(history if isinstance(history, list) else []),
            {
                "reopened_at": datetime.now(UTC).isoformat(),
                "previous_key": configuration.get(IDENTIFIER_KEYS[source.source_type]),
                "previous_evidence_status": source.evidence_status,
                "previous_audit": previous,
            },
        ]
        configuration[IDENTIFIER_KEYS[source.source_type]] = record.external_key
        configuration["discovery_evidence"] = record.evidence_note or record.endpoint
        updated = self.session.scalar(
            update(SourceDefinitionModel)
            .where(
                SourceDefinitionModel.id == source_id,
                SourceDefinitionModel.version == expected_version,
            )
            .values(
                enabled=False,
                terms_reviewed=False,
                collector_local_tested=False,
                reviewed_at=None,
                evidence_status="ats_identified",
                configuration=configuration,
                version=SourceDefinitionModel.version + 1,
            )
            .returning(SourceDefinitionModel.id)
        )
        if updated is None:
            self.session.rollback()
            raise SourceVersionConflictError(source_id)
        self.session.commit()
        self.session.refresh(source)
        return source

    async def probe_source(
        self,
        source_id: UUID,
        *,
        expected_version: int,
        requested_by: str = "interface",
    ) -> tuple[SourceProbeModel, SourceDefinitionModel, ProbeOutcome]:
        """Test the collector against the public endpoint and, if it reads, confirm evidence.

        The probe is written before the request goes out, under a lock on the source, so
        two clicks that race both see the first attempt and only one reaches the network.
        A passing probe confirms the evidence and marks the collector tested; it never
        marks terms reviewed and never enables — those stay explicit steps of the gate.
        What the probe read is discarded: nothing becomes a RawItem outside a SourceRun.
        """
        source = self.session.scalar(
            select(SourceDefinitionModel)
            .where(SourceDefinitionModel.id == source_id)
            .with_for_update()
        )
        if source is None:
            raise SourceNotFoundError(source_id)
        if source.version != expected_version:
            self.session.rollback()
            raise SourceVersionConflictError(source_id)
        if source.source_type not in PROBE_TYPES:
            self.session.rollback()
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"{source.source_type} sources have no public endpoint to probe",
                field="source_type",
            )
        if source.enabled:
            self.session.rollback()
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "an enabled source is proven by its own runs; disable it before probing",
                field="enabled",
            )
        network_policy = _source_network_policy(source.source_type, source.rate_limit_policy)
        wait = self._probe_wait(source, network_policy)
        if wait > 0:
            self.session.rollback()
            raise SourceProbeTooSoonError(wait)

        probe = SourceProbeModel(
            source_definition_id=source.id,
            requested_by=requested_by,
            status="RUNNING",
            started_at=datetime.now(UTC),
        )
        self.session.add(probe)
        self.session.commit()

        outcome = await run_probe(
            source.source_type,
            dict(source.configuration or {}),
            self.registry,
            max_items=PROBE_MAX_ITEMS,
            network_policy=network_policy,
        )
        recorded_probe, recorded_source = self._record_probe(
            source, probe, outcome, expected_version
        )
        return recorded_probe, recorded_source, outcome

    def _probe_wait(self, source: SourceDefinitionModel, policy: CollectionNetworkPolicy) -> int:
        """Seconds until this source may be asked again, by probe or by the run spacing."""
        now = datetime.now(UTC)
        waits = [0.0]
        last_probe = self.session.scalar(
            select(func.max(SourceProbeModel.started_at)).where(
                SourceProbeModel.source_definition_id == source.id
            )
        )
        if last_probe is not None:
            waits.append(PROBE_MIN_INTERVAL_SECONDS - (now - last_probe).total_seconds())
        run_interval = policy.minimum_run_interval_seconds
        if run_interval and source.last_http_attempt_at is not None:
            waits.append(run_interval - (now - source.last_http_attempt_at).total_seconds())
        return ceil(max(waits))

    def _record_probe(
        self,
        source: SourceDefinitionModel,
        probe: SourceProbeModel,
        outcome: ProbeOutcome,
        expected_version: int,
    ) -> tuple[SourceProbeModel, SourceDefinitionModel]:
        finished_at = datetime.now(UTC)
        probe.status = "PASSED" if outcome.ok else "FAILED"
        probe.finished_at = finished_at
        probe.items_seen = outcome.items_seen
        probe.http_requests = outcome.http_requests
        probe.error_code = outcome.error_code
        probe.detail = outcome.detail
        if outcome.last_http_attempt_at is not None:
            self.session.execute(
                update(SourceDefinitionModel)
                .where(SourceDefinitionModel.id == source.id)
                .values(last_http_attempt_at=outcome.last_http_attempt_at)
            )
        if outcome.ok:
            configuration = dict(source.configuration or {})
            existing_audit = configuration.get("homologation_audit")
            configuration["homologation_audit"] = {
                **(existing_audit if isinstance(existing_audit, dict) else {}),
                **collector_test_audit(
                    source.source_type,
                    outcome,
                    probe_id=str(probe.id),
                    probed_at=finished_at,
                    requested_by=probe.requested_by,
                ),
            }
            # Written only if nobody changed the source while the request was out: evidence
            # about a board is not evidence about whatever the source says now.
            confirmed = self.session.scalar(
                update(SourceDefinitionModel)
                .where(
                    SourceDefinitionModel.id == source.id,
                    SourceDefinitionModel.version == expected_version,
                    SourceDefinitionModel.enabled.is_(False),
                )
                .values(
                    evidence_status="confirmed",
                    collector_local_tested=True,
                    configuration=configuration,
                    version=SourceDefinitionModel.version + 1,
                )
                .returning(SourceDefinitionModel.id)
            )
            probe.evidence_recorded = confirmed is not None
        self.session.commit()
        self.session.refresh(source)
        self.session.refresh(probe)
        return probe, source

    def record_script_probe(
        self,
        source: SourceDefinitionModel,
        outcome: ProbeOutcome,
        started_at: datetime,
        *,
        evidence_recorded: bool,
    ) -> SourceProbeModel:
        """Keeps the enable script's attempts in the same history as the interface's."""
        probe = SourceProbeModel(
            source_definition_id=source.id,
            requested_by="script",
            status="PASSED" if outcome.ok else "FAILED",
            started_at=started_at,
            finished_at=datetime.now(UTC),
            items_seen=outcome.items_seen,
            http_requests=outcome.http_requests,
            error_code=outcome.error_code,
            detail=outcome.detail,
            evidence_recorded=evidence_recorded,
        )
        self.session.add(probe)
        self.session.flush()
        return probe

    def scheduling_state(
        self, source: SourceDefinitionModel, *, timezone: str
    ) -> SourceSchedulingState:
        """Everything the clock-driven job needs to decide about one source.

        Built here so the worker never has to parse a rate-limit policy itself: the
        throttle the job honours and the throttle `execute` enforces come from the same
        reader, and cannot disagree.
        """
        policy = _source_network_policy(source.source_type, source.rate_limit_policy)
        host = _budget_host_for_source(source.source_type, source.configuration)
        host_budget_row = self.repository.get_host_budget(host)
        host_budget = (
            HostBudgetState(
                host=host_budget_row.host,
                window_start=host_budget_row.window_start,
                requests_used=host_budget_row.requests_used,
                requests_ceiling=host_budget_row.requests_ceiling,
                cooldown_until=host_budget_row.cooldown_until,
                exploration_reserve_ratio=host_budget_row.exploration_reserve_ratio,
            )
            if host_budget_row is not None
            else None
        )
        history = self.repository.run_history(source.id)
        return SourceSchedulingState(
            schedule=source.schedule,
            timezone=timezone,
            history=history,
            last_http_attempt_at=source.last_http_attempt_at,
            minimum_run_interval_seconds=policy.minimum_run_interval_seconds,
            host=host,
            host_budget=host_budget,
            # A source that has never completed a run is exactly the "fonte nova/pouco
            # observada" the exploration reserve exists for (SPEC 39 §7): without this it
            # would compete for the same 90% slice as every well-observed source on its
            # host and could be crowded out indefinitely (acceptance criterion 2).
            is_low_yield=history.last_started_at is None,
        )

    def get_run(self, run_id: UUID) -> SourceRunModel | None:
        return self.repository.get_run(run_id)

    def list_runs(
        self, *, offset: int, limit: int, source_id: UUID | None = None
    ) -> tuple[list[SourceRunModel], int]:
        return self.repository.list_runs(offset=offset, limit=limit, source_id=source_id)

    async def execute(
        self,
        source_id: UUID,
        request: CollectionRequest,
        *,
        deadline_seconds: float | None = None,
    ) -> SourceRunModel:
        scope = (
            _ClaimScope(self.repository, self._claim_renew_interval)
            if self._claims_enabled
            else None
        )
        try:
            return await self._execute(
                source_id, request, deadline_seconds=deadline_seconds, scope=scope
            )
        finally:
            # After the run's terminal commit, or after F51-06 awaited a live transport's
            # cleanup: ownership is never released while work for the source is alive.
            if scope is not None:
                await scope.close()

    async def _execute(
        self,
        source_id: UUID,
        request: CollectionRequest,
        *,
        deadline_seconds: float | None,
        scope: _ClaimScope | None,
    ) -> SourceRunModel:
        deadline_at = (
            asyncio.get_running_loop().time() + deadline_seconds
            if deadline_seconds is not None
            else None
        )
        if request.source_definition_id not in {None, source_id}:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "collection request source does not match the requested source",
            )
        source = self.repository.get_source(source_id)
        if source is None:
            raise SourceNotFoundError(source_id)
        if not source.enabled:
            raise SourceDisabledError(source_id)
        if source.source_type == "manual" and request.mode is not CollectionMode.MANUAL:
            raise AcquisitionError(
                AcquisitionErrorCode.MANUAL_INPUT_INVALID,
                "manual sources require at least one input",
            )
        if source.source_type != "manual" and request.mode is CollectionMode.MANUAL:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "external sources do not accept manual inputs",
            )

        collector = self.registry.resolve(source.source_type)
        if (
            request.mode is CollectionMode.INCREMENTAL
            and not collector.capabilities.incremental_cursor
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"{source.source_type} does not support incremental collection",
            )
        if request.keywords and not collector.capabilities.keyword_search:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"{source.source_type} does not support keyword search",
            )
        if request.locations and not collector.capabilities.location_search:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"{source.source_type} does not support location search",
            )
        network_policy = _source_network_policy(source.source_type, source.rate_limit_policy)
        run_telemetry = CollectionTelemetry()

        # F50-04: items are always counted against the profile's target areas; the filter
        # only drops new off-target items from a source that has stayed below the floor.
        targets = (
            frozenset(self._target_role_families())
            if self._target_role_families is not None
            else frozenset()
        )
        filter_active = False
        if targets and self._target_area_floor > 0 and source.source_type != "manual":
            share = self.repository.target_area_share(source.id)
            filter_active = share is not None and share < self._target_area_floor

        # A new collection starts at the beginning. Resumption is explicit through the
        # request cursor; a prior run's checkpoint is evidence, not an implicit cursor.
        checkpoint_before = request.cursor
        if request.resume_of_run_id is not None and (
            self.repository.resumable_run(request.resume_of_run_id, source_id=source.id)
            is None
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "resume_of_run_id does not name a partial or failed run of this source "
                "with persisted evidence",
                field="resume_of_run_id",
            )
        run = SourceRun(
            source_definition_id=source.id,
            execution_trigger=request.execution_trigger,
            checkpoint_before=checkpoint_before,
        )
        run.start()
        if targets:
            run.record_target_area()
        # Before the run row and before any HTTP: a contended source costs no request, and
        # taking over an expired lease closes the abandoned run that would block this one.
        claim = scope.acquire(source.id, run.id) if scope is not None else None
        persisted_run = SourceRunModel(
            id=run.id,
            source_definition_id=source.id,
            execution_trigger=run.execution_trigger.value,
            status=run.status.value,
            started_at=run.started_at,
            checkpoint_before=checkpoint_before,
            correlation_id=request.correlation_id,
            resumed_from_run_id=request.resume_of_run_id,
            fencing_token=claim.fencing_token if claim is not None else None,
        )
        self.session.add(persisted_run)
        try:
            self.session.flush()
            # The short, independent Workday reservation session must see the RUNNING
            # run before it records attempts. Later collection writes remain in this
            # session and are committed with the terminal result.
            self.session.commit()
        except IntegrityError as conflict:
            self.session.rollback()
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source already has an active run",
                retryable=True,
            ) from conflict
        if scope is not None and not scope.attach():
            # The lease lapsed between claim and attach, so nobody knows this RUNNING row:
            # end it here or it would block the next run through the active-run index.
            persisted_run.status = SourceRunStatus.PARTIAL.value
            persisted_run.finished_at = datetime.now(UTC)
            persisted_run.complete = False
            persisted_run.error_code = "FENCE_REJECTED"
            persisted_run.error_summary = "execution lease lost before the run was attached"
            self.session.commit()
            raise FencedWriteRejected(f"source {source.id} lease was lost before the run started")

        logger.info(
            "source collection run started",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "run_id": str(run.id),
                "state": "started",
                "deadline_at_monotonic": deadline_at,
                "last_activity_at": datetime.now(UTC).isoformat(),
            },
        )

        # A competing transaction may have waited on the active-run unique index.
        # Reload after acquiring that slot so throttling uses its committed attempt.
        self.session.refresh(source, attribute_names=["last_http_attempt_at"])
        last_http_attempt_at = source.last_http_attempt_at
        minimum_run_interval = (
            network_policy.minimum_run_interval_seconds
            if network_policy.minimum_run_interval_seconds is not None
            else network_policy.minimum_interval_seconds
        )
        throttle_error: AcquisitionError | None = None
        if last_http_attempt_at is not None and minimum_run_interval:
            elapsed = (datetime.now(UTC) - last_http_attempt_at).total_seconds()
            delay = minimum_run_interval - elapsed
            if delay > 0:
                if network_policy.minimum_run_interval_seconds is not None:
                    run_telemetry.record_rate_limit()
                    throttle_error = AcquisitionError(
                        AcquisitionErrorCode.SOURCE_RATE_LIMITED,
                        f"source run interval has not elapsed; retry in {ceil(delay)} seconds",
                        retryable=True,
                    )
                else:
                    if deadline_at is None:
                        await self._sleeper(delay)
                    else:
                        try:
                            async with asyncio.timeout_at(deadline_at):
                                await self._sleeper(delay)
                        except TimeoutError:
                            throttle_error = AcquisitionError(
                                AcquisitionErrorCode.SOURCE_TIMEOUT,
                                "source collection deadline exceeded during throttle",
                                retryable=True,
                            )

        error: AcquisitionError | None = None
        last_cursor: str | None = None
        received_bytes = 0
        newest_dated_item: datetime | None = None
        tavily_proposal_items: list[CollectedItem] = []
        hn_proposal_items: list[CollectedItem] = []
        # Built once per run, not per item: reused by `_fill_missing_description` below
        # for every item in this run that needs one, and closed once the run's discovery
        # loop is done (successfully or not — every branch below is caught, so control
        # always reaches the `aclose()` call after this try/except). The budget is
        # per-run too — a fresh one per item would never see the cumulative spend and
        # so would never stop a run whose extractions, added up, exceed the ceiling.
        extraction_client = (
            self._tavily_extraction.client_factory()
            if self._tavily_extraction is not None
            else None
        )
        # F48-08: Tavily `/extract` calls are counted here, never in `run_telemetry` —
        # that one feeds the ATS host budget, and extraction is a different provider.
        tavily_telemetry = CollectionTelemetry()
        externally_cancelled = False
        durable_reservations = callable(getattr(self.session, "get_bind", None))
        extraction_budget = (
            TavilyCreditBudget(limit=self._tavily_extraction.credit_budget_per_run)
            if self._tavily_extraction is not None
            else None
        )
        try:
            if throttle_error is not None:
                raise throttle_error
            company_reference, company_name, api_region = _collector_settings(source)
            fetch_detail, detail_max_requests = (
                _detail_settings(source.configuration, source.source_type)
                if source.source_type == "workday"
                else _detail_settings(
                    source.configuration, source.source_type, default_fetch_detail=True
                )
                if source.source_type == "inhire"
                else (request.fetch_detail, request.detail_max_requests)
            )
            approval_valid, approval_reason = _workday_detail_approval(
                source.configuration, source.id, company_reference, api_region
            ) if source.source_type == "workday" else (False, "approval_missing")
            budget_host = _budget_host_for_source(source.source_type, source.configuration)

            def reserve_request(is_detail: bool) -> str | None:
                with Session(bind=self.session.get_bind()) as budget_session:
                    return AcquisitionRepository(budget_session).reserve_host_request(
                        budget_host,
                        now=datetime.now(UTC),
                        default_ceiling=self._host_request_ceilings.get(
                            source.source_type, DEFAULT_HOST_REQUESTS_CEILING
                        ),
                        run_id=run.id,
                        detail=is_detail,
                    )

            def persist_cooldown(until: datetime) -> None:
                with Session(bind=self.session.get_bind()) as budget_session:
                    AcquisitionRepository(budget_session).persist_host_cooldown(
                        budget_host, until
                    )

            def persist_detail(telemetry: CollectionTelemetry) -> None:
                with Session(bind=self.session.get_bind()) as budget_session:
                    AcquisitionRepository(budget_session).persist_detail_counters(
                        run.id, telemetry
                    )
            collector_request = replace(
                request,
                target_role_families=tuple(sorted(targets)),
                fetch_detail=fetch_detail,
                detail_max_requests=detail_max_requests,
                detail_approval_valid=approval_valid,
                detail_approval_skip_reason=approval_reason,
                reserve_http_request=(
                    reserve_request
                    if source.source_type == "workday" and durable_reservations
                    else None
                ),
                persist_cooldown=(
                    persist_cooldown
                    if source.source_type == "workday" and durable_reservations
                    else None
                ),
                persist_detail_counters=(
                    persist_detail
                    if source.source_type == "workday" and durable_reservations
                    else None
                ),
                host_requests_remaining=(
                    self._host_requests_remaining(source)
                    if fetch_detail and source.source_type != "workday"
                    else None
                ),
                source_definition_id=source.id,
                cursor=request.cursor,
                company_reference=company_reference or request.company_reference,
                company_name=company_name or request.company_name,
                api_region=api_region or request.api_region,
                telemetry=run_telemetry,
                network_policy=network_policy,
                conditional_headers=(
                    request.conditional_headers
                    if request.conditional_headers is not None
                    else _conditional_headers_for(source)
                ),
                known_ats_boards=(
                    self.repository.enabled_ats_boards()
                    if source.source_type == "tavily_search"
                    else request.known_ats_boards
                ),
                known_items=(
                    self.repository.latest_raw_payloads(source.id)
                    if collector.capabilities.known_items
                    else request.known_items
                ),
            )
            deadline = asyncio.timeout_at(deadline_at)
            async with deadline:
                if deadline.expired():
                    raise TimeoutError("source collection deadline exceeded")
                async with aclosing(collector.discover(collector_request)) as items:
                    try:
                        async for item in items:
                            if deadline.expired():
                                raise TimeoutError("source collection deadline exceeded")
                            run.record_items(seen=1)
                            received_bytes += item_payload_bytes(item)
                            item_date = item.published_at or item.updated_at
                            if item_date is not None and (
                                newest_dated_item is None or item_date > newest_dated_item
                            ):
                                newest_dated_item = item_date
                            item = await self._fill_missing_description(
                                item,
                                client=extraction_client,
                                budget=extraction_budget,
                                telemetry=tavily_telemetry,
                                network_policy=network_policy,
                                run=run,
                                source_type=source.source_type,
                            )
                            if deadline.expired():
                                raise TimeoutError("source collection deadline exceeded")
                            off_target = False
                            if targets:
                                try:
                                    family = classify_role_family(
                                        title=item.title,
                                        departments=departments_from_metadata(item.metadata),
                                    ).role_family
                                except Exception:  # noqa: BLE001 - malformed item is UNKNOWN
                                    family = RoleFamily.UNKNOWN
                                if family is not RoleFamily.UNKNOWN:
                                    off_target = family.value not in targets
                                    run.record_target_area(
                                        target=0 if off_target else 1,
                                        off_target=1 if off_target else 0,
                                    )
                            if scope is not None:
                                scope.fence(self.session)
                            try:
                                created = self._persist_item(
                                    source.id,
                                    run.id,
                                    source.source_type,
                                    item,
                                    observed_at=run.started_at or datetime.now(UTC),
                                    persist_new=not (filter_active and off_target),
                                )
                            except (TypeError, ValueError) as item_error:
                                run.record_items(invalid=1)
                                error = AcquisitionError(
                                    AcquisitionErrorCode.INVALID_ITEM,
                                    str(item_error),
                                    retryable=False,
                                )
                                continue
                            finally:
                                # One mutation unit per item: evidence, occurrence and
                                # presence commit together and release the claim row lock.
                                if scope is not None:
                                    self.session.commit()
                            if created:
                                run.record_items(persisted=1)
                            else:
                                run.record_items(skipped=1)
                            logger.info(
                                "source collection item processed",
                                extra={
                                    "job": "collect",
                                    "source_id": str(source.id),
                                    "run_id": str(run.id),
                                    "state": "progress",
                                    "items_seen": run.items_seen,
                                    "items_persisted": run.items_persisted,
                                    "http_requests": run_telemetry.http_requests,
                                    "last_activity_at": datetime.now(UTC).isoformat(),
                                },
                            )
                            if source.source_type == "tavily_search":
                                tavily_proposal_items.append(item)
                            elif source.source_type == "hacker_news":
                                hn_proposal = _hn_proposal_item(item)
                                if hn_proposal is not None:
                                    hn_proposal_items.append(hn_proposal)
                            if item.cursor is not None:
                                last_cursor = item.cursor
                    except asyncio.CancelledError:
                        logger.warning(
                            "source collection cleanup pending",
                            extra={
                                "job": "collect",
                                "source_id": str(source.id),
                                "run_id": str(run.id),
                                "state": "cleanup_pending",
                                "last_activity_at": datetime.now(UTC).isoformat(),
                            },
                        )
                        raise
            if deadline.expired():
                raise TimeoutError("source collection deadline exceeded")
            # `_persist_item` flushed every candidate's immutable raw evidence before
            # this pass.  A proposal failure is isolated to a savepoint so it cannot
            # erase that evidence or the source run that explains it.
            if tavily_proposal_items:
                try:
                    with self.session.begin_nested():
                        self.propose_from_tavily_evidence(tavily_proposal_items, commit=False)
                except Exception as proposal_error:
                    error = AcquisitionError(
                        AcquisitionErrorCode.INVALID_CONFIGURATION,
                        f"tavily source proposal failed: {proposal_error}",
                    )
            if hn_proposal_items:
                # F20-55: a "Who is hiring?" comment pointing at an ATS board we support
                # feeds the same F20-46 queue, tagged with its own route.
                try:
                    with self.session.begin_nested():
                        self.propose_from_tavily_evidence(
                            hn_proposal_items,
                            commit=False,
                            discovery_via=HN_DISCOVERY_VIA,
                        )
                except Exception as proposal_error:
                    error = AcquisitionError(
                        AcquisitionErrorCode.INVALID_CONFIGURATION,
                        f"hacker news source proposal failed: {proposal_error}",
                    )
        except FencedWriteRejected:
            # This execution lost its lease: nothing more of it may be written. The
            # recovering execution already closed this run as PARTIAL/FENCE_REJECTED.
            raise
        except TimeoutError:
            error = AcquisitionError(
                AcquisitionErrorCode.SOURCE_TIMEOUT,
                "source collection deadline exceeded",
                retryable=True,
            )
        except asyncio.CancelledError:
            externally_cancelled = True
            error = AcquisitionError(
                AcquisitionErrorCode.SOURCE_TIMEOUT,
                "source collection cancelled",
                retryable=True,
            )
        except AcquisitionError as caught:
            error = caught
        except Exception as caught:  # Preserve a stable external error boundary.
            error = AcquisitionError(AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR, str(caught))
        finally:
            if extraction_client is not None:
                await extraction_client.aclose()

        if scope is not None:
            # No await from the fence to the terminal commit below: the claim row lock this
            # takes is released by that commit, and the renewal task must not run meanwhile.
            await scope.stop_renewal()
            scope.fence(self.session)
        if run_telemetry.skipped_items:
            run.record_items(
                seen=run_telemetry.skipped_items, skipped=run_telemetry.skipped_items
            )
        if run_telemetry.invalid_items:
            run.record_items(
                seen=run_telemetry.invalid_items,
                invalid=run_telemetry.invalid_items,
            )
            if error is None:
                error = AcquisitionError(
                    AcquisitionErrorCode.INVALID_ITEM,
                    f"{run_telemetry.invalid_items} source item(s) were invalid: "
                    f"{run_telemetry.last_invalid_item_error}",
                )
        run.record_http_activity(
            requests=run_telemetry.http_requests,
            retries=run_telemetry.retry_count,
            rate_limit_events=run_telemetry.rate_limit_events,
        )
        run.record_credits(run_telemetry.credits_used)

        if error is None:
            final_status = (
                SourceRunStatus.PARTIAL if run.items_invalid else SourceRunStatus.SUCCEEDED
            )
        elif error.code in {
            AcquisitionErrorCode.INVALID_ITEM,
            AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED,
            AcquisitionErrorCode.SOURCE_TIMEOUT,
        }:
            final_status = SourceRunStatus.PARTIAL
        elif (
            source.source_type == "workday"
            and error.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED
        ):
            final_status = SourceRunStatus.PARTIAL
        elif run.items_persisted:
            final_status = SourceRunStatus.PARTIAL
        else:
            final_status = SourceRunStatus.FAILED
        if externally_cancelled:
            final_status = SourceRunStatus.CANCELLED
        run.finish(
            final_status,
            error=error if final_status is not SourceRunStatus.SUCCEEDED else None,
            checkpoint_after=(last_cursor if final_status is SourceRunStatus.SUCCEEDED else None),
        )
        run.items_announced = run_telemetry.items_announced
        run.bytes_received = received_bytes
        run.newest_item_age_seconds = newest_item_age_seconds(
            newest_dated_item, run.finished_at or datetime.now(UTC)
        )
        run.complete = evaluate_completeness(
            status=run.status,
            max_items=request.max_items,
            items_seen=run.items_seen,
            items_announced=run.items_announced,
        )
        # A supplied cursor is a suffix/retry request. Without persisted proof that its
        # preceding pages belong to this same run, it cannot authorize absence/closure.
        if request.cursor is not None:
            run.complete = False
        # A bare 304 would otherwise read as a complete, empty board to
        # `evaluate_completeness` (no announced total, no items seen, status SUCCEEDED):
        # exactly the false "vaga fechada" SPEC 39 §7 forbids. Revalidation proves the
        # representation is unchanged, not that it was read — unless the collector declared
        # a manifest of representations and every one of them revalidated as 304 in this
        # same run, and some earlier run already proved the board's inventory complete.
        # That combination is the only thing SPEC 39 §7 lets a 304 reuse (F20-39).
        if run_telemetry.not_modified:
            manifest_fully_revalidated = (
                run_telemetry.manifest_size is not None
                and run_telemetry.not_modified_count >= run_telemetry.manifest_size
                and request.cursor is None
                and run.items_seen == 0
            )
            run.complete = (
                manifest_fully_revalidated
                and final_status is SourceRunStatus.SUCCEEDED
                and self.repository.has_completed_run(source.id, exclude_run_id=run.id)
            )
        self._copy_run(run, persisted_run)
        if source.source_type == "workday":
            persisted_run.detail_requests = run_telemetry.detail_requests
            persisted_run.detail_failures = run_telemetry.detail_failures
            persisted_run.detail_skipped = run_telemetry.detail_skipped
            persisted_run.detail_skip_reasons = dict(run_telemetry.detail_skip_reasons)
        if run_telemetry.last_http_attempt_at is not None:
            source.last_http_attempt_at = run_telemetry.last_http_attempt_at

        # The checkpoint is part of this same transaction, so it cannot advance before raw evidence.
        # A bare 304 (`run_telemetry.not_modified`) yields no cursor but still revalidates
        # the representation's own etag/last-modified — SPEC 39 §7: that revalidation must
        # never be read as proof the board is fully read (`run.complete` above is untouched
        # by it, and stays governed by `evaluate_completeness`/the manifest check above).
        if final_status is SourceRunStatus.SUCCEEDED and (
            last_cursor is not None
            or run_telemetry.response_etag is not None
            or run_telemetry.response_last_modified is not None
        ):
            checkpoint = source.checkpoint or SourceCheckpointModel(source_definition_id=source.id)
            if last_cursor is not None:
                checkpoint.cursor = last_cursor
                checkpoint.checkpoint_type = "cursor"
            if run_telemetry.response_etag is not None:
                checkpoint.etag = run_telemetry.response_etag
            if run_telemetry.response_last_modified is not None:
                checkpoint.last_modified = run_telemetry.response_last_modified
            checkpoint.promoted_by_run_id = run.id
            checkpoint.promoted_at = datetime.now(UTC)
            self.session.add(checkpoint)

        # Shared host/provider budget (F20-38): every request this run made counts against
        # its host regardless of outcome, and a SOURCE_RATE_LIMITED error's own Retry-After
        # becomes a cooldown the *next* evaluation of any source on this host must respect
        # — persisted here so it survives a worker restart (acceptance criterion 3).
        cooldown_until = (
            datetime.now(UTC) + timedelta(seconds=error.retry_after_seconds)
            if error is not None
            and error.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED
            and error.retry_after_seconds is not None
            else None
        )
        if (source.source_type != "workday" or not durable_reservations) and (
            run_telemetry.http_requests or cooldown_until is not None
        ):
            self.repository.record_host_budget_usage(
                _budget_host_for_source(source.source_type, source.configuration),
                now=datetime.now(UTC),
                requests=run_telemetry.http_requests,
                default_ceiling=self._host_request_ceilings.get(
                    source.source_type, DEFAULT_HOST_REQUESTS_CEILING
                ),
                cooldown_until=cooldown_until,
            )
        self.session.commit()
        self.session.refresh(persisted_run)
        logger.info(
            "source collection run finished",
            extra={
                "job": "collect",
                "source_id": str(source.id),
                "run_id": str(run.id),
                "state": "terminal",
                "terminal_reason": (
                    "cancelled"
                    if final_status is SourceRunStatus.CANCELLED
                    else error.code.value
                    if error is not None
                    else "succeeded"
                ),
                "last_activity_at": datetime.now(UTC).isoformat(),
            },
        )
        self._announce(source, persisted_run, max_items=request.max_items)
        if final_status is SourceRunStatus.CANCELLED:
            raise asyncio.CancelledError
        return persisted_run

    def _host_requests_remaining(self, source: SourceDefinitionModel) -> int | None:
        """Requests the source's host budget still allows now, `None` without a budget row."""
        row = self.repository.get_host_budget(
            _budget_host_for_source(source.source_type, source.configuration)
        )
        if row is None:
            return None
        state = HostBudgetState(
            host=row.host,
            window_start=row.window_start,
            requests_used=row.requests_used,
            requests_ceiling=row.requests_ceiling,
            cooldown_until=row.cooldown_until,
            exploration_reserve_ratio=row.exploration_reserve_ratio,
        ).rolled_over(now=datetime.now(UTC))
        return max(0, state.effective_ceiling(is_low_yield=False) - state.requests_used)

    def _announce(
        self,
        source: SourceDefinitionModel,
        run: SourceRunModel,
        *,
        max_items: int | None,
    ) -> None:
        """Report what this run changed about the source being up.

        Runs after the commit and swallows its own failures: the alert channel describes
        collection, so it must never be able to decide the outcome of a collection.
        """
        try:
            self.alerts.record_run_outcome(
                source,
                run,
                consecutive_failures=self.repository.run_history(source.id).consecutive_failures,
            )
        except Exception:
            logger.exception(
                "source alert evaluation failed",
                extra={"job": "alert", "source_id": str(source.id), "run_id": str(run.id)},
            )
        # A run capped by max_items is expected to fall short of the announced total, so
        # a shortfall there is by design, not evidence of broken pagination.
        if (
            max_items is None
            and run.items_announced is not None
            and run.items_seen < run.items_announced
        ):
            try:
                self.alerts.record_pagination_gap(
                    source,
                    run,
                    items_seen=run.items_seen,
                    items_announced=run.items_announced,
                )
            except Exception:
                logger.exception(
                    "pagination alert evaluation failed",
                    extra={
                        "job": "alert",
                        "source_id": str(source.id),
                        "run_id": str(run.id),
                    },
                )

    async def _fill_missing_description(
        self,
        item: CollectedItem,
        *,
        client: TavilyClient | None,
        budget: TavilyCreditBudget | None,
        telemetry: CollectionTelemetry,
        network_policy: CollectionNetworkPolicy,
        run: SourceRun,
        source_type: str | None = None,
    ) -> CollectedItem:
        """Extracts a body for `item` when it has none, from any source, not only
        `tavily_search`'s own results (F20-45). A no-op when extraction is not configured
        (`client`/`budget` are `None`, no Tavily API key for this deployment) or the item
        already has a description.

        Called once per item, inside the same evidence-first loop `execute()` already
        runs, with a client and budget built once for the whole run (see the caller).
        `extract_missing_descriptions` itself still partitions into batches of up to 20
        (SPEC 41 §3.2) when given more than one URL, but calling it with a single URL here
        keeps this item's persistence exactly as atomic and order-preserving as every
        other item's — an extraction failure part-way through a run must not un-persist
        evidence a prior item in the same run already wrote (see
        `test_collector_failure_after_evidence_marks_run_partial`, the invariant this
        preserves). A cache hit costs no network call regardless, so this only turns into
        one `/extract` call per still-uncached URL rather than one call per run.
        """
        if self._tavily_extraction is None or client is None or budget is None or item.url is None:
            return item
        if (item.description or "").strip():
            return item
        settings = self._tavily_extraction
        # F48-08: a source type whose pages Tavily cannot read (Workday is JS) never spends
        # a call, and a host that failed N times in a row stops being tried.
        if source_type is not None and source_type in settings.skip_source_types:
            return item
        cache = TavilyExtractionCache(
            session=self.session,
            ttl_seconds=settings.cache_ttl_seconds,
        )
        if settings.host_failure_threshold > 0 and cache.host_is_failing(
            item.url, threshold=settings.host_failure_threshold
        ):
            return item
        results = await extract_missing_descriptions(
            client,
            cache,
            [item.url],
            extract_depth=self._tavily_extraction.extract_depth,
            format=self._tavily_extraction.format,
            telemetry=telemetry,
            network_policy=network_policy,
            budget=budget,
            run=run,
        )
        if not results:
            return item
        return apply_extracted_description(item, results[0])

    def _persist_item(
        self,
        source_id: UUID,
        run_id: UUID,
        source_type: str,
        item: CollectedItem,
        *,
        observed_at: datetime,
        persist_new: bool = True,
    ) -> bool:
        if item.source_type.strip().casefold() != source_type:
            raise ValueError("collected item source type does not match its source")
        payload = _json_object(item.raw_payload)
        payload_hash = canonical_payload_hash(payload)
        identity_key = _identity_key(
            item,
            payload_hash,
            allow_payload_identity=source_type == "manual",
        )
        metadata = _json_object(item.metadata)
        semantic_payload = collected_item_v1(item, metadata)
        hashes = content_hashes(semantic_payload, raw_hash=payload_hash)
        envelope_lookup = getattr(self.repository, "raw_item_by_envelope", None)
        existing = (
            envelope_lookup(
                source_id=source_id,
                identity_key=identity_key,
                payload_hash=payload_hash,
                semantic_hash=hashes.semantic_hash,
                semantic_hash_version=hashes.semantic_hash_version,
            )
            if envelope_lookup is not None
            else self.repository.identical_raw_item_exists(
                source_id=source_id,
                identity_key=identity_key,
                payload_hash=payload_hash,
            )
        )
        if existing:
            # Old in-memory adapters returned a boolean; only a real row can receive
            # an observation. Production repository returns that row since F20-39.
            if isinstance(existing, RawItemModel):
                self.repository.record_presence_observation(
                    raw_item=existing,
                    source_run_id=run_id,
                    observed_at=observed_at,
                    content_hash_matched=True,
                )
            return False
        if not persist_new:
            # An off-target posting already stored with other content is still on the
            # board: confirm its presence on the stored row (no new evidence), or a
            # complete run would stop seeing it and close it as absent.
            latest_lookup = getattr(self.repository, "latest_raw_item_by_identity", None)
            latest = (
                latest_lookup(source_id=source_id, identity_key=identity_key)
                if latest_lookup is not None
                else None
            )
            if isinstance(latest, RawItemModel):
                self.repository.record_presence_observation(
                    raw_item=latest,
                    source_run_id=run_id,
                    observed_at=observed_at,
                    content_hash_matched=False,
                )
            return False
        metadata[COLLECTED_ITEM_V1_KEY] = collected_item_v1(item, metadata)
        try:
            with self.session.begin_nested():
                raw_item = RawItemModel(
                    source_run_id=run_id,
                    source_definition_id=source_id,
                    external_id=item.external_id,
                    canonical_url=item.url,
                    identity_key=identity_key,
                    payload_hash=payload_hash,
                    semantic_hash=hashes.semantic_hash,
                    semantic_hash_version=hashes.semantic_hash_version,
                    content_type=_string_or_none(metadata.get("content_type")),
                    parser_version=_string_or_none(metadata.get("parser_version")),
                    item_metadata=metadata,
                )
                # Envelope and body are written together: an envelope whose content never
                # arrived would be indistinguishable from one retention has expired.
                raw_item.payload_record = RawItemPayloadModel(payload=payload)
                self.session.add(raw_item)
                self.session.flush()
                record_observation = getattr(self.repository, "record_presence_observation", None)
                if record_observation is not None:
                    record_observation(
                        raw_item=raw_item,
                        source_run_id=run_id,
                        observed_at=observed_at,
                        content_hash_matched=False,
                    )
        except IntegrityError:
            return False
        return True

    @staticmethod
    def _copy_run(run: SourceRun, model: SourceRunModel) -> None:
        model.status = run.status.value
        model.started_at = run.started_at
        model.finished_at = run.finished_at
        model.items_seen = run.items_seen
        model.items_persisted = run.items_persisted
        model.items_skipped = run.items_skipped
        model.items_invalid = run.items_invalid
        model.http_requests = run.http_requests
        model.retry_count = run.retry_count
        model.rate_limit_events = run.rate_limit_events
        model.error_code = run.error_code.value if run.error_code else None
        model.error_summary = run.error_summary
        model.checkpoint_after = run.checkpoint_after
        model.items_announced = run.items_announced
        model.complete = run.complete
        model.credits_used = run.credits_used
        model.bytes_received = run.bytes_received
        model.newest_item_age_seconds = run.newest_item_age_seconds
        model.items_target_area = run.items_target_area
        model.items_off_target = run.items_off_target


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def collected_item_v1(
    item: CollectedItem,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize the stable boundary consumed by the Opportunities context."""
    source_metadata = dict(metadata if metadata is not None else item.metadata)
    source_metadata.pop(COLLECTED_ITEM_V1_KEY, None)
    return {
        "version": 1,
        "source_type": item.source_type,
        "external_id": item.external_id,
        "url": item.url,
        "title": item.title,
        "company_name": item.company_name,
        "location_text": item.location_text,
        "description": item.description,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        "valid_through": item.valid_through.isoformat() if item.valid_through else None,
        # This is part of the interpretation boundary even for legacy/custom collectors
        # that did not supply parser metadata.  Keep the received metadata untouched;
        # the canonical `None` only makes the semantic identity explicit.
        "parser_version": _string_or_none(source_metadata.get("parser_version")),
        "metadata": source_metadata,
    }


def _json_object(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return result


def _identity_key(
    item: CollectedItem,
    payload_hash: str,
    *,
    allow_payload_identity: bool,
) -> str:
    if item.external_id:
        return f"external:{item.external_id.strip()}"
    if item.url:
        return f"url:{item.url.strip()}"
    if allow_payload_identity:
        return f"payload:{payload_hash}"
    raise ValueError("external collected item requires an external ID or canonical URL")


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


@contextmanager
def _refusing_field(field: str) -> Iterator[None]:
    """Attributes a configuration refusal to the request field that caused it."""
    try:
        yield
    except AcquisitionError as error:
        if error.field is None:
            error.field = field
        raise


#: ATS types `propose_company_source` can turn into an inert proposal (F48-17).
PROPOSABLE_SOURCE_TYPES: tuple[str, ...] = tuple(IDENTIFIER_KEYS)

_WORKDAY_HOST = re.compile(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$")


def _proposal_identifier(record: CompanySource) -> dict[str, str] | None:
    """The configuration keys a proposal needs for `record`, or None when unusable.

    Workday needs `<tenant>/<site>` plus the pod (`api_region`); both come from the record's
    key or its board URL (`https://<tenant>.<pod>.myworkdayjobs.com/[locale/]<site>`).
    """
    key = record.external_key
    if not key:
        return None
    identifier_key = IDENTIFIER_KEYS[record.source_type]
    if record.source_type != "workday":
        return {identifier_key: key}
    parts = urlsplit(record.endpoint or "")
    host = _WORKDAY_HOST.match((parts.hostname or "").casefold())
    if host is None:
        return None
    if "/" not in key:
        segments = [
            segment
            for segment in parts.path.split("/")
            if segment and not re.fullmatch(r"[a-z]{2}(?:-[A-Za-z]{2})?", segment)
        ]
        if not segments:
            return None
        key = f"{host.group(1)}/{segments[0]}"
    return {identifier_key: key, "api_region": host.group(2)}


def _required_string(configuration: Mapping[str, Any], key: str) -> str:
    value = configuration.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AcquisitionError(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"source configuration requires a non-empty {key}",
        )
    return value.strip()


def _optional_string(configuration: Mapping[str, Any], key: str) -> str | None:
    value = configuration.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _source_network_policy(
    source_type: str, policy: Mapping[str, Any] | None
) -> CollectionNetworkPolicy:
    """The source's own policy, or the type's default when it sets no request pacing."""
    own = dict(policy or {})
    if not {"minimum_interval_seconds", "requests_per_second"} & own.keys():
        own = {**DEFAULT_RATE_LIMIT_POLICY_BY_SOURCE_TYPE.get(source_type, {}), **own}
    return _network_policy(own)


def _detail_settings(
    configuration: Mapping[str, Any], source_type: str, *, default_fetch_detail: bool = False
) -> tuple[bool, int]:
    """`fetch_detail` (Workday: default off, SPEC 50 Q1; inHire: default on, its detail route
    is inside the terms review) and `detail_max_requests` (default 200)."""
    fetch_detail = configuration.get("fetch_detail", default_fetch_detail)
    if not isinstance(fetch_detail, bool):
        raise AcquisitionError(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"{source_type} configuration fetch_detail must be a boolean",
            field="configuration.fetch_detail",
        )
    max_requests = configuration.get("detail_max_requests", 200)
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or max_requests < 0:
        raise AcquisitionError(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"{source_type} configuration detail_max_requests must be a non-negative integer",
            field="configuration.detail_max_requests",
        )
    return fetch_detail, max_requests


def _workday_detail_approval(
    configuration: Mapping[str, Any],
    source_id: UUID,
    tenant_identifier: str | None,
    pod: str | None,
) -> tuple[bool, str]:
    """Require a source-local, explicit human decision before any Workday detail call."""
    approval = configuration.get("detail_approval")
    if not isinstance(approval, Mapping):
        return False, "approval_missing"
    tenant = (tenant_identifier or "").split("/", 1)[0]
    expected_host = f"{tenant}.{pod}.myworkdayjobs.com" if tenant and pod else ""
    owner = approval.get("owner")
    host = approval.get("hostname")
    decision = approval.get("decision")
    approved_source_id = approval.get("source_id")
    terms = approval.get("terms_reference") or approval.get("policy_reference")
    reviewed = approval.get("reviewed_at") or approval.get("reviewed_on")
    if (
        not expected_host
        or not isinstance(owner, str)
        or not owner.strip()
        or not isinstance(host, str)
        or host.casefold().rstrip(".") != expected_host.casefold()
        or approved_source_id != str(source_id)
        or decision != "approved"
        or not isinstance(terms, str)
        or not terms.strip()
        or not isinstance(reviewed, str)
    ):
        return False, "approval_missing"
    try:
        if len(reviewed) == 10:
            reviewed_date = date.fromisoformat(reviewed)
        else:
            reviewed_date = datetime.fromisoformat(
                reviewed.replace("Z", "+00:00")
            ).date()
        if reviewed_date > datetime.now(UTC).date():
            return False, "approval_future_date"
    except ValueError:
        return False, "approval_invalid_date"
    return True, "approved"


def _hn_proposal_item(item: CollectedItem) -> CollectedItem | None:
    """A copy of a Who-is-hiring item shaped as proposal evidence, or `None`.

    The persisted item stays a normal job (it must normalize); only this copy carries the
    ATS board URL and the `source_proposal_candidate` marker `propose_from_tavily_evidence`
    reads.
    """
    ats_url = item.metadata.get("ats_board_url")
    if not isinstance(ats_url, str) or not ats_url or not item.company_name:
        return None
    return replace(
        item,
        url=ats_url,
        metadata={**item.metadata, "source_proposal_candidate": True},
    )


def _tavily_proposal_configuration(
    *,
    company: Company,
    source_type: str,
    board_key: str,
    item: CollectedItem,
    discovery_via: str = "tavily_search",
) -> dict[str, Any]:
    metadata = item.metadata
    configuration: dict[str, Any] = {
        "company_name": company.canonical_name,
        IDENTIFIER_KEYS[source_type]: board_key,
        "discovery_evidence": item.url,
        "discovery_via": discovery_via,
    }
    for metadata_key, configuration_key in (
        ("query", "discovery_query"),
        ("rank", "discovery_rank"),
        ("score", "discovery_score"),
        # F20-53: startup signal evidence, only present on the startup search route.
        ("startup_signal_strength", "startup_signal_strength"),
        ("startup_signal_terms", "startup_signal_terms"),
        ("startup_boards", "startup_boards"),
    ):
        value = metadata.get(metadata_key)
        if value is not None:
            configuration[configuration_key] = value
    if item.description:
        configuration["discovery_excerpt"] = item.description
    return configuration


def _collector_settings(
    source: SourceDefinitionModel,
) -> tuple[str | None, str | None, str | None]:
    if source.source_type == "ashby":
        return (
            _required_string(source.configuration, "board_identifier"),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    if source.source_type == "lever":
        return (
            _required_string(source.configuration, "site_identifier"),
            _optional_string(source.configuration, "company_name"),
            LeverCollector.validate_instance(
                _required_string(source.configuration, "api_region")
                if "api_region" in source.configuration
                else "global"
            ),
        )
    if source.source_type == "greenhouse":
        return (
            GreenhouseCollector.validate_board_token(
                _required_string(source.configuration, "board_token")
            ),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    if source.source_type == "workday":
        return (
            _required_string(source.configuration, "tenant_identifier"),
            _optional_string(source.configuration, "company_name"),
            _required_string(source.configuration, "api_region"),
        )
    if source.source_type == "teamtailor":
        return (
            _required_string(source.configuration, "company_identifier"),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    if source.source_type == "inhire":
        return (
            _required_string(source.configuration, "tenant_identifier"),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    if source.source_type == "workable":
        return (
            _required_string(source.configuration, "account_identifier"),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    if source.source_type == "factorial":
        return (
            _required_string(source.configuration, "company_identifier"),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    if source.source_type == "jobposting":
        return (
            _required_string(source.configuration, "page_url"),
            _optional_string(source.configuration, "company_name"),
            None,
        )
    return None, None, None


def _network_policy(policy: Mapping[str, Any]) -> CollectionNetworkPolicy:
    supported = {
        "max_retries",
        "retry_delay_seconds",
        "max_retry_delay_seconds",
        "minimum_interval_seconds",
        "minimum_run_interval_seconds",
        "requests_per_second",
    }
    unknown = sorted(str(key) for key in policy if key not in supported)
    if unknown:
        raise AcquisitionError(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"unsupported rate limit policy fields: {', '.join(unknown)}",
        )

    def number(key: str, default: float) -> float:
        value = policy.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"rate limit policy {key} must be numeric",
            )
        numeric_value = float(value)
        if not isfinite(numeric_value):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"rate limit policy {key} must be finite",
            )
        return numeric_value

    max_retries = policy.get("max_retries", 2)
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise AcquisitionError(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            "rate limit policy max_retries must be an integer",
        )
    minimum_interval = number("minimum_interval_seconds", 0.0)
    if "requests_per_second" in policy:
        requests_per_second = number("requests_per_second", 0.0)
        if requests_per_second <= 0:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "rate limit policy requests_per_second must be positive",
            )
        minimum_interval = max(minimum_interval, 1.0 / requests_per_second)
    try:
        return CollectionNetworkPolicy(
            max_retries=max_retries,
            retry_delay_seconds=number("retry_delay_seconds", 1.0),
            max_retry_delay_seconds=number("max_retry_delay_seconds", 30.0),
            minimum_interval_seconds=minimum_interval,
            minimum_run_interval_seconds=(
                number("minimum_run_interval_seconds", 0.0)
                if "minimum_run_interval_seconds" in policy
                else None
            ),
        )
    except ValueError as error:
        raise AcquisitionError(AcquisitionErrorCode.INVALID_CONFIGURATION, str(error)) from error


def _reject_secret_configuration(configuration: Mapping[str, Any]) -> None:
    forbidden_fragments = ("password", "secret", "private_key", "api_key", "access_token")
    for key, value in configuration.items():
        normalized_key = str(key).casefold()
        if any(fragment in normalized_key for fragment in forbidden_fragments):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"source configuration cannot store secret field: {key}",
            )
        if isinstance(value, Mapping):
            _reject_secret_configuration(value)
