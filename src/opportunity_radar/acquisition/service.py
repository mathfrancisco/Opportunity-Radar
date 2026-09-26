"""Application service that turns collector output into immutable raw evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import ceil, isfinite
from typing import Any, Literal
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
    evaluate_completeness,
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
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
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.scheduling import (
    SourceSchedulingState,
    default_schedule_for_priority,
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
from opportunity_radar.platform.logging import get_logger

COLLECTED_ITEM_V1_KEY = "collected_item_v1"

logger = get_logger("opportunity_radar.acquisition.service")


@dataclass(frozen=True, slots=True)
class TavilyProposalOutcome:
    url: str
    outcome: Literal[
        "created", "already_proposed", "unmatched_pattern", "company_not_found"
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


class SourceDisabledError(AcquisitionError):
    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"source is disabled: {source_id}",
        )


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
        source_rate_limit_policy = dict(rate_limit_policy or {})
        with _refusing_field("rate_limit_policy"):
            resolved_network_policy = _network_policy(source_rate_limit_policy)
        if schedule is None and company_source_id is not None:
            schedule = self._default_schedule(
                company_source_id, resolved_network_policy
            )
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
        if enabled and normalized_type != "manual" and (
            evidence_status != "confirmed"
            or reviewed_at is None
            or not terms_reviewed
            or not collector_local_tested
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
            if commit:
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

    def list_sources(
        self, *, offset: int, limit: int
    ) -> tuple[list[SourceDefinitionModel], int]:
        return self.repository.list_sources(offset=offset, limit=limit)

    def get_source(self, source_id: UUID) -> SourceDefinitionModel | None:
        return self.repository.get_source(source_id)

    def propose_company_source(
        self, company_id: UUID
    ) -> tuple[SourceDefinitionModel | None, str]:
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
                CompanySource.source_type.in_(("ashby", "lever", "greenhouse")),
                CompanySource.external_key.is_not(None),
            )
            .order_by(CompanySource.id)
        )
        if candidate is None:
            return None, "not_detected"
        existing = self.session.scalar(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.company_source_id == candidate.id,
                SourceDefinitionModel.source_type == candidate.source_type,
            )
        )
        if existing is not None:
            return existing, "already_proposed"
        identifier_key = IDENTIFIER_KEYS[candidate.source_type]
        proposal = self.create_source(
            source_type=candidate.source_type,
            name=f"Proposed {company.canonical_name} {candidate.source_type}",
            company_source_id=candidate.id,
            configuration={
                "company_name": company.canonical_name,
                identifier_key: candidate.external_key,
                "discovery_evidence": candidate.evidence_note or candidate.endpoint,
            },
            evidence_status="ats_identified",
        )
        return proposal, "proposed"

    def propose_from_tavily_evidence(
        self, items: Iterable[CollectedItem], *, commit: bool = True
    ) -> TavilyProposalReport:
        """Turn marked, persisted Tavily results into inert ATS source proposals.

        Company names intentionally use exact canonical-name equality.  A Tavily search
        result is evidence of a board, not authority to guess which company owns it.
        """
        outcomes: list[TavilyProposalOutcome] = []
        for item in items:
            if item.metadata.get("source_proposal_candidate") is not True:
                continue
            url = item.url or ""
            detected = detect_ats_board(url)
            if detected is None:
                outcomes.append(TavilyProposalOutcome(url, "unmatched_pattern"))
                continue
            source_type, board_key = detected
            companies = (
                self.session.scalars(
                    select(Company)
                    .where(Company.canonical_name == item.company_name)
                    .limit(2)
                ).all()
                if item.company_name
                else []
            )
            if len(companies) != 1:
                outcomes.append(TavilyProposalOutcome(url, "company_not_found"))
                continue
            company = companies[0]

            identifier_key = IDENTIFIER_KEYS[source_type]
            by_board = self.session.scalar(
                select(SourceDefinitionModel).where(
                    SourceDefinitionModel.source_type == source_type,
                    SourceDefinitionModel.configuration[identifier_key].as_string()
                    == board_key,
                )
            )
            if by_board is not None:
                outcomes.append(
                    TavilyProposalOutcome(url, "already_proposed", by_board.id)
                )
                continue

            by_company = self.session.scalar(
                select(SourceDefinitionModel)
                .where(
                    SourceDefinitionModel.source_type == source_type,
                    SourceDefinitionModel.configuration["company_name"].as_string()
                    == company.canonical_name,
                    SourceDefinitionModel.configuration["discovery_via"].as_string()
                    == "tavily_search",
                )
                .order_by(SourceDefinitionModel.created_at)
            )
            configuration = _tavily_proposal_configuration(
                company=company,
                source_type=source_type,
                board_key=board_key,
                item=item,
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
        if enabled and source.source_type != "manual" and (
            source.evidence_status != "confirmed"
            or effective_reviewed_at is None
            or not terms_reviewed
            or not collector_local_tested
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
        network_policy = _network_policy(source.rate_limit_policy or {})
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

    def _probe_wait(
        self, source: SourceDefinitionModel, policy: CollectionNetworkPolicy
    ) -> int:
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
        policy = _network_policy(source.rate_limit_policy or {})
        return SourceSchedulingState(
            schedule=source.schedule,
            timezone=timezone,
            history=self.repository.run_history(source.id),
            last_http_attempt_at=source.last_http_attempt_at,
            minimum_run_interval_seconds=policy.minimum_run_interval_seconds,
        )

    def get_run(self, run_id: UUID) -> SourceRunModel | None:
        return self.repository.get_run(run_id)

    def list_runs(
        self, *, offset: int, limit: int, source_id: UUID | None = None
    ) -> tuple[list[SourceRunModel], int]:
        return self.repository.list_runs(offset=offset, limit=limit, source_id=source_id)

    async def execute(self, source_id: UUID, request: CollectionRequest) -> SourceRunModel:
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
        if (
            source.source_type == "manual"
            and request.mode is not CollectionMode.MANUAL
        ):
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
        network_policy = _network_policy(source.rate_limit_policy or {})
        run_telemetry = CollectionTelemetry()

        checkpoint_before = source.checkpoint.cursor if source.checkpoint else None
        run = SourceRun(
            source_definition_id=source.id,
            execution_trigger=request.execution_trigger,
            checkpoint_before=checkpoint_before,
        )
        run.start()
        persisted_run = SourceRunModel(
            id=run.id,
            source_definition_id=source.id,
            execution_trigger=run.execution_trigger.value,
            status=run.status.value,
            started_at=run.started_at,
            checkpoint_before=checkpoint_before,
            correlation_id=request.correlation_id,
        )
        self.session.add(persisted_run)
        try:
            self.session.flush()
        except IntegrityError as conflict:
            self.session.rollback()
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source already has an active run",
                retryable=True,
            ) from conflict

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
        if (
            last_http_attempt_at is not None
            and minimum_run_interval
        ):
            elapsed = (datetime.now(UTC) - last_http_attempt_at).total_seconds()
            delay = minimum_run_interval - elapsed
            if delay > 0:
                if network_policy.minimum_run_interval_seconds is not None:
                    run_telemetry.record_rate_limit()
                    throttle_error = AcquisitionError(
                        AcquisitionErrorCode.SOURCE_RATE_LIMITED,
                        "source run interval has not elapsed; "
                        f"retry in {ceil(delay)} seconds",
                        retryable=True,
                    )
                else:
                    await self._sleeper(delay)

        error: AcquisitionError | None = None
        last_cursor: str | None = None
        tavily_proposal_items: list[CollectedItem] = []
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
        extraction_budget = (
            TavilyCreditBudget(limit=self._tavily_extraction.credit_budget_per_run)
            if self._tavily_extraction is not None
            else None
        )
        try:
            if throttle_error is not None:
                raise throttle_error
            company_reference, company_name, api_region = _collector_settings(source)
            collector_request = replace(
                request,
                source_definition_id=source.id,
                cursor=(
                    checkpoint_before
                    if request.cursor is None and checkpoint_before is not None
                    else request.cursor
                ),
                company_reference=company_reference or request.company_reference,
                company_name=company_name or request.company_name,
                api_region=api_region or request.api_region,
                telemetry=run_telemetry,
                network_policy=network_policy,
                known_ats_boards=(
                    self.repository.enabled_ats_boards()
                    if source.source_type == "tavily_search"
                    else request.known_ats_boards
                ),
            )
            async for item in collector.discover(collector_request):
                run.record_items(seen=1)
                item = await self._fill_missing_description(
                    item,
                    client=extraction_client,
                    budget=extraction_budget,
                    telemetry=run_telemetry,
                    network_policy=network_policy,
                    run=run,
                )
                try:
                    created = self._persist_item(
                        source.id,
                        run.id,
                        source.source_type,
                        item,
                    )
                except (TypeError, ValueError) as item_error:
                    run.record_items(invalid=1)
                    error = AcquisitionError(
                        AcquisitionErrorCode.INVALID_ITEM, str(item_error), retryable=False
                    )
                    continue
                if created:
                    run.record_items(persisted=1)
                else:
                    run.record_items(skipped=1)
                if source.source_type == "tavily_search":
                    tavily_proposal_items.append(item)
                if item.cursor is not None:
                    last_cursor = item.cursor
            # `_persist_item` flushed every candidate's immutable raw evidence before
            # this pass.  A proposal failure is isolated to a savepoint so it cannot
            # erase that evidence or the source run that explains it.
            if tavily_proposal_items:
                try:
                    with self.session.begin_nested():
                        self.propose_from_tavily_evidence(
                            tavily_proposal_items, commit=False
                        )
                except Exception as proposal_error:
                    error = AcquisitionError(
                        AcquisitionErrorCode.INVALID_CONFIGURATION,
                        f"tavily source proposal failed: {proposal_error}",
                    )
        except AcquisitionError as caught:
            error = caught
        except Exception as caught:  # Preserve a stable external error boundary.
            error = AcquisitionError(AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR, str(caught))
        finally:
            if extraction_client is not None:
                await extraction_client.aclose()

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
                SourceRunStatus.PARTIAL
                if run.items_invalid
                else SourceRunStatus.SUCCEEDED
            )
        elif error.code in {
            AcquisitionErrorCode.INVALID_ITEM,
            AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED,
        }:
            final_status = SourceRunStatus.PARTIAL
        elif run.items_persisted:
            final_status = SourceRunStatus.PARTIAL
        else:
            final_status = SourceRunStatus.FAILED
        run.finish(
            final_status,
            error=error if final_status is not SourceRunStatus.SUCCEEDED else None,
            checkpoint_after=(
                last_cursor if final_status is SourceRunStatus.SUCCEEDED else None
            ),
        )
        run.items_announced = run_telemetry.items_announced
        run.complete = evaluate_completeness(
            status=run.status,
            max_items=request.max_items,
            items_seen=run.items_seen,
            items_announced=run.items_announced,
        )
        self._copy_run(run, persisted_run)
        if run_telemetry.last_http_attempt_at is not None:
            source.last_http_attempt_at = run_telemetry.last_http_attempt_at

        # The checkpoint is part of this same transaction, so it cannot advance before raw evidence.
        if final_status is SourceRunStatus.SUCCEEDED and last_cursor is not None:
            checkpoint = source.checkpoint or SourceCheckpointModel(
                source_definition_id=source.id
            )
            checkpoint.cursor = last_cursor
            checkpoint.checkpoint_type = "cursor"
            checkpoint.promoted_by_run_id = run.id
            checkpoint.promoted_at = datetime.now(UTC)
            self.session.add(checkpoint)
        self.session.commit()
        self.session.refresh(persisted_run)
        self._announce(source, persisted_run, max_items=request.max_items)
        return persisted_run

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
                consecutive_failures=self.repository.run_history(
                    source.id
                ).consecutive_failures,
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
        if (
            self._tavily_extraction is None
            or client is None
            or budget is None
            or item.url is None
        ):
            return item
        if (item.description or "").strip():
            return item
        cache = TavilyExtractionCache(
            session=self.session,
            ttl_seconds=self._tavily_extraction.cache_ttl_seconds,
        )
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
        if self.repository.identical_raw_item_exists(
            source_id=source_id,
            identity_key=identity_key,
            payload_hash=payload_hash,
        ):
            return False
        metadata = _json_object(item.metadata)
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
                    content_type=_string_or_none(metadata.get("content_type")),
                    parser_version=_string_or_none(metadata.get("parser_version")),
                    item_metadata=metadata,
                )
                # Envelope and body are written together: an envelope whose content never
                # arrived would be indistinguishable from one retention has expired.
                raw_item.payload_record = RawItemPayloadModel(payload=payload)
                self.session.add(raw_item)
                self.session.flush()
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


def _tavily_proposal_configuration(
    *,
    company: Company,
    source_type: str,
    board_key: str,
    item: CollectedItem,
) -> dict[str, Any]:
    metadata = item.metadata
    configuration: dict[str, Any] = {
        "company_name": company.canonical_name,
        IDENTIFIER_KEYS[source_type]: board_key,
        "discovery_evidence": item.url,
        "discovery_via": "tavily_search",
    }
    for metadata_key, configuration_key in (
        ("query", "discovery_query"),
        ("rank", "discovery_rank"),
        ("score", "discovery_score"),
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
        raise AcquisitionError(
            AcquisitionErrorCode.INVALID_CONFIGURATION, str(error)
        ) from error


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
