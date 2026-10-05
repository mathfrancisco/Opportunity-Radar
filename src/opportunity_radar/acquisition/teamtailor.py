"""Teamtailor public jobs-feed collector.

Every Teamtailor-hosted career site publishes a public, unauthenticated JSON Feed 1.1
document at `https://<career-domain>/jobs.json` (JSON Feed spec: https://jsonfeed.org/
version/1.1), with per-job `schema.org/JobPosting` data embedded under `_jobposting`. The
domain is per-company (a Teamtailor subdomain or a custom domain the company points at its
board), so — unlike Lever or Greenhouse, which key a board by a short slug under one fixed
host — the identifier this collector needs is the whole career-site hostname.

The feed does not paginate: `docs/pesquisas/termos-teamtailor.md` (the terms review this
card requires before any code) confirms against two real boards that a single `GET
/jobs.json` returns every published job with no `next_url` or page parameter, and that
`robots.txt` does not disallow it. `capabilities.pagination` is therefore `False`, correcting
the card's original hypothesis of a paginated feed.
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
from opportunity_radar.acquisition.http_client import default_collector_client
from opportunity_radar.acquisition.http_conditional import (
    NotModifiedResponse,
    conditional_request_headers,
    record_conditional_response,
)

# A career-site hostname: labels of letters/digits/hyphens separated by dots, no scheme,
# no path, no port. Rejects anything that is not a bare hostname so a caller cannot smuggle
# a path or query string into the request through the identifier.
_HOSTNAME = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)
_PARSER_VERSION = "teamtailor-jobs-feed-v1"


class TeamtailorCollector:
    """Reads public postings from a Teamtailor-hosted career site's JSON Feed."""

    source_type = "teamtailor"
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
        self._client_factory = client_factory or default_collector_client
        self._max_retries = max_retries
        self._retry_after_seconds = retry_after_seconds
        self._sleeper = sleeper

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        return HealthResult(
            healthy=True,
            summary="Teamtailor public jobs-feed collector is configured",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        domain = self.validate_company_identifier(request.company_reference)
        try:
            items = await self._fetch_items(domain, request)
        except NotModifiedResponse:
            return
        emitted = 0
        for job in items:
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
        if request.max_items is None:
            # The feed is unpaginated: a single successful fetch is the whole board, so its
            # item count is the announced total (same rule as a Lever short final page).
            request.telemetry.record_items_announced(len(items))

    async def _fetch_items(
        self, domain: str, request: CollectionRequest
    ) -> list[Mapping[str, Any]]:
        if self._client is not None:
            return await self._fetch_items_with_client(self._client, domain, request)
        async with self._client_factory() as client:
            return await self._fetch_items_with_client(client, domain, request)

    async def _fetch_items_with_client(
        self, client: httpx.AsyncClient, domain: str, request: CollectionRequest
    ) -> list[Mapping[str, Any]]:
        url = f"https://{quote(domain)}/jobs.json"
        policy = request.network_policy
        max_retries = policy.max_retries if policy is not None else self._max_retries
        retry_delay = (
            policy.retry_delay_seconds if policy is not None else self._retry_after_seconds
        )
        max_retry_delay = policy.max_retry_delay_seconds if policy is not None else 30.0
        minimum_interval = policy.minimum_interval_seconds if policy is not None else 0.0
        await self._wait_for_minimum_interval(request, minimum_interval)
        for attempt in range(max_retries + 1):
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.get(
                    url, headers=conditional_request_headers(request) or None
                )
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                if response.status_code == 304:
                    record_conditional_response(request, response)
                    raise NotModifiedResponse()
                record_conditional_response(request, response)
                error = self._response_error(response)
                if error is None:
                    return self._items(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Teamtailor request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Teamtailor",
                    retryable=True,
                )
            assert error is not None
            if not error.retryable or attempt == max_retries:
                raise error
            await self._sleeper(
                max(
                    minimum_interval,
                    self._retry_delay(response, default=retry_delay, maximum=max_retry_delay),
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
    def validate_company_identifier(value: str | None) -> str:
        if value is None or not _HOSTNAME.fullmatch(value):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Teamtailor company_identifier must be a bare career-site hostname"
                " (no scheme, path or port)",
            )
        return value

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
                f"Teamtailor returned HTTP {status}",
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
                f"Teamtailor returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Teamtailor returned HTTP {status}",
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
    def _items(response: httpx.Response) -> list[Mapping[str, Any]]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor returned invalid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor response must be a JSON Feed object",
            )
        items = payload.get("items")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor response items must be a list of objects",
            )
        return items

    @staticmethod
    def _item(job: Mapping[str, Any], *, company_name: str | None) -> CollectedItem:
        external_id = job.get("id")
        job_url = job.get("url")
        if not isinstance(external_id, str) or not external_id:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor job is missing an id",
            )
        if not isinstance(job_url, str) or not TeamtailorCollector._is_http_url(job_url):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor job is missing a valid url",
            )
        jobposting = job.get("_jobposting")
        if jobposting is not None and not isinstance(jobposting, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor job _jobposting must be an object",
            )
        return CollectedItem(
            source_type=TeamtailorCollector.source_type,
            external_id=external_id,
            url=job_url,
            title=TeamtailorCollector._string(job.get("title")),
            company_name=company_name,
            location_text=TeamtailorCollector._location_text(jobposting),
            description=TeamtailorCollector._string(job.get("content_html")),
            published_at=TeamtailorCollector._published_at(job.get("date_published")),
            raw_payload=job,
            metadata={
                "hiring_organization": (jobposting or {}).get("hiringOrganization"),
                "job_location": (jobposting or {}).get("jobLocation"),
                "date_posted": (jobposting or {}).get("datePosted"),
                "parser_version": _PARSER_VERSION,
            },
        )

    @staticmethod
    def _location_text(jobposting: Mapping[str, Any] | None) -> str | None:
        # The feed exposes location only as free-form schema.org JobLocation/PostalAddress
        # data (docs/pesquisas/termos-teamtailor.md); there is no structured city/country
        # field to key off, so this is a best-effort join, never a fabricated mapping.
        if not jobposting:
            return None
        location = jobposting.get("jobLocation")
        candidate = location[0] if isinstance(location, list) and location else location
        if not isinstance(candidate, dict):
            return None
        address = candidate.get("address")
        if isinstance(address, dict):
            candidate = address
        elif not isinstance(candidate, dict):
            return None
        parts = [
            candidate.get("addressLocality"),
            candidate.get("addressRegion"),
            candidate.get("addressCountry"),
        ]
        text = ", ".join(part for part in parts if isinstance(part, str) and part)
        return text or None

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
                "Teamtailor date_published must be a string",
            )
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Teamtailor date_published is invalid",
            ) from error
