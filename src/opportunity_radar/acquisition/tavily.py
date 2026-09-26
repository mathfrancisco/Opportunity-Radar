"""Tavily REST client: authenticated /search and /extract with retry and telemetry.

Follows the shape of `RemotiveCollector` (docs/44-roadmap-fase-20/fase-20/f20-42-...md,
"Notas de implementação"): client/client_factory injectable, deterministic retry without
real `asyncio.sleep`, telemetry recorded through the same `CollectionTelemetry` every other
collector uses. This module only talks to Tavily; the discovery collector that turns
results into `CollectedItem`s is a later card (F20-44), and the per-run credit budget that
stops new calls once a ceiling is hit is F20-43 (`TavilyCreditBudget` below).
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionNetworkPolicy,
    CollectionRequest,
    CollectionTelemetry,
    CollectorCapabilities,
    HealthcheckContext,
    HealthResult,
    SourceRun,
)
from opportunity_radar.acquisition.models import TavilyExtractCacheModel

_SEARCH_PATH = "/search"
_EXTRACT_PATH = "/extract"
_MAX_EXTRACT_URLS = 20
_SEARCH_PARSER_VERSION = "tavily-search-v1"

# Query keys that identify a click's origin rather than the resource itself. Stripped so
# two links to the same job posting that differ only by campaign tagging canonicalize to
# the same URL (F20-44). Mirrors the tracking-key list `opportunities.domain.normalize_url`
# already uses for the same reason; kept local rather than imported to avoid giving
# `acquisition` a new dependency on `opportunities` for one helper (acquisition currently
# has no such dependency in either direction) — noted here as a deliberate choice.
_TRACKING_QUERY_PREFIXES = ("utm_",)
_TRACKING_QUERY_KEYS = frozenset({"ref", "source", "gclid", "fbclid"})

# Board key location per ATS, matching `acquisition.proposals.IDENTIFIER_KEYS`.
_ATS_BOARD_PATTERNS: dict[str, re.Pattern[str]] = {
    "ashby": re.compile(r"^jobs\.ashbyhq\.com/([^/?#]+)"),
    "greenhouse": re.compile(r"^boards\.greenhouse\.io/([^/?#]+)"),
    "lever": re.compile(r"^jobs\.lever\.co/([^/?#]+)"),
}


def canonicalize_url(url: str) -> str:
    """Lowercase host, no fragment, no tracking query params.

    The single normalization used both for within-run dedupe here (F20-44) and for the
    extraction cache hash (F20-45) — one function, not two copies of the same rule.
    """
    parsed = urlsplit(url.strip())
    hostname = (parsed.hostname or "").casefold()
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    path = parsed.path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not (
                key.casefold().startswith(_TRACKING_QUERY_PREFIXES)
                or key.casefold() in _TRACKING_QUERY_KEYS
            )
        ),
        doseq=True,
    )
    return urlunsplit((parsed.scheme.casefold(), netloc, path, query, ""))


def detect_ats_board(url: str) -> tuple[str, str] | None:
    """`(source_type, board_key)` when `url` matches a known ATS board pattern, else `None`."""
    parsed = urlsplit(url.strip())
    hostname = (parsed.hostname or "").casefold()
    candidate = f"{hostname}{parsed.path}"
    for source_type, pattern in _ATS_BOARD_PATTERNS.items():
        match = pattern.match(candidate)
        if match:
            return source_type, match.group(1)
    return None


@dataclass(frozen=True, slots=True)
class TavilySearchResultItem:
    url: str
    title: str | None
    content: str | None
    score: float | None
    raw_payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TavilySearchResponse:
    results: tuple[TavilySearchResultItem, ...]
    #: Credits Tavily says this one call cost, read from `usage` (`include_usage=true` is
    #: always sent). `None` when the response omitted the block instead of raising —
    #: absence of usage data is not treated as a schema break here.
    credits_used: int | None
    raw_payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TavilyExtractedPage:
    url: str
    raw_content: str | None
    raw_payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TavilyExtractResponse:
    results: tuple[TavilyExtractedPage, ...]
    failed_results: tuple[Mapping[str, Any], ...]
    credits_used: int | None
    raw_payload: Mapping[str, Any]


@dataclass(slots=True)
class TavilyCreditBudget:
    """Tracks credits spent by one `SourceRun` against a per-run ceiling (F20-43).

    Lives per run, not globally: two concurrent runs of different sources do not share a
    counter (docs/44-roadmap-fase-20/fase-20/f20-43-...md, "Notas de implementação").
    """

    limit: int
    spent: int = 0

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError("limit cannot be negative")
        if self.spent < 0:
            raise ValueError("spent cannot be negative")

    @property
    def exhausted(self) -> bool:
        return self.spent >= self.limit

    def ensure_can_call(self) -> None:
        """Raise before starting a new /search or /extract call once the ceiling is hit.

        This is a deliberate budget stop, never a network or provider failure: callers
        catch `AcquisitionError` with `CREDIT_BUDGET_EXCEEDED` and finish the run
        `PARTIAL`, not `FAILED` (SPEC 41, section 6).
        """
        if self.exhausted:
            raise AcquisitionError(
                AcquisitionErrorCode.CREDIT_BUDGET_EXCEEDED,
                f"Tavily credit budget for this run exhausted "
                f"({self.spent} of {self.limit} credits spent)",
            )

    def charge(self, credits: int | None) -> None:
        if credits is None:
            return
        if credits < 0:
            raise ValueError("credits cannot be negative")
        self.spent += credits


class TavilyClient:
    """Authenticated `/search` and `/extract` calls against the Tavily REST API."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.tavily.com",
        search_depth: str = "basic",
        extract_depth: str = "basic",
        extract_format: str = "markdown",
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
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._search_depth = search_depth
        self._extract_depth = extract_depth
        self._extract_format = extract_format
        self._client = client
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0)
            )
        )
        self._max_retries = max_retries
        self._retry_after_seconds = retry_after_seconds
        self._sleeper = sleeper

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        if not self._api_key:
            return HealthResult(
                healthy=True,
                summary=(
                    "Tavily bloqueada por configuração: TAVILY_API_KEY ausente"
                ),
            )
        return HealthResult(
            healthy=True,
            summary="Tavily client is configured",
        )

    async def search(
        self,
        *,
        query: str,
        max_results: int = 5,
        search_depth: str | None = None,
        topic: str = "general",
        time_range: str | None = None,
        include_domains: Sequence[str] | None = None,
        exclude_domains: Sequence[str] | None = None,
        include_raw_content: bool = False,
        telemetry: CollectionTelemetry,
        network_policy: CollectionNetworkPolicy | None = None,
    ) -> TavilySearchResponse:
        if not query or not query.strip():
            raise ValueError("query must not be empty")
        payload: dict[str, Any] = {
            "query": query,
            "search_depth": search_depth or self._search_depth,
            "max_results": max_results,
            "topic": topic,
            "include_raw_content": include_raw_content,
            # Always requested: it is the only reliable way to read what a call cost in
            # credits (SPEC 41, section 3.3). Not a configuration toggle.
            "include_usage": True,
        }
        if time_range is not None:
            payload["time_range"] = time_range
        if include_domains:
            payload["include_domains"] = list(include_domains)
        if exclude_domains:
            payload["exclude_domains"] = list(exclude_domains)
        raw = await self._fetch(
            _SEARCH_PATH,
            payload,
            telemetry=telemetry,
            network_policy=network_policy,
            field="search_depth",
        )
        return self._parse_search_response(raw)

    async def extract(
        self,
        *,
        urls: Sequence[str],
        extract_depth: str | None = None,
        format: str | None = None,
        telemetry: CollectionTelemetry,
        network_policy: CollectionNetworkPolicy | None = None,
    ) -> TavilyExtractResponse:
        url_list = list(urls)
        if not url_list:
            raise ValueError("urls must not be empty")
        if len(url_list) > _MAX_EXTRACT_URLS:
            raise ValueError(f"extract accepts at most {_MAX_EXTRACT_URLS} urls per call")
        payload: dict[str, Any] = {
            "urls": url_list,
            "extract_depth": extract_depth or self._extract_depth,
            "format": format or self._extract_format,
            "include_usage": True,
        }
        raw = await self._fetch(
            _EXTRACT_PATH,
            payload,
            telemetry=telemetry,
            network_policy=network_policy,
            field="extract_depth",
        )
        return self._parse_extract_response(raw)

    async def _fetch(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        telemetry: CollectionTelemetry,
        network_policy: CollectionNetworkPolicy | None,
        field: str,
    ) -> Mapping[str, Any]:
        if not self._api_key:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "Tavily API key is not configured",
                field="tavily_api_key",
            )
        if self._client is not None:
            return await self._fetch_with_client(
                self._client, path, payload, telemetry, network_policy, field
            )
        async with self._client_factory() as client:
            return await self._fetch_with_client(
                client, path, payload, telemetry, network_policy, field
            )

    async def _fetch_with_client(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: Mapping[str, Any],
        telemetry: CollectionTelemetry,
        network_policy: CollectionNetworkPolicy | None,
        field: str,
    ) -> Mapping[str, Any]:
        max_retries = (
            network_policy.max_retries if network_policy is not None else self._max_retries
        )
        retry_delay = (
            network_policy.retry_delay_seconds
            if network_policy is not None
            else self._retry_after_seconds
        )
        max_retry_delay = (
            network_policy.max_retry_delay_seconds if network_policy is not None else 30.0
        )
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        for attempt in range(max_retries + 1):
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.post(url, json=dict(payload), headers=headers)
                if response.status_code == 429:
                    telemetry.record_rate_limit()
                error = self._response_error(response, field, path)
                if error is None:
                    return self._json(response)
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    f"Tavily {path} request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    f"could not connect to Tavily {path}",
                    retryable=True,
                )

            assert error is not None
            if not error.retryable or attempt == max_retries:
                raise error
            await self._sleeper(
                self._retry_delay(response, default=retry_delay, maximum=max_retry_delay)
            )

        raise AssertionError("unreachable")

    @staticmethod
    def _response_error(
        response: httpx.Response, field: str, path: str
    ) -> AcquisitionError | None:
        status = response.status_code
        if 200 <= status < 300:
            return None
        if status == 401:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_UNAUTHORIZED,
                f"Tavily {path} returned HTTP 401",
            )
        if status == 403:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_FORBIDDEN,
                f"Tavily {path} returned HTTP 403",
            )
        if status == 429:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_RATE_LIMITED,
                f"Tavily {path} returned HTTP 429",
                retryable=True,
            )
        if status == 432:
            # Parameter outside the contracted plan (e.g. `advanced` without credit) —
            # a configuration error, not a network or auth one (SPEC 41, section 4).
            return AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"Tavily {path} rejected the {field} parameter for this plan (HTTP 432)",
                field=field,
            )
        if status == 433:
            # Monthly usage limit exhausted. Not SOURCE_RATE_LIMITED (that implies a
            # retry in seconds) and not SOURCE_FORBIDDEN (that implies a permission
            # problem): the key is fine, the provider's budget for this cycle is spent.
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_QUOTA_EXHAUSTED,
                f"Tavily {path} reports the monthly usage limit is exhausted (HTTP 433)",
            )
        if 500 <= status < 600:
            return AcquisitionError(
                AcquisitionErrorCode.SOURCE_SERVER_ERROR,
                f"Tavily {path} returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Tavily {path} returned HTTP {status}",
        )

    @staticmethod
    def _retry_delay(
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
    def _json(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Tavily returned invalid JSON",
            ) from error
        if not isinstance(payload, dict):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Tavily response must be an object",
            )
        return payload

    @staticmethod
    def _credits_used(payload: Mapping[str, Any]) -> int | None:
        usage = payload.get("usage")
        if not isinstance(usage, Mapping):
            return None
        credits = usage.get("credits")
        if isinstance(credits, bool) or not isinstance(credits, int):
            return None
        return credits

    @staticmethod
    def _parse_search_response(payload: Mapping[str, Any]) -> TavilySearchResponse:
        results = payload.get("results")
        if not isinstance(results, list):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Tavily search response must contain a results list",
            )
        items: list[TavilySearchResultItem] = []
        for entry in results:
            if not isinstance(entry, Mapping):
                raise AcquisitionError(
                    AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                    "Tavily search result must be an object",
                )
            url = entry.get("url")
            if not isinstance(url, str) or not url:
                raise AcquisitionError(
                    AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                    "Tavily search result is missing a url",
                )
            score = entry.get("score")
            items.append(
                TavilySearchResultItem(
                    url=url,
                    title=entry.get("title") if isinstance(entry.get("title"), str) else None,
                    content=(
                        entry.get("content") if isinstance(entry.get("content"), str) else None
                    ),
                    score=(
                        float(score)
                        if isinstance(score, (int, float)) and not isinstance(score, bool)
                        else None
                    ),
                    raw_payload=entry,
                )
            )
        return TavilySearchResponse(
            results=tuple(items),
            credits_used=TavilyClient._credits_used(payload),
            raw_payload=payload,
        )

    @staticmethod
    def _parse_extract_response(payload: Mapping[str, Any]) -> TavilyExtractResponse:
        results = payload.get("results")
        if not isinstance(results, list):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Tavily extract response must contain a results list",
            )
        pages: list[TavilyExtractedPage] = []
        for entry in results:
            if not isinstance(entry, Mapping):
                raise AcquisitionError(
                    AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                    "Tavily extract result must be an object",
                )
            url = entry.get("url")
            if not isinstance(url, str) or not url:
                raise AcquisitionError(
                    AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                    "Tavily extract result is missing a url",
                )
            raw_content = entry.get("raw_content")
            pages.append(
                TavilyExtractedPage(
                    url=url,
                    raw_content=raw_content if isinstance(raw_content, str) else None,
                    raw_payload=entry,
                )
            )
        failed = payload.get("failed_results", [])
        if not isinstance(failed, list):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Tavily extract response failed_results must be a list",
            )
        return TavilyExtractResponse(
            results=tuple(pages),
            failed_results=tuple(entry for entry in failed if isinstance(entry, Mapping)),
            credits_used=TavilyClient._credits_used(payload),
            raw_payload=payload,
        )


