"""The one list of platforms the project must never collect from (SPEC 48 sections 1.2, 4.15).

Every route that can create or propose a source (`create_source`, Tavily/HN proposals,
`propose_company_source`, the research importers) and the funnel's guard read this module;
nothing keeps a private copy of the hosts.

Most entries are here for a legal or terms reason. Braintrust is the exception (decision 8):
it is excluded only because it has no structured endpoint (F20-56); it may re-enter with a
structured endpoint and its own terms review.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from opportunity_radar.acquisition.domain import AcquisitionError, AcquisitionErrorCode


@dataclass(frozen=True, slots=True)
class ForbiddenPlatform:
    name: str
    #: Host patterns, optionally with a path prefix ("www.ycombinator.com/jobs"). A host
    #: matches itself and its subdomains; a path prefix restricts the match to that path.
    hosts: tuple[str, ...]
    reason: str


FORBIDDEN_PLATFORMS: tuple[ForbiddenPlatform, ...] = (
    ForbiddenPlatform("Gupy", ("gupy.io",), "termos da plataforma proíbem agregação (F20-32)"),
    ForbiddenPlatform(
        "Wellfound", ("wellfound.com",), "termos proíbem coleta automatizada (F20-51)"
    ),
    ForbiddenPlatform(
        "YC / Work at a Startup",
        ("workatastartup.com", "www.ycombinator.com/jobs"),
        "termos proíbem coleta automatizada (F20-52)",
    ),
    ForbiddenPlatform("Careerflow", ("careerflow.ai",), "termos proíbem coleta automatizada"),
    ForbiddenPlatform("Crossover", ("crossover.com",), "termos proíbem coleta automatizada"),
    ForbiddenPlatform(
        "Braintrust",
        ("usebraintrust.com",),
        "sem endpoint estruturado (F20-56)",
    ),
    ForbiddenPlatform(
        "Landing.jobs", ("landing.jobs",), "termos proíbem coleta automatizada"
    ),
)

#: Every host pattern, for substring scans (the funnel guard counts rows that mention one).
FORBIDDEN_HOST_PATTERNS: tuple[str, ...] = tuple(
    host for platform in FORBIDDEN_PLATFORMS for host in platform.hosts
)
#: Bare hosts (no path prefix): what a search must never be pointed at.
FORBIDDEN_HOST_NAMES: frozenset[str] = frozenset(
    host for host in FORBIDDEN_HOST_PATTERNS if "/" not in host
)

_HOSTLIKE = re.compile(r"(?<![a-z0-9.-])((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s\"'<>]*)?")


def _matches(host: str, path: str, pattern: str) -> bool:
    pattern_host, _, pattern_path = pattern.partition("/")
    if host != pattern_host and not host.endswith(f".{pattern_host}"):
        return False
    return not pattern_path or (path + "/").startswith(f"/{pattern_path}/")


def forbidden_platform_for_host(host: str, path: str = "") -> ForbiddenPlatform | None:
    normalized_host = host.strip().casefold().rstrip(".")
    normalized_path = path.casefold()
    for platform in FORBIDDEN_PLATFORMS:
        if any(_matches(normalized_host, normalized_path, p) for p in platform.hosts):
            return platform
    return None


def forbidden_platform_for_url(url: str) -> ForbiddenPlatform | None:
    """The forbidden platform a URL (or bare `host/path`) points to, if any."""
    text = url.strip()
    if not text:
        return None
    parts = urlsplit(text if "://" in text else f"//{text}")
    return forbidden_platform_for_host(parts.hostname or "", parts.path)


def is_forbidden_url(url: str) -> bool:
    return forbidden_platform_for_url(url) is not None


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _strings(item)


def forbidden_platform_in(value: Any) -> ForbiddenPlatform | None:
    """A forbidden platform named by any host-like token in any string inside `value`."""
    for text in _strings(value):
        for match in _HOSTLIKE.finditer(text.casefold()):
            platform = forbidden_platform_for_host(match.group(1), match.group(2) or "")
            if platform is not None:
                return platform
    return None


def refusal(platform: ForbiddenPlatform, *, field: str | None = None) -> AcquisitionError:
    return AcquisitionError(
        AcquisitionErrorCode.INVALID_CONFIGURATION,
        f"{platform.name} is on the forbidden platform list: {platform.reason}",
        field=field,
    )


def refuse_forbidden(value: Any, *, field: str | None = None) -> None:
    """Raise when anything inside `value` (a URL, a configuration mapping) is forbidden."""
    platform = forbidden_platform_in(value)
    if platform is not None:
        raise refusal(platform, field=field)


__all__ = [
    "FORBIDDEN_HOST_NAMES",
    "FORBIDDEN_HOST_PATTERNS",
    "FORBIDDEN_PLATFORMS",
    "ForbiddenPlatform",
    "forbidden_platform_for_host",
    "forbidden_platform_for_url",
    "forbidden_platform_in",
    "is_forbidden_url",
    "refuse_forbidden",
    "refusal",
]
