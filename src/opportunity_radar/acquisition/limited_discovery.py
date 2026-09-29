"""Limited multi-page discovery for a company whose careers page hides its ATS (F20-36).

`companies/discovery.py` (F20-27) makes exactly one polite GET at the careers page. Many
companies embed their ATS one click deeper — a "team"/"jobs" subpage, or a link only a
sitemap reveals. This module extends that single request into a small, budgeted crawl:
robots.txt first, then the site's declared sitemap(s), then a handful of same-allowlist
HTML pages, always inside `DiscoveryLimits` and never past a private/loopback/link-local
destination. It never creates a `SourceRun` or `RawItem` — discovery is research, evidence
for a human, not collection (SPEC 39 §5 / SPEC 43).
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import zlib
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.companies.discovery import ATS_SIGNATURES, detect_ats
from opportunity_radar.companies.models import CompanySource, DiscoveryAttemptModel

DEFAULT_USER_AGENT = "OpportunityRadarDiscoveryBot/1.0 (+https://opportunity-radar.invalid)"
DEFAULT_TIMEOUT_SECONDS = 10.0
# One request per second across the whole run (SPEC 39 §5); a real batch run passes this
# explicitly, tests leave it at 0 so they do not sleep.
DEFAULT_MINIMUM_INTERVAL_SECONDS = 0.0
#: A policy stop (robots disallow, private destination, unsafe XML) is not transient:
#: it is worth re-checking on the normal weekly cadence, not sooner.
POLICY_BACKOFF = timedelta(days=7)
#: robots.txt being unreachable is more likely transient than a real policy decision, so
#: the next attempt is much sooner.
ROBOTS_UNAVAILABLE_BACKOFF = timedelta(hours=1)
SUCCESS_BACKOFF = timedelta(days=30)
_MAX_REDIRECTS = 5
_RELEVANT_PAGE_HINTS = ("career", "job", "vaga", "emprego", "team", "join", "hiring")
#: Stricter than `_RELEVANT_PAGE_HINTS`: sitemap URLs are numerous and noisy, so only
#: these keywords (English + Portuguese) earn a sitemap-discovered URL a crawl slot.
_SITEMAP_KEYWORDS = re.compile(r"career|jobs?|vagas?|carreiras?", re.IGNORECASE)
_ATTRIBUTE_URL = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_GZIP_MAGIC = b"\x1f\x8b"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

#: Direct, one-request-per-candidate probes against each ATS's own public API — no
#: crawling of the company's site at all. Tried in this order, first non-empty match wins
#: (F20-36 follow-up: most real boards are reachable this way). Only ATS with a collector
#: (never Gupy, which the project cannot aggregate per F20-32).
_DIRECT_ATS_ENDPOINTS: tuple[tuple[str, Callable[[str], str]], ...] = (
    ("ashby", lambda slug: f"https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ("greenhouse", lambda slug: f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
    ("lever", lambda slug: f"https://api.lever.co/v0/postings/{slug}?mode=json"),
    ("workable", lambda slug: f"https://apply.workable.com/api/v1/widget/accounts/{slug}"),
    ("teamtailor", lambda slug: f"https://{slug}.teamtailor.com/jobs.json"),
)
#: Where each ATS's response keeps its job list, for the "is this actually a populated,
#: real board" check — `None` means the response body itself is the list (Lever).
_JOBS_LIST_KEYS: dict[str, str | None] = {
    "ashby": "jobs",
    "greenhouse": "jobs",
    "lever": None,
    "workable": "jobs",
    "teamtailor": "items",
}


class DiscoveryStopReason(StrEnum):
    EXHAUSTED = "EXHAUSTED"  # candidate queue drained within budget
    LIMIT_REACHED = "LIMIT_REACHED"  # depth, responses, bytes or URLs
    POLICY = "POLICY"  # robots.txt, allowlist or private destination
    ERROR = "ERROR"
    DYNAMIC_SITE = "DYNAMIC_SITE"  # evidence of JS rendering, no headless
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class DiscoveryLimits:
    """Conservative limits owned by this project (SPEC 39 §5), not by any protocol."""

    max_depth: int = 2
    max_html_responses: int = 20
    max_sitemap_files: int = 5
    max_html_bytes: int = 2 * 1024 * 1024
    max_sitemap_decompressed_bytes: int = 5 * 1024 * 1024
    max_urls_examined: int = 5_000
    concurrency_per_host: int = 1

    def __post_init__(self) -> None:
        values = (
            self.max_depth,
            self.max_html_responses,
            self.max_sitemap_files,
            self.max_html_bytes,
            self.max_sitemap_decompressed_bytes,
            self.max_urls_examined,
            self.concurrency_per_host,
        )
        if any(value < 0 for value in values):
            raise ValueError("discovery limits cannot be negative")
        if self.concurrency_per_host < 1:
            raise ValueError("concurrency_per_host must be at least 1")


@dataclass(frozen=True, slots=True)
class DiscoveredEndpoint:
    company_id: UUID
    seed_url: str
    discovered_url: str
    method: str  # "sitemap" | "html_link" | "iframe" | "script" | "seed"
    fetched_at: datetime
    evidence_excerpt: str
    confidence_reason: str  # "ats_signature:<name>"


@dataclass(frozen=True, slots=True)
class DiscoveryOutcome:
    company_id: UUID
    stop_reason: DiscoveryStopReason
    endpoints: tuple[DiscoveredEndpoint, ...]
    urls_examined: int
    http_requests: int
    next_attempt_at: datetime | None


def endpoint_ats_name(endpoint: DiscoveredEndpoint) -> str | None:
    """The ATS name a `DiscoveredEndpoint` matched, parsed back from `confidence_reason`."""
    prefix = "ats_signature:"
    if endpoint.confidence_reason.startswith(prefix):
        return endpoint.confidence_reason[len(prefix) :]
    return None


def _slugify(name: str) -> str:
    return _SLUG_PATTERN.sub("-", name.lower()).strip("-")


def direct_slug_candidates(company_name: str, seed_url: str) -> tuple[str, ...]:
    """A handful of plausible board slugs for a company: the hyphenated and compact
    forms of its name, plus its own site's registrable-domain label — in that order, de-
    duplicated. No network access; just string shaping."""
    host = urlsplit(seed_url).hostname or ""
    bare = host.split(":", 1)[0]
    parts = bare.split(".")
    domain_slug = parts[-2] if len(parts) >= 2 else bare
    hyphenated = _slugify(company_name)
    compact = hyphenated.replace("-", "")
    candidates: list[str] = []
    for slug in (compact, hyphenated, domain_slug):
        if slug and slug not in candidates:
            candidates.append(slug)
    return tuple(candidates)


def _has_jobs(ats: str, payload: object) -> bool:
    if ats == "lever":
        return isinstance(payload, list) and len(payload) > 0
    key = _JOBS_LIST_KEYS[ats]
    if not isinstance(payload, dict) or key is None:
        return False
    items = payload.get(key)
    return isinstance(items, list) and len(items) > 0


async def probe_direct_ats(
    company_id: UUID,
    company_name: str,
    seed_url: str,
    *,
    client: httpx.AsyncClient,
    resolve_ips: Callable[[str], Awaitable[tuple[str, ...]]],
    user_agent: str = DEFAULT_USER_AGENT,
    min_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_requests: int = 6,
    now: datetime | None = None,
    slugs: Sequence[str] | None = None,
    only_ats: Sequence[str] | None = None,
) -> tuple[DiscoveredEndpoint | None, int]:
    """One request per (ATS, slug) candidate against the ATS's own public API — never the
    company's own site. Stops at the first ATS/slug pair whose board is real and populated
    (F20-36 follow-up). Skips crawling entirely on a hit, which is most of the time this
    matters: a guessable slug is common and one request is far cheaper than a crawl.

    `slugs` replaces the name-derived guesses and `only_ats` narrows which ATS are tried —
    for a caller that already knows which board it wants confirmed (F20-53: a board named
    by a search result), so exactly that board is checked and nothing else is guessed.
    """
    moment = now or datetime.now(UTC)
    candidates = tuple(slugs) if slugs else direct_slug_candidates(company_name, seed_url)
    requests_made = 0
    for slug in candidates:
        for ats, build_url in _DIRECT_ATS_ENDPOINTS:
            if only_ats is not None and ats not in only_ats:
                continue
            if requests_made >= max_requests:
                return None, requests_made
            url = build_url(slug)
            host = urlsplit(url).hostname or ""
            ips = await resolve_ips(host)
            if not is_public_destination(host, ips):
                continue
            if requests_made > 0 and min_interval_seconds:
                await sleeper(min_interval_seconds)
            requests_made += 1
            try:
                response = await client.get(
                    url, headers={"User-Agent": user_agent}, timeout=DEFAULT_TIMEOUT_SECONDS
                )
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            try:
                payload = response.json()
            except ValueError:
                continue
            if not _has_jobs(ats, payload):
                continue
            endpoint = DiscoveredEndpoint(
                company_id=company_id,
                seed_url=seed_url,
                discovered_url=url,
                method="direct_slug",
                fetched_at=moment,
                evidence_excerpt=f"direct probe slug={slug!r}",
                confidence_reason=f"ats_signature:{ats}",
            )
            return endpoint, requests_made
    return None, requests_made


def canonical_board_url(ats: str, discovered_url: str) -> str:
    """The board's canonical root URL, independent of which page evidence was found on or
    which historical hostname was used — so the same real board never creates two
    `CompanySource` rows under different-looking `endpoint` values (F20-36 dedupe rule).
    """
    parts = urlsplit(discovered_url)
    token = parts.path.strip("/").split("/", 1)[0]
    if not token:
        return discovered_url
    if ats == "greenhouse":
        # boards.greenhouse.io and job-boards.greenhouse.io serve the same board; the
        # latter is the current hostname (F20-36 evidence, 2026-09-28).
        return f"https://job-boards.greenhouse.io/{token}"
    if ats == "ashby":
        return f"https://jobs.ashbyhq.com/{token}"
    if ats == "lever":
        return f"https://jobs.lever.co/{token}"
    return discovered_url


class _PolicyStop(Exception):
    """Robots, allowlist or a private destination refused this request outright."""


class _LimitReached(Exception):
    """A budget (requests, bytes, URLs) was exhausted mid-crawl."""


class _DiscoveryTransportError(Exception):
    """A single request failed at the transport level; the caller decides if it is fatal."""


def is_public_destination(host: str, resolved_ips: tuple[str, ...]) -> bool:
    """Refuse private/loopback/link-local/reserved network for the host or any of its IPs.

    Called before every connection and before following every redirect (SPEC 39 §5). A
    host that resolved to nothing is treated as unsafe: an empty answer is not evidence of
    a public destination.
    """
    if not resolved_ips:
        return False
    candidates = list(resolved_ips)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        candidates.append(host)
    for raw in candidates:
        try:
            parsed = ipaddress.ip_address(raw)
        except ValueError:
            return False
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            return False
    return True


def normalize_discovery_url(url: str) -> str:
    """A canonical form that keeps every query parameter (SPEC 39 §5 dedupe rule).

    A job-identifying query (`?gh_jid=123`) must never collapse into a different job by
    being stripped, so normalization only lower-cases scheme/host, drops the default port
    and fragment, and sorts query parameters for a stable comparison — it never removes one.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    else:
        netloc = host
    if parts.username:
        netloc = f"{parts.username}@{netloc}"
    path = parts.path or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def default_resolve_ips(host: str) -> tuple[str, ...]:
    """A synchronous DNS lookup; callers run it off the event loop (`asyncio.to_thread`)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return ()
    return tuple(sorted({str(info[4][0]) for info in infos}))


async def _default_async_resolve_ips(host: str) -> tuple[str, ...]:
    return await asyncio.to_thread(default_resolve_ips, host)


def _host_allowed(host: str, allowlist: frozenset[str]) -> bool:
    host = host.lower()
    for entry in allowlist:
        entry = entry.lower()
        if entry.startswith("."):
            if host == entry[1:] or host.endswith(entry):
                return True
        elif host == entry:
            return True
    return False


def _next_attempt(now: datetime, delta: timedelta) -> datetime:
    return now + delta


def _looks_dynamic(html: str) -> bool:
    """Heuristic for a JS-rendered shell: near-empty text body alongside script tags.

    Conservative on purpose: a false negative just means one extra wasted page fetch, a
    false positive would abandon a page that had real content to offer.
    """
    without_scripts = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text_only = re.sub(r"<[^>]+>", " ", without_scripts)
    visible = " ".join(text_only.split())
    return len(visible) < 200 and "<script" in html.lower()


def _evidence_snippet(html: str, ats: str) -> str:
    for signature in ATS_SIGNATURES[ats]:
        index = html.find(signature)
        if index != -1:
            start = max(0, index - 60)
            end = min(len(html), index + len(signature) + 60)
            return html[start:end].strip()
    return ats


def _extract_links(html: str, *, base: str) -> list[str]:
    links: list[str] = []
    for match in _ATTRIBUTE_URL.findall(html):
        try:
            joined = str(httpx.URL(base).join(match))
        except Exception:  # noqa: BLE001 - a malformed href is simply skipped
            continue
        if joined.startswith(("http://", "https://")):
            links.append(joined)
    return links


def _looks_relevant_page(url: str) -> bool:
    lowered = url.lower()
    return any(hint in lowered for hint in _RELEVANT_PAGE_HINTS)


class _UnsafeXmlError(Exception):
    """A sitemap declared a DOCTYPE/ENTITY; refused before any XML parser sees it."""


def _reject_unsafe_xml(raw: bytes) -> None:
    lowered = raw.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise _UnsafeXmlError("sitemap declares a doctype/entity; refused")


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_sitemap(raw: bytes) -> tuple[str, tuple[str, ...]]:
    """`(kind, locs)`; `kind` is `"urlset"` or `"sitemapindex"`. Raises `_UnsafeXmlError`."""
    _reject_unsafe_xml(raw)
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise _UnsafeXmlError(f"sitemap is not well-formed XML: {error}") from error
    kind = _local_tag(root.tag)
    locs: list[str] = []
    for child in root:
        for grandchild in child:
            if _local_tag(grandchild.tag) == "loc" and grandchild.text:
                locs.append(grandchild.text.strip())
    return kind, tuple(locs)


def _safe_decompress(raw: bytes, max_bytes: int) -> bytes:
    if not raw.startswith(_GZIP_MAGIC):
        if len(raw) > max_bytes:
            raise _LimitReached("sitemap exceeds the decompressed size budget")
        return raw
    # `gzip` has no streaming `decompressobj`; `zlib`'s does, given the right window bits
    # for the gzip container format (RFC 1952) rather than raw zlib/deflate.
    decompressor = zlib.decompressobj(wbits=zlib.MAX_WBITS | 16)
    chunks: list[bytes] = []
    total = 0
    step = 64 * 1024
    for offset in range(0, len(raw), step):
        chunk = decompressor.decompress(raw[offset : offset + step], max_bytes - total + 1)
        total += len(chunk)
        if total > max_bytes:
            raise _LimitReached("sitemap exceeds the decompressed size budget")
        chunks.append(chunk)
    return b"".join(chunks)


def _sitemap_urls_from_robots(robots_text: str) -> list[str]:
    urls = []
    for line in robots_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            urls.append(stripped.split(":", 1)[1].strip())
    return urls


@dataclass
class _RobotsPolicy:
    """A minimal robots.txt policy: only what this crawler needs to decide."""

    disallow_prefixes: tuple[str, ...]
    sitemap_urls: tuple[str, ...]

    def allows(self, path: str) -> bool:
        return not any(path.startswith(prefix) for prefix in self.disallow_prefixes if prefix)


def _parse_robots(text: str, *, user_agent: str) -> _RobotsPolicy:
    """A tiny RFC 9309 subset: our own agent's group, else `*`; `Disallow` only."""
    groups: dict[str, list[str]] = {}
    current_agents: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if current_agents and not any(
                groups.get(agent) for agent in current_agents
            ):
                pass
            current_agents = [value.lower()]
            groups.setdefault(value.lower(), [])
        elif key == "disallow" and current_agents:
            for agent in current_agents:
                groups[agent].append(value)
    target = user_agent.lower()
    for agent, rules in groups.items():
        if agent != "*" and agent in target:
            return _RobotsPolicy(tuple(rules), tuple(_sitemap_urls_from_robots(text)))
    return _RobotsPolicy(tuple(groups.get("*", [])), tuple(_sitemap_urls_from_robots(text)))


