"""Hacker News "Ask HN: Who is hiring?" collector (F20-55).

Reads the monthly thread through the two sanctioned programmatic channels reviewed in
docs/pesquisas/termos-hn-who-is-hiring.md — never the HTML of news.ycombinator.com:

* Algolia HN Search (`hn.algolia.com/api/v1/search_by_date`) to *locate* the month's
  thread (one request), so no item ids are walked by hand;
* the official Firebase API (`hacker-news.firebaseio.com/v0/item/<id>.json`) for the
  story (its `kids` are the top-level comments) and each comment.

Each top-level comment is one job. The text is free-form, so parsing is deliberately
conservative: only the conventional `Company | Role | Location | ...` header line is read,
and a comment whose company or role cannot be identified is reported as an invalid item
(a pending review, run status PARTIAL) instead of being emitted as an empty job.
"""

from __future__ import annotations

import asyncio
import html
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
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
from opportunity_radar.acquisition.tavily import detect_ats_board

ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
FIREBASE_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
ITEM_PERMALINK = "https://news.ycombinator.com/item?id={item_id}"
DISCOVERY_VIA = "hn_who_is_hiring"
_PARSER_VERSION = "hn-who-is-hiring-v1"
_THREAD_TITLE = re.compile(
    r"^Ask HN: Who is hiring\? \((?P<month>[A-Za-z]+) (?P<year>\d{4})\)$"
)
_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "january february march april may june july august "
            "september october november december"
        ).split(),
        start=1,
    )
}

_TAG = re.compile(r"<[^>]+>")
_PARAGRAPH = re.compile(r"<\s*/?\s*p\s*/?\s*>|<\s*br\s*/?\s*>", re.IGNORECASE)
_HREF = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_BATCH = re.compile(r"\s*\((?:YC\s*)?([WSFX]\d{2}|(?:Winter|Summer|Spring|Fall) \d{4})\)\s*$")
_ROLE = re.compile(
    r"\b(engineer|engineers|engineering|developer|developers|designer|scientist|analyst|"
    r"manager|architect|sre|devops|intern|internship|founding|director|researcher|"
    r"programmer|full[- ]?stack|front[- ]?end|back[- ]?end|swe|qa|recruiter|"
    r"consultant|head of|cto|ceo|writer|specialist|technician|apprentice|eng|engr|"
    r"technical staff)\b",
    re.IGNORECASE,
)
_LOCATION_MARKER = re.compile(
    r"\b(remote|on[- ]?site|onsite|hybrid|in[- ]person)\b", re.IGNORECASE
)
_PLACE = re.compile(r"^[A-Z][A-Za-z.'\- ]+(?:,\s*[A-Z][A-Za-z.'\- ]+)+$")
_NEGATED_REMOTE = re.compile(
    r"\b(no remote|not remote|non[- ]remote|remote not|remote is not)\b", re.IGNORECASE
)
_ONSITE = re.compile(r"\bon[- ]?site\b", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)?")
_ROLE_HEAD = re.compile(
    r"\b(engineer|engineers|developer|developers|designer|manager|scientist|analyst|"
    r"architect|swe|intern)\b",
    re.IGNORECASE,
)
_NOT_A_COMPANY = frozenset({"nyc", "sf", "la", "uk", "us", "usa", "eu", "hiring", "location"})
_MAX_COMPANY_LENGTH = 80
_MAX_COMPANY_WORDS = 8


@dataclass(frozen=True, slots=True)
class ParsedComment:
    company: str
    #: `None` when the header names no role: the item is kept as evidence (company,
    #: location, text) but cannot normalize into an opportunity — never a guessed title.
    title: str | None
    roles: tuple[str, ...]
    location_text: str | None
    remote: bool | None
    yc_batch: str | None
    urls: tuple[str, ...]
    text: str


def comment_text(html_text: str) -> tuple[str, tuple[str, ...]]:
    """Plain text (paragraphs as lines) and the hrefs of an HN comment's HTML."""
    urls = tuple(dict.fromkeys(html.unescape(url) for url in _HREF.findall(html_text)))
    text = _TAG.sub("", _PARAGRAPH.sub("\n", html_text))
    return html.unescape(text).strip(), urls


def _clean_segment(segment: str) -> str:
    return re.sub(r"\s+", " ", _URL.sub("", segment)).strip(" 	-–—:;,")


