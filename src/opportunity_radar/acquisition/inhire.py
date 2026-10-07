"""inHire public career-page collector.

Every inHire tenant (`<tenant>.inhire.app`) has a public, unauthenticated read route that the
tenant's own career page and embed script call: `GET https://api.inhire.app/job-posts/public/
pages` with the tenant in the `X-Tenant` header lists every published job, and `GET
.../pages/<jobId>` carries the description, contract type and publication date the list lacks.

Terms review: `docs/pesquisas/termos-inhire.md` ("viável com ressalvas"). Its conditions are
what this module implements: product User-Agent, serial requests at a low rate (the default
policy is set by `AcquisitionService`), one detail request per job that is new or changed (never
for the whole board on every run), a stop on 403/429 for the whole run, "Tenant not found" as a
configuration error, no `/forms/*` or any route besides these two, and only the fields the
review lists as usable. `settings.*`, `activeJobBoards`, `privacyPolicyUrl`, `about`,
`background`, `logo`, `banner*` and form data are never stored, not even in `raw_payload`.

"New or changed": the list has no `updatedAt`, so a job is changed when one of the list fields
differs from the stored raw payload the service hands over in `CollectionRequest.known_items`.
A known job that did not change is re-emitted from its stored payload: same content, same
hashes, so the service records a presence observation and no new version appears. A known job
whose detail cannot be fetched (cap, budget, failure, stop) is re-emitted the same way, stale
but never blanked.

An edit that touches only the description changes no list field. So each known job is also
re-read once every `_REFRESH_DAYS` days, on the day its id falls on, after every new or
changed job got its detail and only with the room that is left. Only the source's first run
of that day re-reads: a later run the same day (`CollectionRequest.previous_attempt_at` is
today) would fetch the same detail again. A re-read that finds the same content yields the
same payload and hashes, so it creates no version.

E-mail addresses and phone numbers in the description are masked before anything is stored
(the review's personal-data condition); the public page keeps the original text.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime
from typing import Any, TypeVar
from uuid import UUID

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

# The tenant goes into a request header and into the public page URL: one DNS label of
# lowercase letters, digits and hyphens (the shape of every `<tenant>.inhire.app` seen:
# gx2, contaazul, atlastechnol, magalu). Anything else (case, dots, slashes, colons,
# whitespace, CR/LF) is refused, so it cannot alter the header or the URL.
_TENANT = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_PAGES_URL = "https://api.inhire.app/job-posts/public/pages"
_PARSER_VERSION = "inhire-public-pages-v1"
_PUBLISHED_STATUS = "published"
#: Terms review: at most one request per second unless the source's policy says otherwise.
_DEFAULT_MINIMUM_INTERVAL = 1.0
#: Fields that identify a list entry and decide whether a stored job changed.
_LISTING_FIELDS = ("jobId", "displayName", "status", "workplaceType", "location")
_DETAIL_FIELDS = ("description", "contractType", "publishedAt", "lastPublishedAt")
#: A 401/403/429 stops every further request of the run, list or detail.
_STOP_CODES = frozenset(
    {
        AcquisitionErrorCode.SOURCE_UNAUTHORIZED,
        AcquisitionErrorCode.SOURCE_FORBIDDEN,
        AcquisitionErrorCode.SOURCE_RATE_LIMITED,
    }
)
#: A known, unchanged job has its detail re-read once in this many days.
_REFRESH_DAYS = 7
#: Any last path segment resolves on the public page, but the page stays blank without one
#: (checked in a browser on 2026-10-05). A fixed one keeps the URL independent of the title.
_URL_SLUG = "vaga"
# Contact data in the free text. The phone shapes need a country code, an area code in
# parentheses or a mobile ninth digit, so years, ranges and amounts are left alone.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")
_PHONE = re.compile(
    r"\+55\s?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}"
    r"|\(\d{2}\)\s?9?\d{4}[-\s]?\d{4}"
    r"|\b\d{2}\s9\d{4}-\d{4}\b"
)
# What the normalizer's contract patterns can read; anything else passes through as text.
_CONTRACT_EVIDENCE = {"clt": "full-time", "pj": "contract"}
_T = TypeVar("_T")


def _mask_contacts(text: str) -> str:
    return _PHONE.sub("[telefone]", _EMAIL.sub("[email]", text))


class _DetailRun:
    """Per-run state of the detail fetch: cap, host budget and the stop signal."""

    def __init__(self, request: CollectionRequest) -> None:
        self.enabled = request.fetch_detail
        self.cap = request.detail_max_requests
        self.host_remaining = request.host_requests_remaining
        self.requested = 0
        #: The 401/403/429 that stopped the run's requests; re-raised once the items are out.
        self.stopped: AcquisitionError | None = None

    def has_room(self, http_requests: int) -> bool:
        if self.requested >= self.cap:
            return False
        return self.host_remaining is None or http_requests < self.host_remaining


class InhireCollector:
    """Reads published jobs from an inHire tenant's public career-page API."""

    source_type = "inhire"
    capabilities = CollectorCapabilities(company_jobs=True, known_items=True)

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
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
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
        self._today = today

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        return HealthResult(
            healthy=True, summary="inHire public career-page collector is configured"
        )

    @staticmethod
    def validate_tenant_identifier(value: str | None) -> str:
        if value is None or _TENANT.fullmatch(value) is None:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "inHire tenant_identifier must be the lowercase letters, digits and"
                " hyphens of <tenant>.inhire.app (no dots, slashes or whitespace)",
            )
        return value

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        tenant = self.validate_tenant_identifier(request.company_reference)
        if self._client is not None:
            async for item in self._discover_with_client(self._client, tenant, request):
                yield item
            return
        async with self._client_factory() as client:
            async for item in self._discover_with_client(client, tenant, request):
                yield item

    async def _discover_with_client(
        self, client: httpx.AsyncClient, tenant: str, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        tenant_name, jobs = await self._request(
            request,
            lambda: client.get(_PAGES_URL, headers={"X-Tenant": tenant}),
            self._listing_response,
            listing=True,
        )
        # One list call is the whole board (no pagination observed), so its size is the
        # announced total; an empty list is a complete, empty board.
        request.telemetry.record_items_announced(len(jobs))
        company_name = request.company_name or tenant_name
        known_items = request.known_items or {}
        detail = _DetailRun(request)
        today = self._today()
        refresh_slot = today.toordinal() % _REFRESH_DAYS
        previous = request.previous_attempt_at
        # The day's re-reads were already tried by an earlier run of this source today.
        refresh_done = previous is not None and previous.astimezone(UTC).date() == today
        # Jobs due for a re-read wait until every new or changed job had its turn.
        deferred: list[tuple[dict[str, Any], Mapping[str, Any]]] = []
        emitted = 0
        for job in jobs:
            if job.get("status") != _PUBLISHED_STATUS:
                # Unknown or unpublished status: counted, never guessed to be published.
                request.telemetry.record_skipped_item()
                continue
            title = job.get("displayName")
            if not isinstance(title, str) or not title.strip():
                request.telemetry.record_skipped_item()
                continue
            try:
                listing = self._listing(job)
                known = known_items.get(listing["jobId"])
                if (
                    known is not None
                    and detail.enabled
                    and not refresh_done
                    and self._unchanged(known, listing)
                    and UUID(listing["jobId"]).int % _REFRESH_DAYS == refresh_slot
                ):
                    deferred.append((listing, known))
                    continue
                payload = await self._payload(client, tenant, listing, known, request, detail)
                item = self._item(payload, tenant=tenant, company_name=company_name)
            except AcquisitionError as error:
                if error.code is not AcquisitionErrorCode.PARSER_SCHEMA_CHANGED:
                    raise
                request.telemetry.record_invalid_item(error.summary)
                continue
            yield item
            emitted += 1
            if request.max_items is not None and emitted >= request.max_items:
                break
        for listing, known in deferred:
            if request.max_items is not None and emitted >= request.max_items:
                break
            payload = await self._payload(
                client, tenant, listing, known, request, detail, refresh=True
            )
            yield self._item(payload, tenant=tenant, company_name=company_name)
            emitted += 1
        if detail.stopped is not None:
            raise detail.stopped

    @staticmethod
    def _unchanged(known: Mapping[str, Any], listing: Mapping[str, Any]) -> bool:
        """A stored job with its detail whose list fields are what the list shows now."""
        return "description" in known and all(
            known.get(key) == listing[key] for key in _LISTING_FIELDS
        )

    async def _payload(
        self,
        client: httpx.AsyncClient,
        tenant: str,
        listing: dict[str, Any],
        known: Mapping[str, Any] | None,
        request: CollectionRequest,
        detail: _DetailRun,
        *,
        refresh: bool = False,
    ) -> dict[str, Any]:
        """The reduced raw payload of one job: stored, fresh from the detail, or listing only.

        `refresh` re-reads the detail of a stored job whose list fields did not change."""
        fallback = listing
        if known is not None and "description" in known:
            if not refresh and self._unchanged(known, listing):
                return dict(known)
            # A stored job that changed but cannot be refreshed stays as stored: never blanked.
            fallback = dict(known)
        if not detail.enabled:
            return fallback
        telemetry = request.telemetry
        if detail.stopped is not None or not detail.has_room(telemetry.http_requests):
            telemetry.record_detail(skipped=True)
            return fallback
        job_id = listing["jobId"]
        detail.requested += 1
        try:
            fields = await self._request(
                request,
                lambda: client.get(f"{_PAGES_URL}/{job_id}", headers={"X-Tenant": tenant}),
                lambda response: self._detail_fields(response, job_id),
            )
        except AcquisitionError as error:
            telemetry.record_detail(failed=True)
            if error.code in _STOP_CODES:
                detail.stopped = error
            return fallback
        telemetry.record_detail()
        return {**listing, **fields}

    async def _request(
        self,
        request: CollectionRequest,
        send: Callable[[], Awaitable[httpx.Response]],
        parse: Callable[[httpx.Response], _T],
        *,
        listing: bool = False,
    ) -> _T:
        """One HTTP exchange under the request's network policy, shared by list and detail:
        minimum interval, retries for 5xx and timeouts, and the telemetry the host budget
        reads. A 401/403/429 is raised at once and never retried."""
        policy = request.network_policy
        max_retries = policy.max_retries if policy is not None else self._max_retries
        retry_delay = (
            policy.retry_delay_seconds if policy is not None else self._retry_after_seconds
        )
        max_retry_delay = policy.max_retry_delay_seconds if policy is not None else 30.0
        minimum_interval = (
            policy.minimum_interval_seconds if policy is not None else _DEFAULT_MINIMUM_INTERVAL
        )
        if request.telemetry.last_http_attempt_at is not None and minimum_interval:
            elapsed = (
                datetime.now(UTC) - request.telemetry.last_http_attempt_at
            ).total_seconds()
            if minimum_interval > elapsed:
                await self._sleeper(minimum_interval - elapsed)
        for attempt in range(max_retries + 1):
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await send()
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response, listing=listing)
                if error is None:
                    return parse(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "inHire request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to inHire",
                    retryable=True,
                )
            assert error is not None
            if error.code in _STOP_CODES or not error.retryable or attempt == max_retries:
                raise error
            await self._sleeper(min(max(minimum_interval, retry_delay), max_retry_delay))
        raise AssertionError("unreachable")

    @staticmethod
    def _response_error(response: httpx.Response, *, listing: bool) -> AcquisitionError | None:
        status = response.status_code
        if 200 <= status < 300:
            return None
        if status == 404 and listing:
            # The only route that names the tenant: a 404 here is a wrong tenant, not an
            # empty board (an empty board is a 200 with an empty `jobsPage`).
            return AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "inHire tenant not found",
                field="configuration.tenant_identifier",
            )
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
                f"inHire returned HTTP {status}",
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
                f"inHire returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR, f"inHire returned HTTP {status}"
        )

    @staticmethod
    def _json(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "inHire returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "inHire response must be an object"
            )
        return payload

    @staticmethod
    def _listing_response(response: httpx.Response) -> tuple[str | None, list[Mapping[str, Any]]]:
        payload = InhireCollector._json(response)
        jobs = payload.get("jobsPage")
        if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "inHire response is missing a jobsPage list",
            )
        tenant_name = payload.get("tenantName")
        return (tenant_name.strip() or None) if isinstance(tenant_name, str) else None, jobs

    @staticmethod
    def _listing(job: Mapping[str, Any]) -> dict[str, Any]:
        """The list fields kept in the raw payload; the id must be a UUID (it joins a URL)."""
        job_id = job.get("jobId")
        try:
            if not isinstance(job_id, str) or str(UUID(job_id)) != job_id.lower():
                raise ValueError
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "inHire job has an invalid jobId"
            ) from error
        return {key: job[key] if isinstance(job.get(key), str) else None for key in _LISTING_FIELDS}

    @staticmethod
    def _detail_fields(response: httpx.Response, job_id: str) -> dict[str, Any]:
        """Only the usable detail fields; everything else in the response is dropped."""
        payload = InhireCollector._json(response)
        if payload.get("jobId") != job_id:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "inHire detail is for another job"
            )
        description = payload.get("description")
        contract = payload.get("contractType")
        if isinstance(contract, str):
            contract = [contract]
        if not (description is None or isinstance(description, str)) or not (
            contract is None
            or (isinstance(contract, list) and all(isinstance(entry, str) for entry in contract))
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "inHire detail description or contractType has an unexpected type",
            )
        fields: dict[str, Any] = {
            "description": _mask_contacts((description or "").strip()) or None,
            "contractType": [entry.strip() for entry in contract or [] if entry.strip()],
        }
        for key in ("publishedAt", "lastPublishedAt"):
            value = payload.get(key)
            InhireCollector._parse_datetime(value)
            fields[key] = value
        return fields

    @staticmethod
    def _item(
        payload: Mapping[str, Any], *, tenant: str, company_name: str | None
    ) -> CollectedItem:
        job_id = payload["jobId"]
        location = payload.get("location")
        contract_types = payload.get("contractType")
        return CollectedItem(
            source_type=InhireCollector.source_type,
            external_id=job_id,
            # Identity never depends on the title: the id alone resolves on the public page.
            url=f"https://{tenant}.inhire.app/vagas/{job_id}/{_URL_SLUG}",
            title=payload["displayName"].strip(),
            company_name=company_name,
            location_text=location.strip() or None if isinstance(location, str) else None,
            description=payload.get("description"),
            published_at=InhireCollector._parse_datetime(
                payload.get("publishedAt") or payload.get("lastPublishedAt")
            ),
            raw_payload=payload,
            metadata={
                # `Remote` / `Hybrid` / `On-site`: read as work-mode evidence as is.
                "workplace_type": payload.get("workplaceType"),
                # CLT / PJ translated for the contract patterns; unknown values pass as text.
                "contract_type": [
                    _CONTRACT_EVIDENCE.get(entry.casefold(), entry)
                    for entry in contract_types or []
                ],
                "parser_version": _PARSER_VERSION,
            },
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            if not isinstance(value, str):
                raise ValueError
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "inHire date is invalid"
            ) from error
