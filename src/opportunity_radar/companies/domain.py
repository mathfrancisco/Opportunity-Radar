"""Framework-free rules for Company Radar identity."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse


def normalize_name(value: str) -> str:
    """Return a comparison key while preserving the original display name elsewhere."""
    folded = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"\s+", " ", folded.casefold()).strip()


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().casefold()
    if "://" in candidate:
        candidate = urlparse(candidate).hostname or ""
    candidate = candidate.split("/", 1)[0].split(":", 1)[0].removeprefix("www.")
    candidate = candidate.rstrip(".")
    if not candidate or "." not in candidate or any(part == "" for part in candidate.split(".")):
        return None
    try:
        return candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None


@dataclass(frozen=True, slots=True)
class CompanyCandidate:
    name: str
    domain: str | None = None
    aliases: tuple[str, ...] = ()
    sources: tuple[CompanySourceCandidate, ...] = ()
    priority: str = "normal"

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.name)

    @property
    def normalized_domain(self) -> str | None:
        return normalize_domain(self.domain)

    @property
    def normalized_aliases(self) -> tuple[str, ...]:
        canonical = self.normalized_name
        return tuple(
            dict.fromkeys(
                normalized
                for alias in self.aliases
                if (normalized := normalize_name(alias)) and normalized != canonical
            )
        )


@dataclass(frozen=True, slots=True)
class CompanySourceCandidate:
    source_type: str
    endpoint: str


class AmbiguousCompanyIdentityError(ValueError):
    pass