def parse_comment(html_text: str) -> ParsedComment | None:
    """Parse the conventional `Company | Role | Location | ...` header, else `None`.

    `None` means "company not identifiable" — never a guess. A header with a company but no
    recognizable role parses with `title=None`.
    """
    text, urls = comment_text(html_text)
    header = next((line.strip() for line in text.splitlines() if line.strip()), "")
    segments = [_clean_segment(segment) for segment in header.split("|")]
    segments = [segment for segment in segments if segment]
    if len(segments) < 2:
        return None
    company = segments[0]
    batch_match = _BATCH.search(company)
    yc_batch = batch_match.group(1) if batch_match else None
    if batch_match:
        company = company[: batch_match.start()].strip()
    company = _PARENTHETICAL.sub("", company).strip()
    if (
        not company
        or len(company) > _MAX_COMPANY_LENGTH
        or len(company.split()) > _MAX_COMPANY_WORDS
        or _LOCATION_MARKER.search(company)
        or _ROLE_HEAD.search(company)
        or company.casefold() in _NOT_A_COMPANY
        or company.endswith(":")
    ):
        return None
    rest = segments[1:]
    location_parts = [segment for segment in rest if _LOCATION_MARKER.search(segment)]
    roles = tuple(
        segment
        for segment in rest
        if _ROLE.search(segment) and segment not in location_parts and len(segment) <= 120
    )
    if not location_parts:
        location_parts = [
            segment
            for segment in rest
            if segment not in roles and _PLACE.match(segment) and len(segment) <= 60
        ][:1]
    location_text = " | ".join(location_parts) or None
    return ParsedComment(
        company=company,
        title=roles[0] if roles else None,
        roles=roles,
        location_text=location_text,
        remote=_remote(location_text),
        yc_batch=yc_batch,
        urls=urls,
        text=text,
    )


def _remote(location_text: str | None) -> bool | None:
    if location_text is None:
        return None
    if _NEGATED_REMOTE.search(location_text):
        return False
    if re.search(r"\bremote\b", location_text, re.IGNORECASE):
        return True
    if _ONSITE.search(location_text):
        return False
    return None

def _thread_month(title: str) -> tuple[int, int] | None:
    match = _THREAD_TITLE.match(title.strip())
    if match is None:
        return None
    month = _MONTHS.get(match.group("month").casefold())
    return (int(match.group("year")), month) if month else None


