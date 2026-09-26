"""Zero postings, a source that never ran and a blocked source must not look alike."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard.metrics import (
    METRIC_WINDOWS,
    SourceWindowMetrics,
    duplicate_rate_report,
    source_metrics,
)
from opportunity_radar.opportunities.domain import SENIORITY_MAPPING_VERSION
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _source(
    session: Session,
    *,
    enabled: bool = True,
    homologated: bool = True,
    schedule: str | None = "* * * * *",
) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="greenhouse",
        name=f"metrics {uuid4().hex[:8]}",
        enabled=enabled,
        schedule=schedule,
        configuration={"board_token": "metrics"},
        rate_limit_policy={},
        evidence_status="confirmed" if homologated else "unverified",
        reviewed_at=NOW if homologated else None,
        terms_reviewed=homologated,
        collector_local_tested=homologated,
    )
    session.add(source)
    session.flush()
    return source


def _run(
    session: Session,
    source: SourceDefinitionModel,
    *,
    status: str,
    started_at: datetime,
    duration_seconds: float = 1.0,
    items_seen: int = 0,
    items_persisted: int = 0,
    items_skipped: int = 0,
    error_code: str | None = None,
) -> SourceRunModel:
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="SCHEDULED",
        status=status,
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=duration_seconds),
        items_seen=items_seen,
        items_persisted=items_persisted,
        items_skipped=items_skipped,
        error_code=error_code,
        error_summary="probe" if error_code else None,
    )
    session.add(run)
    session.flush()
    return run


def _normalized_posting(
    session: Session,
    source: SourceDefinitionModel,
    run: SourceRunModel,
    *,
    seniority: str,
    evidence: str,
    processed_at: datetime,
) -> None:
    marker = uuid4().hex[:12]
    company = Company(
        canonical_name=f"Metrics {marker}",
        normalized_name=f"metrics-{marker}",
        priority="normal",
    )
    session.add(company)
    session.flush()
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=marker,
        identity_key=f"external:{marker}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    raw_item.payload_record = RawItemPayloadModel(payload={"title": "Probe"})
    session.add(raw_item)
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title="Probe role",
        normalized_title="probe role",
        canonical_company_id=company.id,
        company_name=company.canonical_name,
        work_mode="REMOTE",
        seniority=seniority,
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        version=1,
    )
    session.add(opportunity)
    session.flush()
    occurrence = SourceOccurrenceModel(
        opportunity_id=opportunity.id,
        raw_item_id=raw_item.id,
        source_definition_id=source.id,
        external_id=marker,
    )
    session.add(occurrence)
    session.flush()
    session.add(
        NormalizationResultModel(
            raw_item_id=raw_item.id,
            opportunity_id=opportunity.id,
            source_occurrence_id=occurrence.id,
            status="SUCCEEDED",
            normalizer_version="v3",
            identity_decision="NEW",
            reasons=[
                {
                    "code": "SENIORITY_CLASSIFICATION",
                    "source": evidence,
                    "external_value": None,
                    "mapping_version": SENIORITY_MAPPING_VERSION,
                    "collector": source.source_type,
                    "value": seniority,
                }
            ],
            processed_at=processed_at,
        )
    )
    session.flush()


def _metrics_for(
    session: Session, source_id: object, window: str
) -> SourceWindowMetrics:
    report = source_metrics(session, now=NOW)
    selected = next(item for item in report.windows if item.window == window)
    return next(
        item for item in selected.sources if item.source_definition_id == source_id
    )


def test_both_windows_are_answered() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        report = source_metrics(session, now=NOW)

        assert [item.window for item in report.windows] == list(METRIC_WINDOWS)
        for item in report.windows:
            assert item.until == NOW
            assert item.since < item.until


def test_coverage_separates_an_empty_success_from_a_source_that_did_not_run() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        empty = _source(session)
        idle = _source(session)
        blocked = _source(session, homologated=False)
        disabled = _source(session, enabled=False)
        unscheduled = _source(session, schedule=None)
        _run(session, empty, status="SUCCEEDED", started_at=NOW - timedelta(minutes=5))
        session.commit()

        assert _metrics_for(session, empty.id, "24h").coverage_state == "SUCCEEDED_ZERO"
        assert _metrics_for(session, idle.id, "24h").coverage_state == "NOT_RUN"
        assert (
            _metrics_for(session, blocked.id, "24h").coverage_state
            == "CONFIGURATION_BLOCKED"
        )
        assert _metrics_for(session, disabled.id, "24h").coverage_state == "NOT_ENABLED"
        assert (
            _metrics_for(session, unscheduled.id, "24h").coverage_state
            == "NOT_SCHEDULED"
        )


def test_rates_are_absent_rather_than_zero_without_runs() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        idle = _source(session)
        session.commit()

        metrics = _metrics_for(session, idle.id, "24h")

        assert metrics.has_runs is False
        assert metrics.error_rate is None
        assert metrics.dedupe_rate is None
        assert metrics.latency_p95_seconds is None


def test_errors_are_segmented_by_code_and_rates_are_computed() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        _run(
            session,
            source,
            status="SUCCEEDED",
            started_at=NOW - timedelta(minutes=30),
            duration_seconds=2,
            items_seen=10,
            items_persisted=6,
            items_skipped=4,
        )
        _run(
            session,
            source,
            status="FAILED",
            started_at=NOW - timedelta(minutes=20),
            error_code="SOURCE_SERVER_ERROR",
        )
        _run(
            session,
            source,
            status="FAILED",
            started_at=NOW - timedelta(minutes=10),
            error_code="SOURCE_RATE_LIMITED",
        )
        session.commit()

        metrics = _metrics_for(session, source.id, "24h")

        assert metrics.runs == 3
        assert metrics.runs_failed == 2
        assert metrics.error_rate == pytest.approx(2 / 3)
        assert metrics.dedupe_rate == pytest.approx(0.4)
        assert metrics.latency_p95_seconds is not None
        assert metrics.errors_by_code == {
            "SOURCE_SERVER_ERROR": 1,
            "SOURCE_RATE_LIMITED": 1,
        }
        assert metrics.coverage_state == "FAILED"


def test_the_window_excludes_older_runs() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        _run(session, source, status="SUCCEEDED", started_at=NOW - timedelta(days=3))
        session.commit()

        assert _metrics_for(session, source.id, "24h").runs == 0
        assert _metrics_for(session, source.id, "7d").runs == 1


def test_unknown_seniority_is_reported_with_its_provenance() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        run = _run(
            session,
            source,
            status="SUCCEEDED",
            started_at=NOW - timedelta(minutes=5),
            items_seen=3,
            items_persisted=3,
        )
        for seniority, evidence in (
            ("SENIOR", "title"),
            ("UNKNOWN", "conflict"),
            ("UNKNOWN", "title"),
        ):
            _normalized_posting(
                session,
                source,
                run,
                seniority=seniority,
                evidence=evidence,
                processed_at=NOW - timedelta(minutes=4),
            )
        session.commit()

        seniority_metrics = _metrics_for(session, source.id, "24h").seniority

        assert seniority_metrics.total == 3
        assert seniority_metrics.unknown == 2
        assert seniority_metrics.known == 1
        assert seniority_metrics.counts["SENIOR"] == 1
        assert seniority_metrics.percentages["UNKNOWN"] == pytest.approx(66.67, abs=0.01)
        assert seniority_metrics.mapping_versions == {SENIORITY_MAPPING_VERSION: 3}
        assert seniority_metrics.evidence == {"title": 2, "conflict": 1}


def test_duplicate_rate_reported_before_and_after() -> None:
    """F20-26: the same report, called before and after a confirm, shows the rate move."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        marker = uuid4().hex[:8]
        survivor = OpportunityModel(
            fingerprint=uuid4().hex + uuid4().hex,
            fingerprint_version="v1",
            canonical_title=f"Backend Engineer {marker}",
            normalized_title="backend engineer",
            work_mode="UNKNOWN",
            seniority="UNKNOWN",
            contract_type="UNKNOWN",
            lifecycle_status="ACTIVE",
            version=1,
        )
        duplicate = OpportunityModel(
            fingerprint=uuid4().hex + uuid4().hex,
            fingerprint_version="v1",
            canonical_title=f"Backend Engineer {marker} 2",
            normalized_title="backend engineer",
            work_mode="UNKNOWN",
            seniority="UNKNOWN",
            contract_type="UNKNOWN",
            lifecycle_status="ACTIVE",
            version=1,
        )
        session.add_all([survivor, duplicate])
        session.commit()
        try:
            before = duplicate_rate_report(session)
            assert before.duplicate_of_count == 0

            duplicate.duplicate_of = survivor.id
            session.commit()

            after = duplicate_rate_report(session)
            assert after.duplicate_of_count == before.duplicate_of_count + 1
            assert after.total_opportunities == before.total_opportunities
            assert after.duplicate_rate is not None
            assert after.duplicate_rate > (before.duplicate_rate or 0)
        finally:
            duplicate.duplicate_of = None
            session.commit()
            session.execute(
                delete(OpportunityModel).where(
                    OpportunityModel.id.in_([survivor.id, duplicate.id])
                )
            )
            session.commit()