async def run_limited_discovery(
    seed_url: str,
    *,
    company_id: UUID,
    limits: DiscoveryLimits,
    allowlist: frozenset[str],
    client: httpx.AsyncClient,
    company_name: str = "",
    resolve_ips: Callable[[str], Awaitable[tuple[str, ...]]] | None = None,
    now: datetime | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    min_interval_seconds: float = DEFAULT_MINIMUM_INTERVAL_SECONDS,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    try_direct_slug: bool = True,
) -> DiscoveryOutcome:
    moment = now or datetime.now(UTC)
    resolver = resolve_ips or _default_async_resolve_ips
    seed_parts = urlsplit(seed_url)
    if seed_parts.scheme not in ("http", "https") or not seed_parts.hostname:
        return DiscoveryOutcome(
            company_id, DiscoveryStopReason.ERROR, (), 0, 0, _next_attempt(moment, POLICY_BACKOFF)
        )

    if try_direct_slug and company_name:
        direct_endpoint, direct_requests = await probe_direct_ats(
            company_id,
            company_name,
            seed_url,
            client=client,
            resolve_ips=resolver,
            user_agent=user_agent,
            min_interval_seconds=min_interval_seconds,
            sleeper=sleeper,
            now=moment,
        )
        if direct_endpoint is not None:
            return DiscoveryOutcome(
                company_id,
                DiscoveryStopReason.EXHAUSTED,
                (direct_endpoint,),
                direct_requests,
                direct_requests,
                _next_attempt(moment, SUCCESS_BACKOFF),
            )

    state = _CrawlState(
        client=client,
        limits=limits,
        allowlist=allowlist,
        resolver=resolver,
        user_agent=user_agent,
        min_interval_seconds=min_interval_seconds,
        sleeper=sleeper,
    )

    origin = f"{seed_parts.scheme}://{seed_parts.netloc}"
    try:
        robots = await state.fetch_robots(origin)
    except _PolicyStop:
        return DiscoveryOutcome(
            company_id,
            DiscoveryStopReason.POLICY,
            (),
            state.urls_examined,
            state.http_requests,
            _next_attempt(moment, ROBOTS_UNAVAILABLE_BACKOFF),
        )
    except _DiscoveryTransportError:
        return DiscoveryOutcome(
            company_id,
            DiscoveryStopReason.POLICY,
            (),
            state.urls_examined,
            state.http_requests,
            _next_attempt(moment, ROBOTS_UNAVAILABLE_BACKOFF),
        )

    if robots is not None and not robots.allows(seed_parts.path or "/"):
        return DiscoveryOutcome(
            company_id,
            DiscoveryStopReason.POLICY,
            (),
            state.urls_examined,
            state.http_requests,
            _next_attempt(moment, POLICY_BACKOFF),
        )

    sitemap_seeds = list(robots.sitemap_urls) if robots is not None else []
    if not sitemap_seeds:
        sitemap_seeds = [f"{origin}/sitemap.xml"]

    # Shallow pass first: the careers page alone. Sitemap and extra pages are only worth
    # the extra requests when this misses (most real signatures sit right on the seed).
    visited_pages: set[str] = set()
    try:
        endpoints, html_limited, dynamic_seen = await state.crawl_pages(
            seed_url=normalize_discovery_url(seed_url),
            extra_candidates=[],
            company_id=company_id,
            seed_url_raw=seed_url,
            fetched_at=moment,
            visited=visited_pages,
        )
    except _PolicyStop:
        return DiscoveryOutcome(
            company_id,
            DiscoveryStopReason.POLICY,
            (),
            state.urls_examined,
            state.http_requests,
            _next_attempt(moment, POLICY_BACKOFF),
        )

    sitemap_limited = False
    if not endpoints and not dynamic_seen:
        try:
            candidate_pages, sitemap_limited = await state.crawl_sitemaps(sitemap_seeds)
        except _PolicyStop:
            return DiscoveryOutcome(
                company_id,
                DiscoveryStopReason.POLICY,
                (),
                state.urls_examined,
                state.http_requests,
                _next_attempt(moment, POLICY_BACKOFF),
            )
        if candidate_pages:
            try:
                endpoints, html_limited, dynamic_seen = await state.crawl_pages(
                    seed_url=normalize_discovery_url(seed_url),
                    extra_candidates=candidate_pages,
                    company_id=company_id,
                    seed_url_raw=seed_url,
                    fetched_at=moment,
                    visited=visited_pages,
                )
            except _PolicyStop:
                return DiscoveryOutcome(
                    company_id,
                    DiscoveryStopReason.POLICY,
                    (),
                    state.urls_examined,
                    state.http_requests,
                    _next_attempt(moment, POLICY_BACKOFF),
                )

    if endpoints:
        stop_reason = DiscoveryStopReason.EXHAUSTED
        backoff = SUCCESS_BACKOFF
    elif sitemap_limited or html_limited:
        stop_reason = DiscoveryStopReason.LIMIT_REACHED
        backoff = POLICY_BACKOFF
    elif dynamic_seen:
        stop_reason = DiscoveryStopReason.DYNAMIC_SITE
        backoff = POLICY_BACKOFF
    else:
        stop_reason = DiscoveryStopReason.EXHAUSTED
        backoff = POLICY_BACKOFF

    return DiscoveryOutcome(
        company_id,
        stop_reason,
        tuple(endpoints),
        state.urls_examined,
        state.http_requests,
        _next_attempt(moment, backoff),
    )


