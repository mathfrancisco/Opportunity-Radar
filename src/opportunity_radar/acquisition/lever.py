"""Lever public postings collector."""

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
)

_SITE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_PAGE_SIZE = 100
_PARSER_VERSION = "lever-postings-v1"


class LeverCollector:
    """Reads public postings from Lever's global or EU API instance."""

    source_type = "lever"
    capabilities = CollectorCapabilities(company_jobs=True, pagination=True)

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        client_factory: (
            Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None
        ) = None,
        instance: str = "global",
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
        self._instance = self.validate_instance(instance)
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
            summary="Lever public postings collector is configured",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        site = self.validate_site_slug(request.company_reference)
        instance = self.validate_instance(request.api_region or self._instance)
        emitted = 0
        skip = 0
        if self._client is not None:
            async for item in self._discover_with_client(
                self._client, site, instance, request, skip, emitted
            ):
                emitted += 1
                yield item
            return
        async with self._client_factory() as client:
            async for item in self._discover_with_client(
                client, site, instance, request, skip, emitted
            ):
                yield item

    async def _discover_with_client(
        self,
        client: httpx.AsyncClient,
        site: str,
        instance: str,
        request: CollectionRequest,
        skip: int,
        emitted: int,
    ) -> AsyncIterator[CollectedItem]:
        seen_pages: set[tuple[tuple[str, str], ...]] = set()
        while request.max_items is None or emitted < request.max_items:
            remaining = (
                None if request.max_items is None else request.max_items - emitted
            )
            limit = min(_PAGE_SIZE, remaining) if remaining is not None else _PAGE_SIZE
            postings = await self._fetch_page(
                client, site, instance, skip, limit, request
            )
            page_signature = tuple(
                (str(posting.get("id")), str(posting.get("hostedUrl")))
                for posting in postings
            )
            if postings and page_signature in seen_pages:
                raise AcquisitionError(
                    AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                    "Lever pagination repeated a page without making progress",
                )
            seen_pages.add(page_signature)
            for posting in postings:
                try:
                    item = self._item(posting, company_name=request.company_name)
                except AcquisitionError as error:
                    if error.code is not AcquisitionErrorCode.PARSER_SCHEMA_CHANGED:
                        raise
                    request.telemetry.record_invalid_item(error.summary)
                    continue
                yield item
                emitted += 1
                if request.max_items is not None and emitted >= request.max_items:
                    return
            if len(postings) < limit:
                return
            skip += len(postings)

    @staticmethod
    def validate_site_slug(company_reference: str | None) -> str:
        if company_reference is None or not _SITE_SLUG.fullmatch(company_reference):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Lever company_reference must be a non-empty site slug",
            )
        return company_reference

    @staticmethod
    def validate_instance(instance: str) -> str:
        normalized = instance.casefold()
        if normalized not in {"global", "eu"}:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Lever api_region must be global or eu",
            )
        return normalized

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        site: str,
        instance: str,
        skip: int,
        limit: int,
        request: CollectionRequest,
    ) -> list[Mapping[str, Any]]:
        host = "api.eu.lever.co" if instance == "eu" else "api.lever.co"
        url = f"https://{host}/v0/postings/{quote(site)}"
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
                    url, params={"mode": "json", "skip": skip, "limit": limit}
                )
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response)
                if error is None:
                    return self._postings(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Lever request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Lever",
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
                code, f"Lever returned HTTP {status}", retryable=status == 429
            )
        if 500 <= status < 600:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                f"Lever returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR, f"Lever returned HTTP {status}"
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
    def _postings(response: httpx.Response) -> list[Mapping[str, Any]]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Lever returned invalid JSON"
            ) from error
        if not isinstance(payload, list) or any(
            not isinstance(item, dict) for item in payload
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Lever response must be a list of objects",
            )
        return payload

    @staticmethod
    def _item(
        posting: Mapping[str, Any], *, company_name: str | None
    ) -> CollectedItem:
        external_id = posting.get("id")
        hosted_url = posting.get("hostedUrl")
        if not isinstance(external_id, str) or not external_id:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Lever posting is missing an id",
            )
        if not isinstance(hosted_url, str) or not LeverCollector._is_http_url(
            hosted_url
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Lever posting is missing a valid hostedUrl",
            )
        categories = posting.get("categories")
        if categories is not None and not isinstance(categories, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Lever posting categories must be an object",
            )
        return CollectedItem(
            source_type=LeverCollector.source_type,
            external_id=external_id,
            url=hosted_url,
            title=LeverCollector._string(posting.get("text")),
            company_name=company_name,
            location_text=LeverCollector._string((categories or {}).get("location")),
            description=LeverCollector._string(posting.get("descriptionPlain")),
            raw_payload=posting,
            metadata={
                "categories": categories,
                "country": posting.get("country"),
                "applyUrl": posting.get("applyUrl"),
                "workplaceType": posting.get("workplaceType"),
                "salaryRange": posting.get("salaryRange"),
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
