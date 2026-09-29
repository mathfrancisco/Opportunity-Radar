"""Startup evidence for a company (card F20-54, SPEC 45 section 5).

Evidence is appended, never overwritten: a company's strength is derived from every row,
so a weak sighting can never displace a strong one and repeated sightings accumulate for
audit. This is display/filter metadata — matching, score and verdict never read it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, get_args
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import CompanyStartupEvidence

StartupSignal = Literal["yc_batch", "seed_stage", "series_a", "other"]
StartupStrength = Literal["strong", "weak"]

SIGNALS: tuple[str, ...] = get_args(StartupSignal)
STRENGTHS: tuple[str, ...] = get_args(StartupStrength)


class InvalidStartupEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StartupSummary:
    #: `strong` when any row is strong, else `weak`. `None` for a company with no evidence.
    strength: str | None
    #: Batch of the most recent strong `yc_batch` row that names one.
    batch: str | None
    evidence_count: int


def summarize(evidence: Iterable[CompanyStartupEvidence]) -> StartupSummary:
    rows = sorted(evidence, key=lambda row: row.captured_at)
    if not rows:
        return StartupSummary(strength=None, batch=None, evidence_count=0)
    strong = [row for row in rows if row.strength == "strong"]
    batches = [row.batch for row in strong if row.signal == "yc_batch" and row.batch]
    return StartupSummary(
        strength="strong" if strong else "weak",
        batch=batches[-1] if batches else None,
        evidence_count=len(rows),
    )


def record_startup_evidence(
    session: Session,
    company_id: UUID,
    *,
    signal: str,
    strength: str,
    source_text: str,
    source_url: str | None = None,
    batch: str | None = None,
    captured_at: datetime | None = None,
) -> CompanyStartupEvidence:
    """Append one piece of evidence; an identical sighting returns the existing row."""
    if signal not in SIGNALS:
        raise InvalidStartupEvidenceError(f"unknown startup signal: {signal}")
    if strength not in STRENGTHS:
        raise InvalidStartupEvidenceError(f"unknown startup strength: {strength}")
    text = source_text.strip()
    if not text:
        raise InvalidStartupEvidenceError("startup evidence needs its source text")
    existing = session.scalar(
        select(CompanyStartupEvidence).where(
            CompanyStartupEvidence.company_id == company_id,
            CompanyStartupEvidence.signal == signal,
            CompanyStartupEvidence.strength == strength,
            CompanyStartupEvidence.source_text == text,
            CompanyStartupEvidence.source_url.is_(None)
            if source_url is None
            else CompanyStartupEvidence.source_url == source_url,
        )
    )
    if existing is not None:
        return existing
    row = CompanyStartupEvidence(
        company_id=company_id,
        signal=signal,
        strength=strength,
        source_text=text,
        source_url=source_url,
        batch=batch,
        captured_at=captured_at or datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def startup_evidence(session: Session, company_id: UUID) -> Sequence[CompanyStartupEvidence]:
    return session.scalars(
        select(CompanyStartupEvidence)
        .where(CompanyStartupEvidence.company_id == company_id)
        .order_by(CompanyStartupEvidence.captured_at, CompanyStartupEvidence.id)
    ).all()


_BRAND_CASED_YC = re.compile(r"\bYC\b")
_YC_WORD = re.compile(r"\bY[\s-]?Combinator\b", re.IGNORECASE)
_BATCH = re.compile(
    r"(?:\bYC\b|Y[\s-]?Combinator)[^.\n]{0,25}?\b([SWXF]\d{2}|[SW]20\d{2})\b",
    re.IGNORECASE,
)
_SERIES_A = re.compile(r"\bSeries\s+A\b", re.IGNORECASE)
_SEED = re.compile(r"\bseed[\s-]stage\b|\bseed\s+round\b|\bseed[\s-]funded\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DerivedStartupEvidence:
    signal: str
    strength: str
    source_text: str
    batch: str | None


def _snippet(text: str, start: int, end: int, radius: int = 90) -> str:
    left, right = max(0, start - radius), min(len(text), end + radius)
    return " ".join(text[left:right].split())


def derive_startup_evidence(
    *, strong_term: bool, term: str, excerpt: str | None
) -> DerivedStartupEvidence:
    """Turn a discovery signal into auditable evidence, from literal text only.

    A `strong_term` (brand term) is recorded strong/`yc_batch` only when the result text
    itself names Y Combinator/YC; the search term alone does not prove it (SPEC 45 pilot:
    recruiting agencies match brand queries), so it is stored weak/`other`. A weak (stage)
    term maps to `series_a`/`seed_stage` when the text says so, else `other`. The batch is
    read only when it follows the brand in the text (e.g. "YC S24").
    """
    text = excerpt or ""
    if strong_term:
        brand = _YC_WORD.search(text) or _BRAND_CASED_YC.search(text)
        if brand is not None:
            batch = _BATCH.search(text)
            return DerivedStartupEvidence(
                "yc_batch",
                "strong",
                _snippet(text, brand.start(), brand.end()),
                batch.group(1).upper() if batch else None,
            )
        return DerivedStartupEvidence(
            "other", "weak", f"busca por {term}; o texto do resultado não cita a marca", None
        )
    for signal, pattern in (("series_a", _SERIES_A), ("seed_stage", _SEED)):
        found = pattern.search(text)
        if found is not None:
            return DerivedStartupEvidence(
                signal, "weak", _snippet(text, found.start(), found.end()), None
            )
    return DerivedStartupEvidence(
        "other", "weak", f"busca por {term}; o texto do resultado não cita o estágio", None
    )