class _CrawlState:
    """Mutable bookkeeping for one `run_limited_discovery` call. Not part of the public API."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        limits: DiscoveryLimits,
        allowlist: frozenset[str],
        resolver: Callable[[str], Awaitable[tuple[str, ...]]],
        user_agent: str,
        min_interval_seconds: float,
        sleeper: Callable[[float], Awaitable[None]],
    ) -> None:
        self._client = client
        self._limits = limits
        self._allowlist = allowlist
        self._resolver = resolver
        self._user_agent = user_agent
        self._min_interval = min_interval_seconds
        self._sleeper = sleeper
        self.http_requests = 0
        self.urls_examined = 0

    @property
    def _request_budget(self) -> int:
        return self._limits.max_html_responses + self._limits.max_sitemap_files

    async def _safe_destination(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or "@" in parts.netloc:
            return False
        host = parts.hostname
        if host is None or not _host_allowed(host, self._allowlist):
            return False
        ips = await self._resolver(host)
        return is_public_destination(host, ips)

    async def _get(self, url: str) -> httpx.Response:
        """One safety-checked, paced, redirect-following GET. Raises on any refusal."""
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            if not await self._safe_destination(current):
                raise _PolicyStop(f"unsafe destination: {current}")
            if self.http_requests >= self._request_budget:
                raise _LimitReached("http request budget exhausted")
            if self.http_requests > 0 and self._min_interval:
                await self._sleeper(self._min_interval)
            self.http_requests += 1
            try:
                response = await self._client.get(
                    current,
                    headers={"User-Agent": self._user_agent},
                    timeout=DEFAULT_TIMEOUT_SECONDS,
                    follow_redirects=False,
                )
            except httpx.HTTPError as error:
                raise _DiscoveryTransportError(str(error)) from error
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise _DiscoveryTransportError("redirect with no Location header")
                current = str(httpx.URL(current).join(location))
                continue
            return response
        raise _DiscoveryTransportError("too many redirects")

    async def fetch_robots(self, origin: str) -> _RobotsPolicy | None:
        try:
            response = await self._get(f"{origin}/robots.txt")
        except _DiscoveryTransportError as error:
            raise _PolicyStop(str(error)) from error
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise _PolicyStop(f"robots.txt returned HTTP {response.status_code}")
        return _parse_robots(response.text, user_agent=self._user_agent)

    async def crawl_sitemaps(self, seeds: list[str]) -> tuple[list[str], bool]:
        queue: deque[str] = deque(seeds)
        visited: set[str] = set()
        candidates: list[str] = []
        attempts = 0
        limited = False
        while queue:
            if attempts >= self._limits.max_sitemap_files:
                limited = bool(queue)
                break
            if self.urls_examined >= self._limits.max_urls_examined:
                limited = True
                break
            raw_url = queue.popleft()
            normalized = normalize_discovery_url(raw_url)
            if normalized in visited:
                continue
            visited.add(normalized)
            attempts += 1
            self.urls_examined += 1
            try:
                response = await self._get(normalized)
            except _LimitReached:
                limited = True
                break
            except _DiscoveryTransportError:
                continue
            if response.status_code >= 400:
                continue
            try:
                content = _safe_decompress(
                    response.content, self._limits.max_sitemap_decompressed_bytes
                )
                kind, locs = _parse_sitemap(content)
            except _LimitReached:
                limited = True
                break
            except _UnsafeXmlError:
                raise _PolicyStop("sitemap declares unsafe XML") from None
            if kind == "sitemapindex":
                queue.extend(locs)
            else:
                for loc in locs:
                    if _SITEMAP_KEYWORDS.search(loc.lower()):
                        candidates.append(loc)
        return candidates, limited

    async def crawl_pages(
        self,
        *,
        seed_url: str,
        extra_candidates: list[str],
        company_id: UUID,
        seed_url_raw: str,
        fetched_at: datetime,
        visited: set[str] | None = None,
    ) -> tuple[list[DiscoveredEndpoint], bool, bool]:
        queue: deque[tuple[str, int, str]] = deque()
        queue.append((seed_url, 0, "seed"))
        for candidate in extra_candidates:
            queue.append((normalize_discovery_url(candidate), 1, "sitemap"))
        visited = set() if visited is None else visited
        endpoints: list[DiscoveredEndpoint] = []
        dynamic_seen = False
        limited = False
        while queue:
            if len(visited) >= self._limits.max_html_responses:
                limited = bool(queue)
                break
            if self.urls_examined >= self._limits.max_urls_examined:
                limited = True
                break
            url, depth, method = queue.popleft()
            if url in visited or depth > self._limits.max_depth:
                continue
            visited.add(url)
            self.urls_examined += 1
            try:
                response = await self._get(url)
            except _LimitReached:
                limited = True
                break
            except _DiscoveryTransportError:
                continue
            if response.status_code >= 400:
                continue
            if len(response.content) > self._limits.max_html_bytes:
                limited = True
                continue
            body = response.text
            if _looks_dynamic(body):
                dynamic_seen = True
                continue
            ats = detect_ats(body)
            if ats is not None:
                endpoints.append(
                    DiscoveredEndpoint(
                        company_id=company_id,
                        seed_url=seed_url_raw,
                        discovered_url=str(response.url),
                        method=method,
                        fetched_at=fetched_at,
                        evidence_excerpt=_evidence_snippet(body, ats),
                        confidence_reason=f"ats_signature:{ats}",
                    )
                )
                return endpoints, limited, dynamic_seen
            if depth < self._limits.max_depth:
                for link in _extract_links(body, base=str(response.url)):
                    if _looks_relevant_page(link):
                        queue.append((normalize_discovery_url(link), depth + 1, "html_link"))
        return endpoints, limited, dynamic_seen


def record_limited_discovery_attempt(
    session: Session, outcome: DiscoveryOutcome, *, checked_url: str
) -> DiscoveryAttemptModel:
    """Persist one attempt so `companies.discovery.eligible_companies` will not repeat it
    before `next_attempt_at` (the same table F20-27 writes to; see module docstring)."""
    ats_found = None
    if outcome.endpoints:
        ats_found = endpoint_ats_name(outcome.endpoints[0])
    attempt = DiscoveryAttemptModel(
        company_id=outcome.company_id,
        checked_url=checked_url,
        http_status=200 if outcome.endpoints else None,
        ats_found=ats_found,
        stop_reason=outcome.stop_reason.value,
        urls_examined=outcome.urls_examined,
        http_requests=outcome.http_requests,
        next_attempt_at=outcome.next_attempt_at,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def upsert_ats_identified_source(
    session: Session, endpoint: DiscoveredEndpoint
) -> CompanySource:
    """A `CompanySource` for the discovered ATS; a second attempt over the same company
    and ATS updates the existing record's evidence history instead of duplicating it, so
    an already-inert proposal keeps pointing at one `CompanySource` (F20-36 criterion 4).
    """
    ats = endpoint_ats_name(endpoint)
    if ats is None:
        raise ValueError("endpoint has no recognizable ATS signature")
    canonical_endpoint = canonical_board_url(ats, endpoint.discovered_url)
    history_line = (
        f"{endpoint.fetched_at.isoformat()} discovery via {endpoint.method}: "
        f"{endpoint.evidence_excerpt}"
    )

    def _find_existing() -> CompanySource | None:
        return session.scalar(
            select(CompanySource).where(
                CompanySource.company_id == endpoint.company_id,
                CompanySource.source_type == ats,
            )
        )

    existing = _find_existing()
    if existing is not None:
        existing.endpoint = canonical_endpoint
        existing.last_verified_at = endpoint.fetched_at
        existing.evidence_note = (
            f"{existing.evidence_note}\n{history_line}" if existing.evidence_note else history_line
        )
        session.commit()
        session.refresh(existing)
        return existing
    source = CompanySource(
        company_id=endpoint.company_id,
        source_type=ats,
        endpoint=canonical_endpoint,
        verification_method="discovery",
        verification_status="ats_identified",
        evidence_note=history_line,
        last_verified_at=endpoint.fetched_at,
    )
    session.add(source)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent discovery run (parallel across hosts, F20-36 follow-up) inserted
        # the same (company, ATS) row first: fall back to updating it instead of failing
        # this company's whole discovery attempt (`uq_company_source_company_type_endpoint`).
        session.rollback()
        existing = _find_existing()
        if existing is None:
            raise
        existing.endpoint = canonical_endpoint
        existing.last_verified_at = endpoint.fetched_at
        existing.evidence_note = (
            f"{existing.evidence_note}\n{history_line}" if existing.evidence_note else history_line
        )
        session.commit()
        session.refresh(existing)
        return existing
    session.refresh(source)
    return source
