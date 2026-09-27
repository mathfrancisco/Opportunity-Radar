"""Factorial public careers-page collector.

Every Factorial-hosted career site is a server-rendered HTML page at
`https://<company-slug>.factorialhr.com/` (`docs/pesquisas/termos-factorial.md`, the terms
review this card requires before any code). Unlike Ashby, Lever, Greenhouse or Teamtailor,
Factorial has **no public JSON endpoint** for its jobs board: the only documented Factorial
API (`api.factorialhr.com`) is the authenticated HR/ATS admin API, which needs a per-company
Bearer token and is out of scope ("Fora de escopo: fonte que exige login").

The career page instead embeds every open job in the initial HTML response, one
`<li class="job-offer-item">` per job, with the structured facts this collector needs in
`data-*` attributes (`data-job-postings-url`, `data-team-id`, `data-location-id`,
`data-is-remote`, `data-contract-type`) plus three ordered `<div>` labels (title, team name,
location name) inside each `<li>`. The client-side "All teams"/"All contract types" filters
seen on the page are CSS/JS over this same HTML, not a separate API call — there is no
pagination, no `next_url`, and no page parameter, confirmed against three real boards of very
different sizes (2, ~70 and one mid-sized board). `capabilities.pagination` is therefore
`False`, and one successful response is the whole board.

This collector reads only the documented `data-*` attributes and the three ordered label
`<div>`s per job — never raw prose from the page — using the standard-library
`html.parser.HTMLParser`, so no new HTML-parsing dependency was needed. The listing page
exposes no structured description and no seniority field, so `description` and any
seniority mapping (F20-02) are left absent rather than guessed; the job's team name/id is
the only structured grouping available and is carried in `metadata` for a downstream
department mapping (F20-03) to use, the same way Teamtailor's collector defers to
downstream mapping instead of guessing.
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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
from opportunity_radar.acquisition.http_conditional import (
    NotModifiedResponse,
    conditional_request_headers,
    record_conditional_response,
)

# A Factorial company slug: the subdomain segment before `.factorialhr.com`
# (`agentero`, `currency-solutions`, ...). No public evidence of Factorial supporting a
# custom domain the way Teamtailor does, so this stays a bare slug under the fixed host,
# matching Ashby/Lever/Greenhouse rather than Teamtailor's whole-hostname identifier.
_SLUG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
# The marker that a response is a Factorial jobs-listing page at all (present on every
# board tested, regardless of job count): the Stimulus controller behind the team/contract
# filters. Its absence means the page shape is not what this collector was written against
# (wrong URL, a redirect to a login wall, a template Factorial has changed) -- never
# silently read as "zero jobs".
_JOB_ITEM_CLASS = "job-offer-item"
_PARSER_VERSION = "factorial-careers-page-v1"
_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


@dataclass(slots=True)
class _ParsedJob:
    attrs: dict[str, str | None]
    texts: list[str] = field(default_factory=list)


class _FactorialJobsParser(HTMLParser):
    """Pulls each `<li class="job-offer-item">` and its `data-*` facts out of the page.

    Reads structure only: the element's own attributes and the plain text of its child
    `<div>`s, in document order. It never infers meaning from CSS classes beyond finding
    the job items themselves, and it does not touch anything outside a job `<li>` (the
    team/contract `<select>` filters that precede the list are siblings, never descendants,
    of a job item, so their option text never leaks into a job's texts).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.saw_listing_marker = False
        self.jobs: list[_ParsedJob] = []
        self._in_job = False
        self._job_depth = 0
        self._current: _ParsedJob | None = None
        self._label_depth: int | None = None
        self._label_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if attrs_dict.get("data-controller") == "job-filters":
            self.saw_listing_marker = True
        if not self._in_job:
            classes = (attrs_dict.get("class") or "").split()
            if tag == "li" and _JOB_ITEM_CLASS in classes:
                self._in_job = True
                self._job_depth = 1
                self._current = _ParsedJob(attrs=attrs_dict)
            return
        # HTMLParser does not emit an end tag for ordinary HTML void elements such as
        # ``<br>``. They are descendants of a posting but do not extend its scope.
        if tag == "div" and self._label_depth is None:
            classes = (attrs_dict.get("class") or "").split()
            if "factorial__headingFontFamily" in classes or "text-gray-350" in classes:
                self._label_depth = self._job_depth + 1
                self._label_parts = []
        if tag not in _VOID_ELEMENTS:
            self._job_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if not self._in_job:
            return
        if tag in _VOID_ELEMENTS:
            return
        if tag == "div" and self._label_depth == self._job_depth:
            assert self._current is not None
            text = " ".join(self._label_parts)
            # Append unconditionally, even when empty: a job with no team assigned
            # (`data-team-id=""`) still renders this label `<div>`, just with no text
            # inside (confirmed live against careers.factorialhr.com, where 9 of 140 real
            # postings have this exact shape). Dropping the empty label would shift the
            # location text into the team slot and make a real job look schema-changed.
            self._current.texts.append(text)
            self._label_depth = None
            self._label_parts = []
        self._job_depth -= 1
        if self._job_depth == 0 and tag == "li":
            assert self._current is not None
            self.jobs.append(self._current)
            self._in_job = False
            self._current = None

    def handle_data(self, data: str) -> None:
        if not self._in_job or self._current is None:
            return
        text = data.strip()
        if text and self._label_depth is not None:
            self._label_parts.append(text)


class FactorialCollector:
    """Reads public postings from a Factorial-hosted career page."""

    source_type = "factorial"
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

    async def healthcheck(self, context: HealthcheckContext | None = None) -> HealthResult:
        del context
        return HealthResult(
            healthy=True,
            summary="Factorial public careers-page collector is configured",
        )

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        slug = self.validate_company_identifier(request.company_reference)
        try:
            jobs = await self._fetch_jobs(slug, request)
        except NotModifiedResponse:
            return
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
        if request.max_items is None:
            # The page is unpaginated: a single successful fetch is the whole board, same
            # rule as Teamtailor's unpaginated feed.
            request.telemetry.record_items_announced(len(jobs))

    async def _fetch_jobs(self, slug: str, request: CollectionRequest) -> list[_ParsedJob]:
        if self._client is not None:
            return await self._fetch_jobs_with_client(self._client, slug, request)
        async with self._client_factory() as client:
            return await self._fetch_jobs_with_client(client, slug, request)

    async def _fetch_jobs_with_client(
        self, client: httpx.AsyncClient, slug: str, request: CollectionRequest
    ) -> list[_ParsedJob]:
        url = f"https://{quote(slug)}.factorialhr.com/"
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
                    return self._jobs(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Factorial request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Factorial",
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
        if value is None or not _SLUG.fullmatch(value):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Factorial company_identifier must be a bare career-site slug"
                " (no scheme, dots, path or port)",
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
                f"Factorial returned HTTP {status}",
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
                f"Factorial returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Factorial returned HTTP {status}",
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
    def _jobs(response: httpx.Response) -> list[_ParsedJob]:
        body = response.text
        parser = _FactorialJobsParser()
        parser.feed(body)
        if not parser.saw_listing_marker:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Factorial response is not a jobs-listing page",
            )
        if parser._in_job:
            # A truncated listing cannot prove an empty or complete inventory.
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Factorial response ended inside a job listing",
            )
        return parser.jobs

    @staticmethod
    def _item(job: _ParsedJob, *, company_name: str | None) -> CollectedItem:
        job_url = job.attrs.get("data-job-postings-url")
        if not isinstance(job_url, str) or not FactorialCollector._is_http_url(job_url):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Factorial job is missing a valid data-job-postings-url",
            )
        external_id = urlparse(job_url).path.rsplit("/", 1)[-1]
        if not external_id:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Factorial job url has no identifiable slug",
            )
        if len(job.texts) < 3:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Factorial job is missing title, team or location text",
            )
        title, team_name, location_name = job.texts[0], job.texts[1], job.texts[2]
        is_remote = job.attrs.get("data-is-remote")
        return CollectedItem(
            source_type=FactorialCollector.source_type,
            external_id=external_id,
            url=job_url,
            title=title,
            company_name=company_name,
            location_text=location_name or None,
            raw_payload={"attrs": dict(job.attrs), "texts": list(job.texts)},
            metadata={
                "team_name": team_name or None,
                "team_id": job.attrs.get("data-team-id"),
                "location_id": job.attrs.get("data-location-id"),
                "is_remote": is_remote == "true" if is_remote is not None else None,
                "contract_type": job.attrs.get("data-contract-type"),
                "parser_version": _PARSER_VERSION,
            },
        )

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
