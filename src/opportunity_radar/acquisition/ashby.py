"""Ashby public job-board collector."""

from __future__ import annotations

import asyncio
import hashlib
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
)

_BOARD_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_PARSER_VERSION = "ashby-job-board-v2"


class AshbyCollector:
    """Reads listed jobs from Ashby's unauthenticated public job-board API."""

    source_type = "ashby"
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

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        return HealthResult(healthy=True, summary="Ashby public job-board collector is configured")

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        board = self.validate_board_identifier(request.company_reference)
        payload = await self._fetch_jobs(board, request)
        jobs = self._jobs(payload)
        request.telemetry.record_items_announced(len(jobs))
        emitted = 0
        for job in jobs:
            if job.get("isListed") is not True:
                continue
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
    def validate_board_identifier(company_reference: str | None) -> str:
        if company_reference is None or not _BOARD_IDENTIFIER.fullmatch(company_reference):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Ashby company_reference must be a non-empty job-board slug",
            )
        return company_reference

    async def _fetch_jobs(
        self, board: str, request: CollectionRequest
    ) -> Mapping[str, Any]:
        if self._client is not None:
            return await self._fetch_jobs_with_client(self._client, board, request)
        async with self._client_factory() as client:
            return await self._fetch_jobs_with_client(client, board, request)

    async def _fetch_jobs_with_client(
        self,
        client: httpx.AsyncClient,
        board: str,
        request: CollectionRequest,
    ) -> Mapping[str, Any]:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{quote(board)}"
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
        for attempt in range(max_retries + 1):
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.get(
                    url, params={"includeCompensation": "true"}
                )
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response)
                if error is None:
                    return self._json_payload(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Ashby request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Ashby",
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
                f"Ashby returned HTTP {status}",
                retryable=status == 429,
            )
        if 500 <= status < 600:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                f"Ashby returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR, f"Ashby returned HTTP {status}"
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
    def _json_payload(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Ashby returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Ashby response must be an object"
            )
        return payload

    @staticmethod
    def _jobs(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        if payload.get("apiVersion") != "1":
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Ashby response apiVersion is unsupported",
            )
        jobs = payload.get("jobs")
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Ashby response jobs must be a list of objects",
            )
        return jobs

    @staticmethod
    def _item(
        job: Mapping[str, Any], *, company_name: str | None
    ) -> CollectedItem:
        job_url = job.get("jobUrl")
        if not isinstance(job_url, str) or not AshbyCollector._is_http_url(job_url):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Ashby listed job is missing a valid jobUrl",
            )
        published_at = AshbyCollector._published_at(job.get("publishedAt"))
        return CollectedItem(
            source_type=AshbyCollector.source_type,
            external_id=f"ashby:{hashlib.sha256(job_url.encode()).hexdigest()}",
            url=job_url,
            title=AshbyCollector._string(job.get("title")),
            company_name=company_name,
            location_text=AshbyCollector._string(job.get("location")),
            description=AshbyCollector._string(job.get("descriptionPlain")),
            published_at=published_at,
            raw_payload=job,
            metadata={
                "applyUrl": job.get("applyUrl"),
                "secondaryLocations": job.get("secondaryLocations"),
                "department": job.get("department"),
                "team": job.get("team"),
                "isRemote": job.get("isRemote"),
                "workplaceType": job.get("workplaceType"),
                "employmentType": job.get("employmentType"),
                "compensation": job.get("compensation"),
                "parser_version": _PARSER_VERSION,
            },
        )

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _published_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Ashby publishedAt must be a string"
            )
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Ashby publishedAt is invalid"
            ) from error
