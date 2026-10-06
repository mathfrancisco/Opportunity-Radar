"""Workday public career-site collector.

Every Workday tenant's career site (`<tenant>.<pod>.myworkdayjobs.com/<site>`) is a
single-page app that reads from an undocumented-but-common JSON backend:
`POST /wday/cxs/<tenant>/<site>/jobs` for the paginated listing, offset/limit based. There
is no authentication and no API key; it is the same request the candidate's browser makes.

Terms review: `docs/pesquisas/termos-workday.md`. The listing endpoint does not expose a
full job description (only title, location text and the detail path), so this collector
never invents one — `description` stays `None`, same as it would for a field the endpoint
genuinely does not carry.

Detail (SPEC 50, F50-03): `GET /wday/cxs/<tenant>/<site><externalPath>` carries the
description. It has not been through the terms review, so it is fetched only when the
source's `fetch_detail` flag is on and only for postings in the profile's target areas.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar

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
from opportunity_radar.opportunities.role_family import (
    classify_role_family,
    departments_from_metadata,
)

_SLUG = r"[A-Za-z0-9][A-Za-z0-9_-]*"
_TENANT_SITE = re.compile(rf"^({_SLUG})/({_SLUG})$")
_POD = re.compile(r"^wd\d+$")
_PAGE_SIZE = 20
_PARSER_VERSION = "workday-cxs-v1"
_T = TypeVar("_T")


class _DetailRun:
    """Per-run state of the optional detail fetch (SPEC 50, F50-03)."""

    def __init__(self, request: CollectionRequest) -> None:
        self.enabled = request.fetch_detail and bool(request.target_role_families)
        self.approved = request.detail_approval_valid
        self.approval_skip_reason = (
            request.detail_approval_skip_reason
            if self.enabled
            else "disabled"
            if not request.fetch_detail
            else "no_target_roles"
        )
        self.cap = request.detail_max_requests
        self.host_remaining = request.host_requests_remaining
        #: Set by a 429 on a detail request: no further detail requests this run.
        self.stopped = False

    def has_room(self, http_requests: int) -> bool:
        """Whether another real detail transport fits the per-run cap.

        Shared host capacity is checked atomically immediately before each transport.
        """
        return self.cap > http_requests


class WorkdayCollector:
    """Reads public postings from a Workday tenant's career site (CXS backend)."""

    source_type = "workday"
    capabilities = CollectorCapabilities(
        company_jobs=True,
        pagination=True,
        incremental_cursor=True,
        etag=True,
        last_modified=True,
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
            summary="Workday public career-site collector is configured",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        tenant, site = self.validate_tenant_identifier(request.company_reference)
        pod = self.validate_pod(request.api_region)
        emitted = 0
        if self._client is not None:
            async for item in self._discover_with_client(
                self._client, tenant, site, pod, request, emitted
            ):
                emitted += 1
                yield item
            return
        async with self._client_factory() as client:
            async for item in self._discover_with_client(
                client, tenant, site, pod, request, emitted
            ):
                yield item

    async def _discover_with_client(
        self,
        client: httpx.AsyncClient,
        tenant: str,
        site: str,
        pod: str,
        request: CollectionRequest,
        emitted: int,
    ) -> AsyncIterator[CollectedItem]:
        seen_pages: set[tuple[str, ...]] = set()
        total_fetched = 0
        board_total: int | None = None
        detail = _DetailRun(request)
        # A resumed run (F20-39 `resume_of_run_id`) supplies an explicit cursor: the offset
        # to pick up from, never derived automatically. A fresh run has no cursor and
        # starts at 0, same as before this card.
        offset = self._parse_cursor(request.cursor)
        while request.max_items is None or emitted < request.max_items:
            remaining = (
                None if request.max_items is None else request.max_items - emitted
            )
            limit = min(_PAGE_SIZE, remaining) if remaining is not None else _PAGE_SIZE
            if board_total is not None and offset >= board_total:
                # Workday serves at most `total` (capped at 2000) results; past that it
                # wraps back to the first page instead of ending, so the announced total
                # is the end of the board, not a page repeat.
                request.telemetry.record_items_announced(total_fetched)
                return
            try:
                postings, total = await self._fetch_page(
                    client, tenant, site, pod, offset, limit, request
                )
            except NotModifiedResponse:
                return
            if board_total is None and total is not None and offset == 0:
                board_total = total
            page_signature = tuple(str(posting.get("externalPath")) for posting in postings)
            if postings and page_signature in seen_pages:
                raise AcquisitionError(
                    AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                    "Workday pagination repeated a page without making progress",
                )
            seen_pages.add(page_signature)
            total_fetched += len(postings)
            for index, posting in enumerate(postings):
                if not self._has_title(posting):
                    # Card F20-75: no title, no opportunity. Skipped, not invalid.
                    request.telemetry.record_skipped_item()
                    continue
                try:
                    item = self._item(
                        posting,
                        tenant=tenant,
                        site=site,
                        pod=pod,
                        company_name=request.company_name,
                        # The offset a resume should pick up from if this run is
                        # interrupted right after this item (F20-39 "retomada").
                        cursor=str(offset + index + 1),
                    )
                except AcquisitionError as error:
                    if error.code is not AcquisitionErrorCode.PARSER_SCHEMA_CHANGED:
                        raise
                    request.telemetry.record_invalid_item(error.summary)
                    continue
                if detail.enabled and self._is_target(item, request):
                    item = await self._with_detail(
                        client, item, tenant, site, pod, request, detail
                    )
                yield item
                emitted += 1
                if request.max_items is not None and emitted >= request.max_items:
                    return
            if len(postings) < limit:
                # Workday never states a trustworthy total across every tenant, so, like
                # Lever, a page shorter than what was asked for is itself the end: this
                # exhaustive read is the announced count, not a guess from an empty page.
                request.telemetry.record_items_announced(total_fetched)
                return
            offset += len(postings)

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            offset = int(cursor)
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Workday cursor must be a non-negative integer offset",
                field="cursor",
            ) from error
        if offset < 0:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Workday cursor must be a non-negative integer offset",
                field="cursor",
            )
        return offset

    @staticmethod
    def validate_tenant_identifier(company_reference: str | None) -> tuple[str, str]:
        if company_reference is None:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Workday company_reference must be '<tenant>/<site>'",
            )
        match = _TENANT_SITE.fullmatch(company_reference)
        if match is None:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Workday company_reference must be '<tenant>/<site>'",
            )
        return match.group(1), match.group(2)

    @staticmethod
    def validate_pod(api_region: str | None) -> str:
        if api_region is None or not _POD.fullmatch(api_region.strip().casefold()):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Workday api_region must be a pod like 'wd1' or 'wd5'",
            )
        return api_region.strip().casefold()

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        tenant: str,
        site: str,
        pod: str,
        offset: int,
        limit: int,
        request: CollectionRequest,
    ) -> tuple[list[Mapping[str, Any]], int | None]:
        url = f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"

        async def send() -> httpx.Response:
            # Validators only ever describe a fresh, full read from offset 0; a
            # resumed run's cursor picks up mid-board, a different scope a 304 for
            # offset 0 could never speak for.
            headers = (
                conditional_request_headers(request)
                if offset == 0 and request.cursor is None
                else {}
            )
            return await client.post(
                url,
                json={"limit": limit, "offset": offset, "searchText": ""},
                headers=headers or None,
            )

        def conditional(response: httpx.Response) -> None:
            if response.status_code == 304:
                record_conditional_response(request, response)
                raise NotModifiedResponse()
            record_conditional_response(request, response)

        return await self._request(
            request,
            send,
            lambda response: (self._postings(response), self._total(response)),
            inspect=conditional,
            detail=False,
        )

    async def _request(
        self,
        request: CollectionRequest,
        send: Callable[[], Awaitable[httpx.Response]],
        parse: Callable[[httpx.Response], _T],
        *,
        inspect: Callable[[httpx.Response], None] | None = None,
        detail: bool = False,
    ) -> _T:
        """One HTTP exchange under the request's network policy, shared by listing and detail:
        minimum interval, retries with Retry-After, and the telemetry the host budget reads."""
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
                if detail and request.telemetry.detail_requests >= request.detail_max_requests:
                    raise AcquisitionError(
                        AcquisitionErrorCode.SOURCE_RATE_LIMITED,
                        "per-run detail request cap exhausted",
                        retryable=False,
                    )
                if request.reserve_http_request is not None:
                    denied = request.reserve_http_request(detail)
                    if denied is not None:
                        raise AcquisitionError(
                            AcquisitionErrorCode.SOURCE_RATE_LIMITED,
                            f"Workday host request blocked by {denied}",
                            retryable=False,
                        )
                elif (
                    request.host_requests_remaining is not None
                    and request.telemetry.http_requests >= request.host_requests_remaining
                ):
                    raise AcquisitionError(
                        AcquisitionErrorCode.SOURCE_RATE_LIMITED,
                        "Workday host quota exhausted",
                    )
                request.telemetry.record_http_attempt(retry=attempt > 0)
                if detail:
                    request.telemetry.detail_requests += 1
                response = await send()
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                    retry_after = parse_retry_after_seconds(response.headers.get("Retry-After"))
                    wait = retry_after if retry_after is not None else max_retry_delay
                    if request.persist_cooldown is not None:
                        request.persist_cooldown(datetime.now(UTC) + timedelta(seconds=wait))
                if inspect is not None:
                    inspect(response)
                if detail and response.status_code == 304:
                    return parse(response)
                error = self._response_error(response)
                if error is None:
                    return parse(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Workday request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Workday",
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
    def _is_target(item: CollectedItem, request: CollectionRequest) -> bool:
        """Same classification `AcquisitionService` applies at collection time (F50-04)."""
        try:
            family = classify_role_family(
                title=item.title, departments=departments_from_metadata(item.metadata)
            ).role_family
        except Exception:  # noqa: BLE001 - an unclassifiable posting gets no detail request
            return False
        return family.value in request.target_role_families

    async def _with_detail(
        self,
        client: httpx.AsyncClient,
        item: CollectedItem,
        tenant: str,
        site: str,
        pod: str,
        request: CollectionRequest,
        detail: _DetailRun,
    ) -> CollectedItem:
        """The item with its description, or unchanged when the detail cannot be had.

        Never raises: a posting is never dropped and a run never fails over its detail.
        Identity (external id, URL) is untouched, so turning detail on creates no duplicate.
        """
        telemetry = request.telemetry
        if not detail.enabled:
            telemetry.record_detail(skipped=True, reason=detail.approval_skip_reason)
            if request.persist_detail_counters is not None:
                request.persist_detail_counters(telemetry)
            return item
        if not detail.approved:
            telemetry.record_detail(skipped=True, reason=detail.approval_skip_reason)
            if request.persist_detail_counters is not None:
                request.persist_detail_counters(telemetry)
            return item
        if detail.stopped or not detail.has_room(telemetry.detail_requests):
            reason = "cooldown" if detail.stopped else "cap"
            telemetry.record_detail(skipped=True, reason=reason)
            if request.persist_detail_counters is not None:
                request.persist_detail_counters(telemetry)
            return item
        url = (
            f"https://{tenant}.{pod}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
            f"{item.external_id}"
        )
        requests_before = telemetry.detail_requests
        try:
            description = await self._request(
                request, lambda: client.get(url), self._detail_description, detail=True
            )
        except AcquisitionError as error:
            denied = (
                "cap"
                if "detail request cap" in error.summary
                else "quota"
                if "quota" in error.summary
                else "cooldown"
                if "cooldown" in error.summary
                else None
            )
            if denied:
                if denied == "cap" and telemetry.detail_requests > requests_before:
                    telemetry.detail_failures += 1
                telemetry.record_detail(skipped=True, reason=denied)
            else:
                telemetry.detail_failures += 1
            if error.code is AcquisitionErrorCode.SOURCE_RATE_LIMITED:
                # The 429 is already counted as a rate-limit event; stop asking.
                detail.stopped = True
            if request.persist_detail_counters is not None:
                request.persist_detail_counters(telemetry)
            return item
        if request.persist_detail_counters is not None:
            request.persist_detail_counters(telemetry)
        return item if description is None else replace(item, description=description)

    @staticmethod
    def _detail_description(response: httpx.Response) -> str | None:
        if response.status_code == 304:
            return None
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Workday returned invalid JSON"
            ) from error
        info = payload.get("jobPostingInfo") if isinstance(payload, dict) else None
        if not isinstance(info, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday detail is missing jobPostingInfo",
            )
        description = info.get("jobDescription")
        if description is None:
            return None
        if not isinstance(description, str):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday detail jobDescription must be a string",
            )
        return description.strip() or None

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
                f"Workday returned HTTP {status}",
                retryable=False,
                retry_after_seconds=(
                    parse_retry_after_seconds(response.headers.get("Retry-After"))
                    if status == 429
                    else None
                ),
            )
        if 500 <= status < 600:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                f"Workday returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Workday returned HTTP {status}",
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
    def _total(response: httpx.Response) -> int | None:
        # Workday only states `total` on the offset-0 page (later pages carry 0) and caps
        # it at 2000 on huge boards, so it is read leniently and only trusted when > 0.
        payload = response.json()
        total = payload.get("total") if isinstance(payload, dict) else None
        if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
            return None
        return total

    @staticmethod
    def _postings(response: httpx.Response) -> list[Mapping[str, Any]]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "Workday returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday response must be an object",
            )
        postings = payload.get("jobPostings")
        if not isinstance(postings, list) or any(
            not isinstance(posting, dict) for posting in postings
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday response is missing a jobPostings list",
            )
        return postings

    @staticmethod
    def _has_title(posting: Mapping[str, Any]) -> bool:
        title = posting.get("title")
        return isinstance(title, str) and bool(title.strip())

    @staticmethod
    def _item(
        posting: Mapping[str, Any],
        *,
        tenant: str,
        site: str,
        pod: str,
        company_name: str | None,
        cursor: str | None = None,
    ) -> CollectedItem:
        title = posting.get("title")
        external_path = posting.get("externalPath")
        if not isinstance(title, str) or not title.strip():
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday posting is missing a title",
            )
        if not isinstance(external_path, str) or not external_path.startswith("/"):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday posting is missing a valid externalPath",
            )
        bullet_fields = posting.get("bulletFields")
        if bullet_fields is not None and not isinstance(bullet_fields, list):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Workday posting bulletFields must be a list",
            )
        requisition_id = (
            bullet_fields[0]
            if bullet_fields and isinstance(bullet_fields[0], str)
            else None
        )
        return CollectedItem(
            source_type=WorkdayCollector.source_type,
            external_id=external_path,
            url=f"https://{tenant}.{pod}.myworkdayjobs.com/{site}{external_path}",
            title=title,
            company_name=company_name,
            location_text=WorkdayCollector._string(posting.get("locationsText")),
            # The listing endpoint never carries the full description; only the per-job
            # detail does, fetched on top of this item when enabled (see module docstring).
            description=None,
            published_at=WorkdayCollector._parse_posted_on(posting.get("postedOn")),
            cursor=cursor,
            raw_payload=posting,
            metadata={
                "posted_on": posting.get("postedOn"),
                "requisition_id": requisition_id,
                "parser_version": _PARSER_VERSION,
            },
        )

    #: Card F20-61. Workday's public CxS listing endpoint never carries an exact
    #: posting timestamp — the only date-shaped signal it exposes is this relative
    #: age string ("Posted Today", "Posted 3 Days Ago", "Posted 30+ Days Ago"). It is
    #: real source data, not a fabricated date: `"Posted N Days Ago"` at least means
    #: the posting is `N` days old as of the request, so `now - N days` is read as
    #: that lower bound, never as an exact publication instant. Anything outside this
    #: known vocabulary (a future Workday UI string change) yields `None` rather than
    #: a guess.
    _POSTED_ON_PATTERN = re.compile(
        r"^posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)$", re.IGNORECASE
    )

    @staticmethod
    def _parse_posted_on(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        match = WorkdayCollector._POSTED_ON_PATTERN.match(value.strip())
        if match is None:
            return None
        now = datetime.now(UTC)
        head = match.group(1).lower()
        if head == "today":
            return now
        if head == "yesterday":
            return now - timedelta(days=1)
        days = match.group(2)
        return now - timedelta(days=int(days)) if days is not None else None

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) else None
