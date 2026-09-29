"""Public schema.org `JobPosting` collector (F20-37).

A company with a confirmed careers page and no supported ATS still often marks up its own
listing with `JobPosting` JSON-LD, the same structured data search engines read. This
collector reads exactly that markup — object, list, or `@graph` — and nothing else: no
headless browser, no guessed CSS selector, no residency/eligibility inferred from a
"remote" label. Absence of a field is `UNKNOWN` (`None`), never a fabricated value, and a
page with no compatible markup (challenge, soft-404, empty shell, incompatible schema) is
always a failure (`AcquisitionErrorCode.PARSER_SCHEMA_CHANGED`), never an empty success.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
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
    parse_retry_after_seconds,
)

_PARSER_VERSION = "job-posting-jsonld-v1"
_JSONLD_SCRIPT = re.compile(
    r"""<script[^>]*type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script>""",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class JobPostingFields:
    """What the JSON-LD separates, with no inference: absence is `UNKNOWN`, not empty."""

    identifier: str | None
    title: str | None
    description_html: str | None
    hiring_organization_name: str | None
    apply_url: str | None
    date_posted: datetime | None
    valid_through: datetime | None
    employment_type: str | None
    job_location_text: str | None
    job_location_type: str | None
    applicant_location_requirements: tuple[str, ...]
    base_salary_min: Decimal | None
    base_salary_max: Decimal | None
    base_salary_currency: str | None
    base_salary_unit: str | None
    raw_node: dict[str, Any]


def _is_job_posting(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    node_type = node.get("@type")
    if isinstance(node_type, str):
        return node_type == "JobPosting"
    if isinstance(node_type, list):
        return "JobPosting" in node_type
    return False


def _iter_job_posting_nodes(parsed: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(parsed, list):
        for item in parsed:
            nodes.extend(_iter_job_posting_nodes(item))
    elif isinstance(parsed, dict):
        if _is_job_posting(parsed):
            nodes.append(parsed)
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                nodes.extend(_iter_job_posting_nodes(item))
    return nodes


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _organization_name(value: Any) -> str | None:
    if isinstance(value, dict):
        return _text(value.get("name"))
    return _text(value)


def _location_text(value: Any) -> str | None:
    """`jobLocation` as one human string; never touches `jobLocationType`."""
    if isinstance(value, list):
        parts = [p for p in (_location_text(item) for item in value) if p]
        return "; ".join(parts) if parts else None
    if not isinstance(value, dict):
        return _text(value)
    address = value.get("address")
    if isinstance(address, dict):
        address_parts = [
            text
            for key in ("addressLocality", "addressRegion", "addressCountry")
            if (text := _text(address.get(key))) is not None
        ]
        joined = ", ".join(address_parts)
        if joined:
            return joined
    return _text(value.get("name"))


def _applicant_location_requirements(value: Any) -> tuple[str, ...]:
    """Only what the markup explicitly declares — never derived from `jobLocationType`."""
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for entry in value:
        name = entry.get("name") if isinstance(entry, dict) else entry
        text = _text(name)
        if text:
            names.append(text)
    return tuple(names)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not decimal_value.is_finite():
        return None
    return decimal_value


def _salary_fields(
    value: Any,
) -> tuple[Decimal | None, Decimal | None, str | None, str | None]:
    if not isinstance(value, dict):
        return None, None, None, None
    currency = _text(value.get("currency"))
    inner = value.get("value")
    if isinstance(inner, dict):
        minimum = _decimal(inner.get("minValue"))
        maximum = _decimal(inner.get("maxValue"))
        single = _decimal(inner.get("value"))
        unit = _text(inner.get("unitText"))
        if minimum is None and maximum is None and single is not None:
            minimum = maximum = single
        return minimum, maximum, currency, unit
    single = _decimal(inner)
    return single, single, currency, None


def _apply_url(node: dict[str, Any], *, page_url: str) -> str | None:
    for key in ("url", "sameAs"):
        candidate = node.get(key)
        if _is_http_url(candidate):
            return candidate
    return page_url if _is_http_url(page_url) else None


def _fields_from_node(node: dict[str, Any], *, page_url: str) -> JobPostingFields | None:
    title = _text(node.get("title"))
    company = _organization_name(node.get("hiringOrganization"))
    apply_url = _apply_url(node, page_url=page_url)
    if not title or not company or not apply_url:
        # Identity/company/title/candidature link is what makes this a usable item
        # (F20-37 criterion 1). A node missing any of them is skipped, not fabricated.
        return None
    min_salary, max_salary, currency, unit = _salary_fields(node.get("baseSalary"))
    identifier = node.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    return JobPostingFields(
        identifier=_text(identifier),
        title=title,
        description_html=_text(node.get("description")),
        hiring_organization_name=company,
        apply_url=apply_url,
        date_posted=_parse_datetime(node.get("datePosted")),
        valid_through=_parse_datetime(node.get("validThrough")),
        employment_type=_text(
            ", ".join(node["employmentType"])
            if isinstance(node.get("employmentType"), list)
            else node.get("employmentType")
        ),
        job_location_text=_location_text(node.get("jobLocation")),
        job_location_type=_text(node.get("jobLocationType")),
        applicant_location_requirements=_applicant_location_requirements(
            node.get("applicantLocationRequirements")
        ),
        base_salary_min=min_salary,
        base_salary_max=max_salary,
        base_salary_currency=currency,
        base_salary_unit=unit,
        raw_node=node,
    )


def extract_job_postings(html: str, *, page_url: str) -> list[JobPostingFields]:
    """Read `<script type="application/ld+json">` `JobPosting` markup: object, list or
    `@graph`. Raises `AcquisitionError(PARSER_SCHEMA_CHANGED)` for a challenge, login,
    empty HTML, soft-404, or a page with no compatible markup — never an empty success.
    """
    if not html or not html.strip():
        raise AcquisitionError(
            AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
            "job posting page returned an empty body",
        )
    nodes: list[dict[str, Any]] = []
    for raw_script in _JSONLD_SCRIPT.findall(html):
        try:
            parsed = json.loads(raw_script.strip())
        except ValueError:
            continue
        nodes.extend(_iter_job_posting_nodes(parsed))
    fields = [
        parsed_fields
        for node in nodes
        if (parsed_fields := _fields_from_node(node, page_url=page_url)) is not None
    ]
    if not fields:
        raise AcquisitionError(
            AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
            "no compatible JobPosting markup found "
            "(challenge, soft-404, empty page or unsupported schema)",
        )
    return fields


def job_posting_metadata_v1(fields: JobPostingFields) -> dict[str, object]:
    """Serialize `JobPostingFields` for `CollectedItem.metadata['job_posting_v1']`."""
    return {
        "identifier": fields.identifier,
        "employment_type": fields.employment_type,
        "job_location_text": fields.job_location_text,
        "job_location_type": fields.job_location_type,
        "applicant_location_requirements": list(fields.applicant_location_requirements),
        "valid_through": fields.valid_through.isoformat() if fields.valid_through else None,
        "base_salary_min": (
            str(fields.base_salary_min) if fields.base_salary_min is not None else None
        ),
        "base_salary_max": (
            str(fields.base_salary_max) if fields.base_salary_max is not None else None
        ),
        "base_salary_currency": fields.base_salary_currency,
        "base_salary_unit": fields.base_salary_unit,
        "parser_version": _PARSER_VERSION,
    }


def _external_id(fields: JobPostingFields) -> str:
    if fields.identifier:
        return f"jobposting:{fields.identifier}"
    digest = hashlib.sha256(f"{fields.apply_url}|{fields.title}".encode()).hexdigest()
    return f"jobposting:{digest}"


class JobPostingCollector:
    """Reads a single configured page for `JobPosting` structured data."""

    source_type = "jobposting"
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
        return HealthResult(
            healthy=True,
            summary="JobPosting pages are read directly; no dedicated API to probe",
        )

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        page_url = request.company_reference
        if not _is_http_url(page_url):
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "jobposting collector requires an absolute HTTP(S) configuration.page_url",
                field="configuration.page_url",
            )
        assert page_url is not None
        html = await self._fetch_page(page_url, request)
        postings = extract_job_postings(html, page_url=page_url)
        emitted = 0
        for fields in postings:
            yield self._item(fields)
            emitted += 1
            if request.max_items is not None and emitted >= request.max_items:
                return

    async def _fetch_page(self, page_url: str, request: CollectionRequest) -> str:
        if self._client is not None:
            return await self._fetch_with_client(self._client, page_url, request)
        async with self._client_factory() as client:
            return await self._fetch_with_client(client, page_url, request)

    async def _fetch_with_client(
        self, client: httpx.AsyncClient, page_url: str, request: CollectionRequest
    ) -> str:
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
                response = await client.get(page_url, follow_redirects=True)
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response)
                if error is None:
                    return response.text
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "job posting page request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to the job posting page",
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
                f"job posting page returned HTTP {status}",
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
                f"job posting page returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"job posting page returned HTTP {status}",
        )

    def _retry_delay(
        self, response: httpx.Response | None, *, default: float, maximum: float
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
    def _item(fields: JobPostingFields) -> CollectedItem:
        return CollectedItem(
            source_type=JobPostingCollector.source_type,
            external_id=_external_id(fields),
            url=fields.apply_url,
            title=fields.title,
            company_name=fields.hiring_organization_name,
            location_text=fields.job_location_text,
            description=fields.description_html,
            published_at=fields.date_posted,
            valid_through=fields.valid_through,
            raw_payload=fields.raw_node,
            metadata={
                "job_posting_v1": job_posting_metadata_v1(fields),
                "attribution": "schema.org JobPosting",
            },
        )
