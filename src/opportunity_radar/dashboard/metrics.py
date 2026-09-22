"""Per-source operational metrics over the last 24 hours and the last seven days.

Two questions this answers that a run list cannot. First, a source that returned nothing
is not a source that did not run: both look like zero postings, and only one of them is a
problem, so coverage is reported as an explicit state rather than inferred from a count.
Second, a distribution concentrated in `SENIOR` proves nothing while `UNKNOWN` is large —
the unknown share is therefore always carried next to the known one, with the version of
the mapping that produced it, and is never folded into a level.

Everything here is derived from persisted runs and occurrences. Logs rotate and are not
queryable per source, so a metric that could only come from them is a metric this module
deliberately does not offer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Float, column, extract, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    SourceAlertIncidentModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.opportunities.domain import SENIORITY_MAPPING_VERSION
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)

#: The two windows the Overview and the API both answer for.
METRIC_WINDOWS: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}

SENIORITY_REASON_CODE = "SENIORITY_CLASSIFICATION"
UNKNOWN_SENIORITY = "UNKNOWN"

#: Runs that have not decided anything yet are excluded from every rate.
_UNFINISHED = ("PENDING", "RUNNING")


@dataclass(frozen=True, slots=True)
class SeniorityDistribution:
    """Counts, shares and where the level came from — never a level on its own."""

    counts: dict[str, int] = field(default_factory=dict)
    percentages: dict[str, float] = field(default_factory=dict)
    mapping_versions: dict[str, int] = field(default_factory=dict)
    evidence: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def unknown(self) -> int:
        return self.counts.get(UNKNOWN_SENIORITY, 0)

    @property
    def known(self) -> int:
        return self.total - self.unknown


@dataclass(frozen=True, slots=True)
class SourceWindowMetrics:
    source_definition_id: UUID
    name: str
    source_type: str
    enabled: bool
    schedule: str | None
    coverage_state: str
    runs: int
    runs_succeeded: int
    runs_partial: int
    runs_failed: int
    items_seen: int
    items_persisted: int
    items_skipped: int
    items_invalid: int
    latency_p95_seconds: float | None
    errors_by_code: dict[str, int] = field(default_factory=dict)
    seniority: SeniorityDistribution = field(default_factory=SeniorityDistribution)
    incident_open: bool = False

    @property
    def has_runs(self) -> bool:
        """Whether any rate below is backed by data. Zero runs is reported, not zeroed."""
        return self.runs > 0

    @property
    def error_rate(self) -> float | None:
        return None if not self.has_runs else self.runs_failed / self.runs

    @property
    def dedupe_rate(self) -> float | None:
        """Share of collected items already held. Undefined when nothing was collected."""
        return None if self.items_seen == 0 else self.items_skipped / self.items_seen


@dataclass(frozen=True, slots=True)
class SourceMetricsWindow:
    window: str
    since: datetime
    until: datetime
    sources: tuple[SourceWindowMetrics, ...]


@dataclass(frozen=True, slots=True)
class SourceMetricsReport:
    generated_at: datetime
    windows: tuple[SourceMetricsWindow, ...]


def source_metrics(
    session: Session,
    *,
    now: datetime | None = None,
    windows: dict[str, timedelta] | None = None,
) -> SourceMetricsReport:
    reference = now or datetime.now(UTC)
    selected = windows or METRIC_WINDOWS
    sources = list(
        session.scalars(
            select(SourceDefinitionModel).order_by(SourceDefinitionModel.name)
        )
    )
    open_incidents = set(
        session.scalars(
            select(SourceAlertIncidentModel.source_definition_id).where(
                SourceAlertIncidentModel.recovered_at.is_(None)
            )
        )
    )
    return SourceMetricsReport(
        generated_at=reference,
        windows=tuple(
            _window(session, sources, open_incidents, label, reference - span, reference)
            for label, span in selected.items()
        ),
    )


def _window(
    session: Session,
    sources: list[SourceDefinitionModel],
    open_incidents: set[UUID],
    label: str,
    since: datetime,
    until: datetime,
) -> SourceMetricsWindow:
    runs = _run_aggregates(session, since)
    errors = _errors_by_code(session, since)
    latest = _latest_run_in_window(session, since)
    seniority = _seniority_by_source(session, since)
    return SourceMetricsWindow(
        window=label,
        since=since,
        until=until,
        sources=tuple(
            _source_metrics(
                source,
                runs.get(source.id),
                errors.get(source.id, {}),
                latest.get(source.id),
                seniority.get(source.id, SeniorityDistribution()),
                source.id in open_incidents,
            )
            for source in sources
        ),
    )


def _source_metrics(
    source: SourceDefinitionModel,
    aggregate: Any,
    errors: dict[str, int],
    latest: Any,
    seniority: SeniorityDistribution,
    incident_open: bool,
) -> SourceWindowMetrics:
    return SourceWindowMetrics(
        source_definition_id=source.id,
        name=source.name,
        source_type=source.source_type,
        enabled=source.enabled,
        schedule=source.schedule,
        coverage_state=_coverage_state(source, latest),
        runs=int(aggregate.runs) if aggregate else 0,
        runs_succeeded=int(aggregate.succeeded) if aggregate else 0,
        runs_partial=int(aggregate.partial) if aggregate else 0,
        runs_failed=int(aggregate.failed) if aggregate else 0,
        items_seen=int(aggregate.items_seen or 0) if aggregate else 0,
        items_persisted=int(aggregate.items_persisted or 0) if aggregate else 0,
        items_skipped=int(aggregate.items_skipped or 0) if aggregate else 0,
        items_invalid=int(aggregate.items_invalid or 0) if aggregate else 0,
        latency_p95_seconds=(
            float(aggregate.latency_p95)
            if aggregate and aggregate.latency_p95 is not None
            else None
        ),
        errors_by_code=errors,
        seniority=seniority,
        incident_open=incident_open,
    )


def _coverage_state(source: SourceDefinitionModel, latest: Any) -> str:
    """Why this source produced what it produced, before any count is read.

    The order matters: a disabled source has no schedule to miss, and a source blocked on
    homologation never reached its schedule either. Only once neither explains the silence
    is an absent run reported as a source that should have run and did not.
    """
    if not source.enabled:
        return "NOT_ENABLED"
    if source.source_type != "manual" and not (
        source.evidence_status == "confirmed"
        and source.reviewed_at is not None
        and source.terms_reviewed
        and source.collector_local_tested
    ):
        return "CONFIGURATION_BLOCKED"
    if source.source_type != "manual" and not source.schedule:
        return "NOT_SCHEDULED"
    if latest is None:
        return "NOT_RUN"
    if latest.status == "SUCCEEDED" and (latest.items_seen or 0) == 0:
        return "SUCCEEDED_ZERO"
    return str(latest.status)


def _run_aggregates(session: Session, since: datetime) -> dict[UUID, Any]:
    duration = extract(
        "epoch", SourceRunModel.finished_at - SourceRunModel.started_at
    ).cast(Float)
    rows = session.execute(
        select(
            SourceRunModel.source_definition_id.label("source_definition_id"),
            func.count().label("runs"),
            func.count()
            .filter(SourceRunModel.status == "SUCCEEDED")
            .label("succeeded"),
            func.count().filter(SourceRunModel.status == "PARTIAL").label("partial"),
            func.count().filter(SourceRunModel.status == "FAILED").label("failed"),
            func.sum(SourceRunModel.items_seen).label("items_seen"),
            func.sum(SourceRunModel.items_persisted).label("items_persisted"),
            func.sum(SourceRunModel.items_skipped).label("items_skipped"),
            func.sum(SourceRunModel.items_invalid).label("items_invalid"),
            func.percentile_cont(0.95)
            .within_group(duration)
            .label("latency_p95"),
        )
        .where(
            SourceRunModel.started_at >= since,
            SourceRunModel.status.not_in(_UNFINISHED),
        )
        .group_by(SourceRunModel.source_definition_id)
    ).all()
    return {row.source_definition_id: row for row in rows}


def _errors_by_code(session: Session, since: datetime) -> dict[UUID, dict[str, int]]:
    rows = session.execute(
        select(
            SourceRunModel.source_definition_id,
            SourceRunModel.error_code,
            func.count(),
        )
        .where(
            SourceRunModel.started_at >= since,
            SourceRunModel.error_code.is_not(None),
        )
        .group_by(SourceRunModel.source_definition_id, SourceRunModel.error_code)
    ).all()
    by_source: dict[UUID, dict[str, int]] = {}
    for source_id, error_code, total in rows:
        by_source.setdefault(source_id, {})[str(error_code)] = int(total)
    return by_source


def _latest_run_in_window(session: Session, since: datetime) -> dict[UUID, Any]:
    ranked = (
        select(
            SourceRunModel.source_definition_id.label("source_definition_id"),
            SourceRunModel.status.label("status"),
            SourceRunModel.items_seen.label("items_seen"),
            func.row_number()
            .over(
                partition_by=SourceRunModel.source_definition_id,
                order_by=(
                    func.coalesce(
                        SourceRunModel.finished_at, SourceRunModel.started_at
                    ).desc(),
                    SourceRunModel.id.desc(),
                ),
            )
            .label("position"),
        )
        .where(
            SourceRunModel.started_at >= since,
            SourceRunModel.status.not_in(_UNFINISHED),
        )
        .subquery("ranked_window_runs")
    )
    rows = session.execute(select(ranked).where(ranked.c.position == 1)).all()
    return {row.source_definition_id: row for row in rows}


def _seniority_by_source(
    session: Session, since: datetime
) -> dict[UUID, SeniorityDistribution]:
    """Levels and their provenance, read from the normalization that decided them."""
    counts: dict[UUID, dict[str, int]] = {}
    for source_id, level, total in session.execute(
        select(
            SourceOccurrenceModel.source_definition_id,
            OpportunityModel.seniority,
            func.count(),
        )
        .join(
            OpportunityModel,
            OpportunityModel.id == SourceOccurrenceModel.opportunity_id,
        )
        .join(
            NormalizationResultModel,
            NormalizationResultModel.source_occurrence_id == SourceOccurrenceModel.id,
        )
        .where(NormalizationResultModel.processed_at >= since)
        .group_by(
            SourceOccurrenceModel.source_definition_id, OpportunityModel.seniority
        )
    ).all():
        counts.setdefault(source_id, {})[str(level)] = int(total)

    reason = (
        func.jsonb_array_elements(NormalizationResultModel.reasons)
        .table_valued(column("value", JSONB))
        .lateral("seniority_reason")
    )
    # The JSON extractions are projected once and grouped over the projection: repeating
    # them in GROUP BY would emit a second, separately-bound expression that PostgreSQL
    # cannot match against the first.
    extracted = (
        select(
            SourceOccurrenceModel.source_definition_id.label("source_definition_id"),
            reason.c.value["mapping_version"].astext.label("mapping_version"),
            reason.c.value["source"].astext.label("evidence"),
            reason.c.value["code"].astext.label("code"),
        )
        .select_from(SourceOccurrenceModel)
        .join(
            NormalizationResultModel,
            NormalizationResultModel.source_occurrence_id == SourceOccurrenceModel.id,
        )
        .join(reason, literal(True))
        .where(NormalizationResultModel.processed_at >= since)
        .subquery("seniority_reasons")
    )
    mapping_versions: dict[UUID, dict[str, int]] = {}
    evidence: dict[UUID, dict[str, int]] = {}
    for source_id, version, origin, total in session.execute(
        select(
            extracted.c.source_definition_id,
            extracted.c.mapping_version,
            extracted.c.evidence,
            func.count(),
        )
        .where(extracted.c.code == SENIORITY_REASON_CODE)
        .group_by(
            extracted.c.source_definition_id,
            extracted.c.mapping_version,
            extracted.c.evidence,
        )
    ).all():
        # One row per (version, evidence) pair, so both dimensions accumulate rather
        # than overwrite: a mapping version used by two kinds of evidence is one version.
        versions = mapping_versions.setdefault(source_id, {})
        key = str(version or SENIORITY_MAPPING_VERSION)
        versions[key] = versions.get(key, 0) + int(total)
        origins = evidence.setdefault(source_id, {})
        origin_key = str(origin or "unknown")
        origins[origin_key] = origins.get(origin_key, 0) + int(total)

    distributions: dict[UUID, SeniorityDistribution] = {}
    for source_id, levels in counts.items():
        total = sum(levels.values())
        distributions[source_id] = SeniorityDistribution(
            counts=levels,
            percentages={
                level: round(count * 100 / total, 2) for level, count in levels.items()
            }
            if total
            else {},
            mapping_versions=mapping_versions.get(source_id, {}),
            evidence=evidence.get(source_id, {}),
        )
    return distributions


__all__ = [
    "METRIC_WINDOWS",
    "SENIORITY_REASON_CODE",
    "UNKNOWN_SENIORITY",
    "SeniorityDistribution",
    "SourceMetricsReport",
    "SourceMetricsWindow",
    "SourceWindowMetrics",
    "source_metrics",
]
