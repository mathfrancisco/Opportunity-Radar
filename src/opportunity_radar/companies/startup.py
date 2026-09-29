"""Startup evidence for a company (card F20-54, SPEC 45 section 5).

Evidence is appended, never overwritten: a company's strength is derived from every row,
so a weak sighting can never displace a strong one and repeated sightings accumulate for
audit. This is display/filter metadata — matching, score and verdict never read it.
"""

from __future__ import annotations

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