class TavilySearchCollector:
    """Keyword-search discovery over the Tavily `/search` endpoint (F20-44).

    Sits next to `RemotiveCollector` in the registry: same `keyword_search` capability,
    same `CollectedItem` contract. Credit budgeting (F20-43) is applied per discovery run.
    Its Tavily call is guarded before it starts, then its reported usage is charged to
    the same run-scoped budget before items are emitted.
    """

    source_type = "tavily_search"
    capabilities = CollectorCapabilities(keyword_search=True)

    def __init__(
        self,
        *,
        client: TavilyClient | None = None,
        client_factory: Callable[[], TavilyClient] | None = None,
        time_range: str = "month",
        include_domains: Sequence[str] = (),
        max_results: int = 10,
        known_ats_boards: frozenset[tuple[str, str]] = frozenset(),
        credit_budget_per_run: int = 100,
    ) -> None:
        if client is not None and client_factory is not None:
            raise ValueError("provide either client or client_factory, not both")
        if client is None and client_factory is None:
            raise ValueError("provide client or client_factory")
        self._client = client
        self._client_factory = client_factory
        # Never open (card acceptance criterion): a default is always in effect, and
        # nothing in this class accepts `None` to widen it.
        self._time_range = time_range
        self._include_domains = tuple(include_domains)
        self._max_results = max_results
        if credit_budget_per_run < 0:
            raise ValueError("credit_budget_per_run cannot be negative")
        self._credit_budget_per_run = credit_budget_per_run
        # Pre-calculated pairs of (source_type, board_key) that already have a
        # CompanySource enabled for that board. Injected by whoever builds the registry,
        # since collectors carry no database session (see `Collector` Protocol).
        self._known_ats_boards = known_ats_boards

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        return await self._resolve_client().healthcheck(context)

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        if not request.keywords:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "tavily_search requires at least one keyword",
                field="keywords",
            )
        client = self._resolve_client()
        budget = TavilyCreditBudget(limit=self._credit_budget_per_run)
        budget.ensure_can_call()
        query = " ".join(keyword.strip() for keyword in request.keywords)
        response = await client.search(
            query=query,
            max_results=self._max_results,
            time_range=self._time_range,
            include_domains=self._include_domains or None,
            telemetry=request.telemetry,
            network_policy=request.network_policy,
        )
        # Tavily reports usage only with the response, so this paid call can reach the
        # ceiling. The guard below prevents every subsequent call in this run.
        budget.charge(response.credits_used)
        request.telemetry.record_credits(response.credits_used or 0)
        seen_urls: set[str] = set()
        emitted = 0
        for rank, result in enumerate(response.results):
            canonical = canonicalize_url(result.url)
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            metadata: dict[str, Any] = {
                "query": query,
                "rank": rank,
                "score": result.score,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "parser_version": _SEARCH_PARSER_VERSION,
            }
            board = detect_ats_board(result.url)
            known_ats_boards = (
                request.known_ats_boards
                if request.known_ats_boards is not None
                else self._known_ats_boards
            )
            if board is not None and board not in known_ats_boards:
                metadata["source_proposal_candidate"] = True
            yield CollectedItem(
                source_type=self.source_type,
                url=result.url,
                title=result.title,
                description=result.content,
                raw_payload=result.raw_payload,
                metadata=metadata,
            )
            emitted += 1
            if request.max_items is not None and emitted >= request.max_items:
                budget.ensure_can_call()
                return
        budget.ensure_can_call()

    def _resolve_client(self) -> TavilyClient:
        if self._client is not None:
            return self._client
        assert self._client_factory is not None
        return self._client_factory()


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    url: str
    raw_content: str | None
    #: `AcquisitionErrorCode.value` when this URL failed inside an otherwise successful
    #: batch. `None` means the extraction succeeded (or found nothing, which is not an
    #: error — see `TavilyExtractResponse.results` vs `failed_results`).
    error: str | None
    from_cache: bool


