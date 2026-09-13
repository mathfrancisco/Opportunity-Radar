"""Application service that turns collector output into immutable raw evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from math import isfinite
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.repository import AcquisitionRepository


class SourceNotFoundError(AcquisitionError):
    def __init__(self, source_id: UUID) -> None:
        super().__init__(
            AcquisitionErrorCode.INVALID_CONFIGURATION,
            f"source not found: {source_id}",
        )


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
    ) -> None:
        self.session = session
        self.repository = repository or AcquisitionRepository(session)
        self.registry = registry or CollectorRegistry(
            (
                ManualCollector(),
                AshbyCollector(),
                LeverCollector(),
                GreenhouseCollector(),
            )
        )
        self._sleeper = sleeper

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
    ) -> SourceDefinitionModel:
        normalized_type = source_type.strip().casefold()
        normalized_name = name.strip()
        if not normalized_name:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source name cannot be empty",
            )
        self.registry.resolve(normalized_type)
        source_configuration = dict(configuration or {})
        _reject_secret_configuration(source_configuration)
        source_rate_limit_policy = dict(rate_limit_policy or {})
        _network_policy(source_rate_limit_policy)
        if normalized_type == "ashby":
            AshbyCollector.validate_board_identifier(
                _required_string(source_configuration, "board_identifier")
            )
        if normalized_type == "lever":
            LeverCollector.validate_site_slug(
                _required_string(source_configuration, "site_identifier")
            )
            LeverCollector.validate_instance(
                _required_string(source_configuration, "api_region")
                if "api_region" in source_configuration
                else "global"
            )
        if normalized_type == "greenhouse":
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
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source definition conflicts with an existing record",
            ) from error
        self.session.refresh(source)
        return source

    def list_sources(
        self, *, offset: int, limit: int
    ) -> tuple[list[SourceDefinitionModel], int]:
        return self.repository.list_sources(offset=offset, limit=limit)

    def get_source(self, source_id: UUID) -> SourceDefinitionModel | None:
        return self.repository.get_source(source_id)

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
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source definition was changed; refresh it before updating",
            )
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
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "source definition was changed; refresh it before updating",
            )
        self.session.commit()
        self.session.refresh(source)
        return source

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
        network_policy = _network_policy(source.rate_limit_policy or {})
        run_telemetry = CollectionTelemetry()

        checkpoint_before = source.checkpoint.cursor if source.checkpoint else None
        run = SourceRun(source_definition_id=source.id, checkpoint_before=checkpoint_before)
        run.start()
        persisted_run = SourceRunModel(
            id=run.id,
            source_definition_id=source.id,
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
        if (
            last_http_attempt_at is not None
            and network_policy.minimum_interval_seconds
        ):
            elapsed = (datetime.now(UTC) - last_http_attempt_at).total_seconds()
            delay = network_policy.minimum_interval_seconds - elapsed
            if delay > 0:
                await self._sleeper(delay)

        error: AcquisitionError | None = None
        last_cursor: str | None = None
        try:
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
            )
            async for item in collector.discover(collector_request):
                run.record_items(seen=1)
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
                if item.cursor is not None:
                    last_cursor = item.cursor
        except AcquisitionError as caught:
            error = caught
        except Exception as caught:  # Preserve a stable external error boundary.
            error = AcquisitionError(AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR, str(caught))

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

        if error is None:
            final_status = (
                SourceRunStatus.PARTIAL
                if run.items_invalid
                else SourceRunStatus.SUCCEEDED
            )
        elif error.code is AcquisitionErrorCode.INVALID_ITEM:
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
        return persisted_run

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
        try:
            with self.session.begin_nested():
                self.session.add(
                    RawItemModel(
                        source_run_id=run_id,
                        source_definition_id=source_id,
                        external_id=item.external_id,
                        canonical_url=item.url,
                        identity_key=identity_key,
                        payload=payload,
                        payload_hash=payload_hash,
                        content_type=_string_or_none(metadata.get("content_type")),
                        parser_version=_string_or_none(metadata.get("parser_version")),
                        item_metadata=metadata,
                    )
                )
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


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


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
