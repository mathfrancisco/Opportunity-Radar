"""Remotive public remote-jobs collector."""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

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

_API_URL = "https://remotive.com/api/remote-jobs"
_PARSER_VERSION = "remotive-remote-jobs-v1"


class RemotiveCollector:
    """Reads keyword-filtered jobs from Remotive's public API."""

    source_type = "remotive"
    capabilities = CollectorCapabilities(keyword_search=True)

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
        return HealthResult(
            healthy=True,
            summary="Remotive public jobs collector is configured",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        jobs = await self._fetch_jobs(request)
        emitted = 0
        for job in jobs:
            try:
                item = self._item(job)
            except AcquisitionError as error:
                if error.code is not AcquisitionErrorCode.PARSER_SCHEMA_CHANGED:
                    raise
                request.telemetry.record_invalid_item(error.summary)
                continue
            yield item
            emitted += 1
            if request.max_items is not None and emitted >= request.max_items:
                return

    async def _fetch_jobs(
        self, request: CollectionRequest
    ) -> list[Mapping[str, Any]]:
        if self._client is not None:
            return await self._fetch_jobs_with_client(self._client, request)
        async with self._client_factory() as client:
            return await self._fetch_jobs_with_client(client, request)

    async def _fetch_jobs_with_client(
        self, client: httpx.AsyncClient, request: CollectionRequest
    ) -> list[Mapping[str, Any]]:
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
        params: dict[str, str | int] = {}
        if request.keywords:
            params["search"] = " ".join(
                keyword.strip() for keyword in request.keywords
            )
        if request.max_items is not None:
            params["limit"] = request.max_items

        await self._wait_for_minimum_interval(request, minimum_interval)
        for attempt in range(max_retries + 1):
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.get(_API_URL, params=params)
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response)
                if error is None:
                    return self._jobs(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Remotive request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Remotive",
                    retryable=True,
                )

            assert error is not None
            if not error.retryable or attempt == max_retries:
                raise error
            await self._sleeper(
                max(
                    minimum_interval,
                    self._retry_delay(
                        response, default=retry_delay, maximum=max_retry_delay
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
                f"Remotive returned HTTP {status}",
                retryable=status == 429,
            )
        if 500 <= status < 600:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                f"Remotive returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Remotive returned HTTP {status}",
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
    def _jobs(response: httpx.Response) -> list[Mapping[str, Any]]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive returned invalid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive response must be an object",
            )
        jobs = payload.get("jobs")
        count = payload.get("job-count")
        if not isinstance(jobs, list) or any(
            not isinstance(job, dict) for job in jobs
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive response jobs must be a list of objects",
            )
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive response job-count must be a non-negative integer",
            )
        if count != len(jobs):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive response job-count must equal the returned jobs",
            )
        return jobs

    @staticmethod
    def _item(job: Mapping[str, Any]) -> CollectedItem:
        external_id = RemotiveCollector._external_id(job.get("id"))
        job_url = job.get("url")
        if not isinstance(job_url, str) or not RemotiveCollector._is_http_url(
            job_url
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive job is missing a valid url",
            )
        return CollectedItem(
            source_type=RemotiveCollector.source_type,
            external_id=external_id,
            url=job_url,
            title=RemotiveCollector._string(job.get("title")),
            company_name=RemotiveCollector._string(job.get("company_name")),
            location_text=RemotiveCollector._string(
                job.get("candidate_required_location")
            ),
            description=RemotiveCollector._string(job.get("description")),
            published_at=RemotiveCollector._published_at(
                job.get("publication_date")
            ),
            raw_payload=job,
            metadata={
                "category": job.get("category"),
                "job_type": job.get("job_type"),
                "salary": job.get("salary"),
                "company_logo": job.get("company_logo"),
                "attribution": "Remotive",
                "parser_version": _PARSER_VERSION,
            },
        )

    @staticmethod
    def _external_id(value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive job id must be a string or integer",
            )
        normalized = str(value)
        if not normalized:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive job id must not be empty",
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
    def _published_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive publication_date must be a string",
            )
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Remotive publication_date is invalid",
            ) from error