class ExtractionCachePort(Protocol):
    """What `extract_missing_descriptions` needs from a cache (F20-45).

    A `Protocol`, not a hard dependency on `TavilyExtractionCache`: the batching and
    partial-failure logic below is exercised in tests against a plain in-memory stand-in,
    the same way `Collector` lets adapters be tested without a database.
    """

    def get(self, url: str) -> ExtractionResult | None: ...
    def put(self, url: str, result: ExtractionResult) -> None: ...


class TavilyExtractionCache:
    """Persists `/extract` results by canonical URL hash, one row per URL, forever within
    its TTL (F20-45). Reuses `canonicalize_url` (F20-44) for the hash so the dedupe in the
    collector and the cache key here never disagree about what "the same URL" means.
    """

    def __init__(self, *, session: Session, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._session = session
        self._ttl_seconds = ttl_seconds

    def get(self, url: str) -> ExtractionResult | None:
        row = self._session.get(TavilyExtractCacheModel, self._hash(url))
        if row is None:
            return None
        if row.expires_at <= datetime.now(UTC):
            return None
        return ExtractionResult(
            url=row.canonical_url,
            raw_content=row.raw_content,
            error=row.error,
            from_cache=True,
        )

    def put(self, url: str, result: ExtractionResult) -> None:
        url_hash = self._hash(url)
        canonical = canonicalize_url(url)
        now = datetime.now(UTC)
        row = self._session.get(TavilyExtractCacheModel, url_hash)
        if row is None:
            row = TavilyExtractCacheModel(url_hash=url_hash, canonical_url=canonical)
            self._session.add(row)
        row.canonical_url = canonical
        row.raw_content = result.raw_content
        row.status = "failed" if result.error else "success"
        row.error = result.error
        row.extracted_at = now
        row.expires_at = now + timedelta(seconds=self._ttl_seconds)

    @staticmethod
    def _hash(url: str) -> str:
        return hashlib.sha256(canonicalize_url(url).encode()).hexdigest()


def _partition(urls: Sequence[str], size: int) -> list[list[str]]:
    return [list(urls[index : index + size]) for index in range(0, len(urls), size)]


async def extract_missing_descriptions(
    client: TavilyClient,
    cache: ExtractionCachePort,
    urls: Sequence[str],
    *,
    extract_depth: str | None = None,
    format: str | None = None,
    telemetry: CollectionTelemetry,
    network_policy: CollectionNetworkPolicy | None = None,
    budget: TavilyCreditBudget | None = None,
    run: SourceRun | None = None,
) -> list[ExtractionResult]:
    """Fills in bodies for URLs with no description, one cache entry per URL forever.

    Partitions `urls` into batches of at most 20 (`/extract`'s own limit, not a radar
    choice), serves cache hits without a call, and only sends misses. A failure isolated to
    one URL inside a batch is recorded for that URL and never drops the batch's other
    results (SPEC 41, F20-45 acceptance criteria).
    """
    results: list[ExtractionResult] = []
    for batch in _partition(list(urls), _MAX_EXTRACT_URLS):
        misses: list[str] = []
        for url in batch:
            cached = cache.get(url)
            if cached is not None:
                results.append(cached)
            else:
                misses.append(url)
        if not misses:
            continue
        response = await client.extract(
            urls=misses,
            extract_depth=extract_depth,
            format=format,
            telemetry=telemetry,
            network_policy=network_policy,
        )
        if budget is not None:
            budget.charge(response.credits_used)
        if run is not None:
            run.record_credits(response.credits_used or 0)
        failed_by_url = {
            entry.get("url"): entry.get("error")
            for entry in response.failed_results
            if isinstance(entry.get("url"), str)
        }
        succeeded_urls = {page.url for page in response.results}
        for page in response.results:
            result = ExtractionResult(
                url=page.url, raw_content=page.raw_content, error=None, from_cache=False
            )
            cache.put(page.url, result)
            results.append(result)
        for url in misses:
            if url in succeeded_urls:
                continue
            error = failed_by_url.get(url) or AcquisitionErrorCode.INVALID_ITEM.value
            result = ExtractionResult(url=url, raw_content=None, error=str(error), from_cache=False)
            cache.put(url, result)
            results.append(result)
    return results


def apply_extracted_description(item: CollectedItem, result: ExtractionResult) -> CollectedItem:
    """Swaps in the extracted markdown when present; otherwise the item is unchanged.

    A failed or cache-miss-that-stayed-a-miss result carries `raw_content=None`, and the
    provisional description a collector already set (F20-44) is left standing rather than
    erased by an extraction that found nothing.
    """
    if result.raw_content is None:
        return item
    return replace(item, description=result.raw_content)
