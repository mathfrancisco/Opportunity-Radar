"""Workable public widget collector.

Every Workable account exposes its active postings through a public, unauthenticated
widget that its own careers page calls:
`GET https://apply.workable.com/api/v1/widget/accounts/<account>?details=true`. With
`details=true` each job carries its HTML description and location detail; without it, the
response omits `description`/`full_description` entirely, so this collector always sends
it.

Terms review: `docs/pesquisas/termos-workable.md`. That review found no pagination
parameter anywhere in the widget: the response is every active job for the account in one
JSON object (`{"jobs": [...]}`). This collector therefore issues exactly one request per
`discover()` call — there is no `skip`/`offset` loop to run, and `CollectorCapabilities`
declares `pagination=False` to say so plainly. A `max_items` cap is applied to the single
response rather than to a page size, and, because the whole board arrives in one answer,
the announced total is always known once that answer parses.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

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
from opportunity_radar.acquisition.http_conditional import (
    NotModifiedResponse,
    conditional_request_headers,
    record_conditional_response,
)

_ACCOUNT_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_PARSER_VERSION = "workable-widget-v1"


class WorkableCollector:
    """Reads public postings from a Workable account's careers widget."""

    source_type = "workable"
    capabilities = CollectorCapabilities(
        company_jobs=True, pagination=False, etag=True, last_modified=True
    )

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
            summary="Workable public widget collector is configured",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        account = self.validate_account_identifier(request.company_reference)
        if self._client is not None:
            async for item in self._discover_with_client(self._client, account, request):
                yield item
            return
        async with self._client_factory() as client:
            async for item in self._discover_with_client(client, account, request):
                yield item

    async def _discover_with_client(
        self,
        client: httpx.AsyncClient,
        account: str,
        request: CollectionRequest,
    ) -> AsyncIterator[CollectedItem]:
        try:
            jobs = await self._fetch_jobs(client, account, request)
        except NotModifiedResponse:
            return
        emitted = 0
        for job in jobs:
            if request.max_items is not None and emitted >= request.max_items:
                # The widget answers with the whole board in one response, so a cap short
                # of its length means the total was seen but not all of it was taken —
                # never announce a count the caller did not actually receive.
                return
            try:
                item = self._item(job, company_name=request.company_name)
            except AcquisitionError as error:
                if error.code is not AcquisitionErrorCode.PARSER_SCHEMA_CHANGED:
                    raise
                request.telemetry.record_invalid_item(error.summary)
                continue
            yield item
            emitted += 1
        # Reaching here (rather than the early return above) means every job in the
        # single response was consumed, so the count is not a guess cut short by
        # max_items — it is the whole board the widget answered with.
        request.telemetry.record_items_announced(emitted)

    @staticmethod
    def validate_account_identifier(company_reference: str | None) -> str:
        if company_reference is None or not _ACCOUNT_SLUG.fullmatch(company_reference):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Workable company_reference must be a non-empty account slug",
            )
        return company_reference

    async def _fetch_jobs(
        self,
        client: httpx.AsyncClient,
        account: str,
        request: CollectionRequest,
    ) -> list[Mapping[str, Any]]:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{account}"
        policy = request.network_policy
        max_retries = policy.max_retries if policy is not None else self._max_retries
        retry_delay = (
            policy.retry_delay_seconds if policy is not None else self._retry_after_seconds
        )
        max_retry_delay = policy.max_retry_delay_seconds if policy is not None else 30.0
        minimum_interval = (
            policy.minimum_interval_seconds if policy is not None else 0.0
        )
        if request.telemetry.last_http_attempt_at is not None and minimum_interval:
            elapsed = (
                datetime.now(UTC) - request.telemetry.last_http_attempt_at
            ).total_seconds()
            delay = minimum_interval - elapsed
            if delay > 0:
                await self._sleeper(delay)
        for attempt in range(max_retries + 1):
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.get(
                    url,
                    params={"details": "true"},
                    headers=conditional_request_headers(request) or None,
                )
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                if response.status_code == 304:
                    record_conditional_response(request, response)
                    raise NotModifiedResponse()
                record_conditional_response(request, response)
                error = self._response_error(response)
                if error is None:
                    return self._jobs(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Workable request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Workable",
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
                f"Workable returned HTTP {status}",
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
                f"Workable returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Workable returned HTTP {status}",
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
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Workable returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable response must be an object",
            )
        jobs = payload.get("jobs")
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable response is missing a jobs list",
            )
        return jobs

    @staticmethod
    def _item(
        job: Mapping[str, Any], *, company_name: str | None
    ) -> CollectedItem:
        external_id = job.get("id") or job.get("shortcode")
        url = job.get("url")
        title = job.get("title")
        if not isinstance(external_id, str) or not external_id:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable job is missing an id",
            )
        if not isinstance(url, str) or not url:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable job is missing a url",
            )
        if not isinstance(title, str) or not title.strip():
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable job is missing a title",
            )
        location = job.get("location")
        if location is not None and not isinstance(location, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable job location must be an object",
            )
        location_text = WorkableCollector._string((location or {}).get("location_str"))
        description = WorkableCollector._string(
            job.get("full_description")
        ) or WorkableCollector._string(job.get("description"))
        return CollectedItem(
            source_type=WorkableCollector.source_type,
            external_id=external_id,
            url=url,
            title=title,
            company_name=company_name,
            location_text=location_text,
            description=description,
            published_at=WorkableCollector._parse_published_on(job.get("published_on")),
            raw_payload=job,
            metadata={
                "workplace_type": (location or {}).get("workplace_type"),
                "telecommuting": (location or {}).get("telecommuting"),
                "experience": job.get("experience"),
                "published_on": job.get("published_on"),
                "created_at": job.get("created_at"),
                "state": job.get("state"),
                "parser_version": _PARSER_VERSION,
            },
        )

    #: Card F20-61. Workable's public widget carries `published_on` (a `YYYY-MM-DD`
    #: date, the real day this posting went live — distinct from `created_at`, which
    #: is a draft's creation time and may predate publication). `None` when the job
    #: has no value (e.g. never published) rather than falling back to `created_at`,
    #: which would misrepresent draft time as publication time.
    @staticmethod
    def _parse_published_on(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable published_on must be a string",
            )
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workable published_on is invalid",
            ) from error

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) else None
