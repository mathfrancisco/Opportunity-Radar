"""Greenhouse public job-board collector."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionRequest,
    CollectorCapabilities,
    HealthcheckContext,
    HealthResult,
    parse_retry_after_seconds,
)

_BOARD_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_PARSER_VERSION = "greenhouse-job-board-v1"
DEFAULT_BASE_URL = "https://boards-api.greenhouse.io"


class GreenhouseCollector:
    """Reads jobs from Greenhouse's unauthenticated public board API."""

    source_type = "greenhouse"
    capabilities = CollectorCapabilities(company_jobs=True)

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        client_factory: (
            Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None
        ) = None,
        max_retries: int = 2,
        retry_after_seconds: float = 1.0,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        # Overridable so the autonomous cycle can be exercised against a local board.
        # Proving that the worker collects on its own requires a source it can actually
        # reach, and a gate that depends on a third party is not a gate.
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        if client is not None and client_factory is not None:
            raise ValueError("provide either client or client_factory, not both")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_after_seconds < 0:
            raise ValueError("retry_after_seconds cannot be negative")
        self._client = client
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
            )
        )
        self._max_retries = max_retries
        self._retry_after_seconds = retry_after_seconds
        self._sleeper = sleeper
        self._base_url = base_url.rstrip("/")

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        return HealthResult(
            healthy=True,
            summary="Greenhouse public job-board collector is configured",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        board = self.validate_board_token(request.company_reference)
        jobs, total = await self._fetch_jobs(board, request)
        request.telemetry.record_items_announced(total)
        emitted = 0
        for job in jobs:
            try:
                item = self._item(job, company_name=request.company_name)
            except AcquisitionError as error:
                if error.code is not AcquisitionErrorCode.PARSER_SCHEMA_CHANGED:
                    raise
                request.telemetry.record_invalid_item(error.summary)
                continue
            yield item
            emitted += 1
            if request.max_items is not None and emitted >= request.max_items:
                return

    @staticmethod
    def validate_board_token(company_reference: str | None) -> str:
        if company_reference is None or not _BOARD_TOKEN.fullmatch(company_reference):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Greenhouse company_reference must be a non-empty board token",
            )
        return company_reference

    async def _fetch_jobs(
        self, board: str, request: CollectionRequest
    ) -> tuple[list[Mapping[str, Any]], int]:
        if self._client is not None:
            return await self._fetch_jobs_with_client(self._client, board, request)
        async with self._client_factory() as client:
            return await self._fetch_jobs_with_client(client, board, request)

    async def _fetch_jobs_with_client(
        self,
        client: httpx.AsyncClient,
        board: str,
        request: CollectionRequest,
    ) -> tuple[list[Mapping[str, Any]], int]:
        url = f"{self._base_url}/v1/boards/{quote(board)}/jobs"
        policy = request.network_policy
        max_retries = policy.max_retries if policy is not None else self._max_retries
        retry_delay = (
            policy.retry_delay_seconds
            if policy is not None
            else self._retry_after_seconds
        )
        max_retry_delay = (
            policy.max_retry_delay_seconds if policy is not None else 30.0
        )
        minimum_interval = (
            policy.minimum_interval_seconds if policy is not None else 0.0
        )
        await self._wait_for_minimum_interval(request, minimum_interval)
        for attempt in range(max_retries + 1):
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.get(url, params={"content": "true"})
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response)
                if error is None:
                    return self._jobs(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Greenhouse request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Greenhouse",
                    retryable=True,
                )

            assert error is not None
            if not error.retryable or attempt == max_retries:
                raise error
            await self._sleeper(
                max(
                    minimum_interval,
                    self._retry_delay(
                        response,
                        default=retry_delay,
                        maximum=max_retry_delay,
                    ),
                )
            )

        raise AssertionError("unreachable")

    async def _wait_for_minimum_interval(
        self, request: CollectionRequest, minimum_interval: float
    ) -> None:
        last_attempt = request.telemetry.last_http_attempt_at
        if last_attempt is None or minimum_interval == 0:
            return
        elapsed = (datetime.now(UTC) - last_attempt).total_seconds()
        delay = minimum_interval - elapsed
        if delay > 0:
            await self._sleeper(delay)

    @staticmethod
    def _response_error(response: httpx.Response) -> AcquisitionError | None:
        status = response.status_code
        if 200 <= status < 300:
            return None
        codes = {
            401: AcquisitionErrorCode.SOURCE_UNAUTHORIZED,
            403: AcquisitionErrorCode.SOURCE_FORBIDDEN,
            404: AcquisitionErrorCode.SOURCE_NOT_FOUND,
            429: AcquisitionErrorCode.SOURCE_RATE_LIMITED,
        }
        code = codes.get(status)
        if code is not None:
            return AcquisitionError(
                code,
                f"Greenhouse returned HTTP {status}",
                retryable=status == 429,
                retry_after_seconds=(
                    parse_retry_after_seconds(response.headers.get("Retry-After"))
                    if status == 429
                    else None
                ),
            )
        if 500 <= status < 600:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                f"Greenhouse returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Greenhouse returned HTTP {status}",
        )

    def _retry_delay(
        self,
        response: httpx.Response | None,
        *,
        default: float,
        maximum: float,
    ) -> float:
        delay = default
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    parsed_seconds = float(retry_after)
                except ValueError:
                    try:
                        parsed_date = parsedate_to_datetime(retry_after)
                        if parsed_date.tzinfo is None:
                            parsed_date = parsed_date.replace(tzinfo=UTC)
                        parsed_seconds = (parsed_date - datetime.now(UTC)).total_seconds()
                    except (TypeError, ValueError, OverflowError):
                        parsed_seconds = default
                if math.isfinite(parsed_seconds):
                    delay = max(0.0, parsed_seconds)
        return min(delay, maximum)

    @staticmethod
    def _jobs(response: httpx.Response) -> tuple[list[Mapping[str, Any]], int]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse returned invalid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse response must be an object",
            )
        jobs = payload.get("jobs")
        meta = payload.get("meta")
        if not isinstance(jobs, list) or any(
            not isinstance(job, dict) for job in jobs
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse response jobs must be a list of objects",
            )
        if not isinstance(meta, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse response meta must be an object",
            )
        total = meta.get("total")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse response meta.total must be a non-negative integer",
            )
        return jobs, total

    @staticmethod
    def _item(
        job: Mapping[str, Any], *, company_name: str | None
    ) -> CollectedItem:
        external_id = GreenhouseCollector._external_id(job.get("id"))
        job_url = job.get("absolute_url")
        if not isinstance(job_url, str) or not GreenhouseCollector._is_http_url(
            job_url
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse job is missing a valid absolute_url",
            )
        location = job.get("location")
        if location is not None and not isinstance(location, Mapping):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse job location must be an object",
            )
        return CollectedItem(
            source_type=GreenhouseCollector.source_type,
            external_id=external_id,
            url=job_url,
            title=GreenhouseCollector._string(job.get("title")),
            company_name=company_name,
            location_text=GreenhouseCollector._string((location or {}).get("name")),
            description=GreenhouseCollector._string(job.get("content")),
            updated_at=GreenhouseCollector._updated_at(job.get("updated_at")),
            raw_payload=job,
            metadata={
                "internal_job_id": job.get("internal_job_id"),
                "requisition_id": job.get("requisition_id"),
                "language": job.get("language"),
                "departments": job.get("departments"),
                "offices": job.get("offices"),
                "greenhouse_metadata": job.get("metadata"),
                "parser_version": _PARSER_VERSION,
            },
        )

    @staticmethod
    def _external_id(value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse job id must be a string or integer",
            )
        normalized = str(value)
        if not normalized:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse job id must not be empty",
            )
        return normalized

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _updated_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse updated_at must be a string",
            )
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Greenhouse updated_at is invalid",
            ) from error