class HackerNewsCollector:
    """Monthly "Who is hiring?" thread as one job per top-level comment."""

    source_type = "hacker_news"
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
        if max_retries < 0 or retry_after_seconds < 0:
            raise ValueError("retry settings cannot be negative")
        self._client = client
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=15.0, pool=5.0),
                headers={"User-Agent": "opportunity-radar (personal job radar)"},
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
            healthy=True, summary="Hacker News Who-is-hiring collector is configured"
        )

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        if self._client is not None:
            async for item in self._discover(self._client, request):
                yield item
            return
        async with self._client_factory() as client:
            async for item in self._discover(client, request):
                yield item

    async def _discover(
        self, client: httpx.AsyncClient, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        thread_id, thread_title = await self._locate_thread(client, request)
        story = await self._get_json(
            client, FIREBASE_ITEM_URL.format(item_id=thread_id), None, request
        )
        kids = story.get("kids") if isinstance(story, dict) else None
        if not isinstance(kids, list) or any(
            isinstance(kid, bool) or not isinstance(kid, int) for kid in kids
        ):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Hacker News thread kids must be a list of integer ids",
            )
        keywords = tuple(k.casefold() for k in request.keywords if k.strip())
        emitted = 0
        live = 0
        for kid in kids:
            comment = await self._get_json(
                client, FIREBASE_ITEM_URL.format(item_id=kid), None, request
            )
            if not isinstance(comment, dict) or comment.get("deleted") or comment.get("dead"):
                continue
            body = comment.get("text")
            if comment.get("type") != "comment" or not isinstance(body, str) or not body:
                continue
            live += 1
            parsed = parse_comment(body)
            if parsed is None:
                request.telemetry.record_invalid_item(
                    f"Hacker News comment {kid}: company or role not identifiable"
                )
                continue
            if parsed.title is None and not any(
                detect_ats_board(url) is not None for url in parsed.urls
            ):
                # Card F48-03 (same family as F20-75): a header that names no role is not an
                # opportunity. Skipped, not persisted as a raw item the normalizer would
                # then record as FAILED. A comment that still links a supported ATS board
                # is persisted: it feeds the source-proposal queue (F20-55).
                request.telemetry.record_skipped_item()
                continue
            if keywords and not any(k in parsed.text.casefold() for k in keywords):
                continue
            yield self._item(comment, parsed, thread_id, thread_title)
            emitted += 1
            if request.max_items is not None and emitted >= request.max_items:
                return
        if not keywords:
            # Deleted/dead comments are never "seen"; announcing the live count keeps the
            # completeness check exact (a keyword filter legitimately reads fewer).
            request.telemetry.record_items_announced(live)

    async def _locate_thread(
        self, client: httpx.AsyncClient, request: CollectionRequest
    ) -> tuple[int, str]:
        """Newest "Who is hiring?" thread by the bot, or `company_reference` = `YYYY-MM`."""
        payload = await self._get_json(
            client,
            ALGOLIA_URL,
            {
                "query": "Ask HN: Who is hiring?",
                "tags": "story,author_whoishiring",
                "hitsPerPage": 12,
                "attributesToRetrieve": "objectID,title,created_at",
            },
            request,
        )
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Hacker News search response hits must be a list",
            )
        wanted = (request.company_reference or "").strip()
        candidates: list[tuple[tuple[int, int], int, str]] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            title = hit.get("title")
            object_id = hit.get("objectID")
            month = _thread_month(title) if isinstance(title, str) else None
            if month is None or not isinstance(object_id, str) or not object_id.isdigit():
                continue
            candidates.append((month, int(object_id), title))  # type: ignore[arg-type]
        if wanted:
            candidates = [c for c in candidates if f"{c[0][0]:04d}-{c[0][1]:02d}" == wanted]
        if not candidates:
            raise AcquisitionError(
                AcquisitionErrorCode.SOURCE_NOT_FOUND,
                "no 'Ask HN: Who is hiring?' thread found"
                + (f" for {wanted}" if wanted else ""),
            )
        _, thread_id, title = max(candidates, key=lambda c: c[0])
        return thread_id, title

    @staticmethod
    def _item(
        comment: Mapping[str, Any],
        parsed: ParsedComment,
        thread_id: int,
        thread_title: str,
    ) -> CollectedItem:
        comment_id = comment.get("id")
        if isinstance(comment_id, bool) or not isinstance(comment_id, int):
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                "Hacker News comment id must be an integer",
            )
        posted = comment.get("time")
        published_at = (
            datetime.fromtimestamp(posted, UTC)
            if isinstance(posted, int) and not isinstance(posted, bool)
            else None
        )
        ats_board = next(
            (board for url in parsed.urls if (board := detect_ats_board(url)) is not None),
            None,
        )
        ats_url = (
            next(url for url in parsed.urls if detect_ats_board(url) == ats_board)
            if ats_board is not None
            else None
        )
        return CollectedItem(
            source_type=HackerNewsCollector.source_type,
            external_id=str(comment_id),
            url=ITEM_PERMALINK.format(item_id=comment_id),
            title=parsed.title,
            company_name=parsed.company,
            location_text=parsed.location_text,
            description=parsed.text,
            published_at=published_at,
            raw_payload=comment,
            metadata={
                "thread_id": thread_id,
                "thread_title": thread_title,
                "roles": list(parsed.roles),
                "remote": parsed.remote,
                "yc_batch": parsed.yc_batch,
                "urls": list(parsed.urls),
                "ats_board_url": ats_url,
                "attribution": "Hacker News",
                "parser_version": _PARSER_VERSION,
            },
        )

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: Mapping[str, str | int] | None,
        request: CollectionRequest,
    ) -> Any:
        policy = request.network_policy
        max_retries = policy.max_retries if policy is not None else self._max_retries
        retry_delay = (
            policy.retry_delay_seconds if policy is not None else self._retry_after_seconds
        )
        max_retry_delay = policy.max_retry_delay_seconds if policy is not None else 30.0
        minimum_interval = policy.minimum_interval_seconds if policy is not None else 0.0
        for attempt in range(max_retries + 1):
            await self._wait(request, minimum_interval)
            response: httpx.Response | None = None
            error: AcquisitionError | None = None
            try:
                request.telemetry.record_http_attempt(retry=attempt > 0)
                response = await client.get(url, params=params)
                if response.status_code == 429:
                    request.telemetry.record_rate_limit()
                error = self._response_error(response)
                if error is None:
                    try:
                        return response.json()
                    except ValueError as invalid:
                        raise AcquisitionError(
                            AcquisitionErrorCode.PARSER_SCHEMA_CHANGED,
                            "Hacker News returned invalid JSON",
                        ) from invalid
            except httpx.TimeoutException:
                error = AcquisitionError(
                    AcquisitionErrorCode.SOURCE_TIMEOUT,
                    "Hacker News request timed out",
                    retryable=True,
                )
            except httpx.TransportError:
                error = AcquisitionError(
                    AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
                    "could not connect to Hacker News",
                    retryable=True,
                )
            assert error is not None
            if not error.retryable or attempt == max_retries:
                raise error
            delay = retry_delay
            if error.retry_after_seconds is not None:
                delay = error.retry_after_seconds
            await self._sleeper(min(max(delay, minimum_interval), max_retry_delay))
        raise AssertionError("unreachable")

    async def _wait(self, request: CollectionRequest, minimum_interval: float) -> None:
        last_attempt = request.telemetry.last_http_attempt_at
        if last_attempt is None or minimum_interval == 0:
            return
        delay = minimum_interval - (datetime.now(UTC) - last_attempt).total_seconds()
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
                f"Hacker News returned HTTP {status}",
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
                f"Hacker News returned HTTP {status}",
                retryable=True,
            )
        return AcquisitionError(
            AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR,
            f"Hacker News returned HTTP {status}",
        )
