"""What the semantic analysis costs, how often it fails and how far behind it is.

Read from the costs each analysis row records (F16-03), in the same two windows as the
per-source metrics. A window crosses model changes, so every aggregate is grouped by
`model_id`: a p95 that mixes two models describes neither. A window with nothing to
measure answers `None`, never zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.metrics import METRIC_WINDOWS
from opportunity_radar.matching.models import MatchAnalysisModel

_COMPLETED = "AI_COMPLETED"
_FAILED = "AI_FAILED"


@dataclass(frozen=True, slots=True)
class ModelAnalysisMetrics:
    model_id: str | None
    analyses: int
    completed: int
    failed: int
    total_ms_p50: float | None
    total_ms_p95: float | None
    total_ms_p99: float | None
    prompt_tokens_avg: float | None
    output_tokens_avg: float | None
    load_ms_avg: float | None
    reused: int
    failures_by_code: dict[str, int] = field(default_factory=dict)

    @property
    def failure_rate(self) -> float | None:
        return self.failed / self.analyses if self.analyses else None

    @property
    def failure_rates(self) -> dict[str, float]:
        if not self.analyses:
            return {}
        return {code: total / self.analyses for code, total in self.failures_by_code.items()}

    @property
    def reuse_rate(self) -> float | None:
        """A completed row with no cost never reached the model: it came from the cache."""
        return self.reused / self.completed if self.completed else None


@dataclass(frozen=True, slots=True)
class AnalysisMetricsWindow:
    window: str
    since: datetime
    until: datetime
    models: tuple[ModelAnalysisMetrics, ...]

    def for_model(self, model_id: str) -> ModelAnalysisMetrics | None:
        return next((item for item in self.models if item.model_id == model_id), None)


@dataclass(frozen=True, slots=True)
class AnalysisMetricsReport:
    generated_at: datetime
    current_model: str
    pending: int
    windows: tuple[AnalysisMetricsWindow, ...]


def analysis_metrics(
    session: Session,
    *,
    current_model: str,
    pending: int,
    now: datetime | None = None,
    windows: dict[str, timedelta] | None = None,
) -> AnalysisMetricsReport:
    """`pending` comes from the caller, which knows the queue's configured budget."""
    reference = now or datetime.now(UTC)
    selected = windows or METRIC_WINDOWS
    return AnalysisMetricsReport(
        generated_at=reference,
        current_model=current_model,
        pending=pending,
        windows=tuple(
            _window(session, label, reference - span, reference)
            for label, span in selected.items()
        ),
    )


def _window(
    session: Session, label: str, since: datetime, until: datetime
) -> AnalysisMetricsWindow:
    failures = _failures_by_code(session, since, until)
    return AnalysisMetricsWindow(
        window=label,
        since=since,
        until=until,
        models=tuple(
            _model_metrics(row, failures.get(row.model_id, {}))
            for row in _aggregates(session, since, until)
        ),
    )


def _in_window(since: datetime, until: datetime) -> tuple[Any, ...]:
    return (
        MatchAnalysisModel.analyzed_at >= since,
        MatchAnalysisModel.analyzed_at <= until,
    )


def _aggregates(session: Session, since: datetime, until: datetime) -> list[Any]:
    # Aggregates skip nulls, so rows with no recorded cost never pull a percentile down.
    total_ms = MatchAnalysisModel.total_ms
    return list(
        session.execute(
            select(
                MatchAnalysisModel.model_id.label("model_id"),
                func.count().label("analyses"),
                func.count().filter(MatchAnalysisModel.status == _COMPLETED).label("completed"),
                func.count().filter(MatchAnalysisModel.status == _FAILED).label("failed"),
                func.count()
                .filter(MatchAnalysisModel.status == _COMPLETED, total_ms.is_(None))
                .label("reused"),
                func.percentile_cont(0.5).within_group(total_ms).label("p50"),
                func.percentile_cont(0.95).within_group(total_ms).label("p95"),
                func.percentile_cont(0.99).within_group(total_ms).label("p99"),
                func.avg(MatchAnalysisModel.prompt_tokens).label("prompt_tokens"),
                func.avg(MatchAnalysisModel.output_tokens).label("output_tokens"),
                func.avg(MatchAnalysisModel.load_ms).label("load_ms"),
            )
            .where(*_in_window(since, until))
            .group_by(MatchAnalysisModel.model_id)
            .order_by(func.count().desc(), MatchAnalysisModel.model_id)
        ).all()
    )


def _failures_by_code(
    session: Session, since: datetime, until: datetime
) -> dict[str | None, dict[str, int]]:
    rows = session.execute(
        select(
            MatchAnalysisModel.model_id,
            MatchAnalysisModel.failure_code,
            func.count(),
        )
        .where(
            *_in_window(since, until),
            MatchAnalysisModel.status == _FAILED,
            MatchAnalysisModel.failure_code.is_not(None),
        )
        .group_by(MatchAnalysisModel.model_id, MatchAnalysisModel.failure_code)
    ).all()
    result: dict[str | None, dict[str, int]] = {}
    for model_id, code, total in rows:
        result.setdefault(model_id, {})[code] = total
    return result


def _optional(value: Any) -> float | None:
    return None if value is None else float(value)


def _model_metrics(row: Any, failures: dict[str, int]) -> ModelAnalysisMetrics:
    return ModelAnalysisMetrics(
        model_id=row.model_id,
        analyses=row.analyses,
        completed=row.completed,
        failed=row.failed,
        total_ms_p50=_optional(row.p50),
        total_ms_p95=_optional(row.p95),
        total_ms_p99=_optional(row.p99),
        prompt_tokens_avg=_optional(row.prompt_tokens),
        output_tokens_avg=_optional(row.output_tokens),
        load_ms_avg=_optional(row.load_ms),
        reused=row.reused,
        failures_by_code=failures,
    )


__all__ = [
    "AnalysisMetricsReport",
    "AnalysisMetricsWindow",
    "ModelAnalysisMetrics",
    "analysis_metrics",
]
