"""One message per incident, one recovery per repair, and collection that ignores both."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.alerts import (
    FAILED,
    LOG_ONLY,
    WEBHOOK,
    SourceAlertService,
)
from opportunity_radar.acquisition.models import (
    SourceAlertIncidentModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _RecordingNotifier:
    def __init__(self, *, accepts: bool = True) -> None:
        self.accepts = accepts
        self.messages: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> bool:
        self.messages.append(message)
        return self.accepts


class _RaisingNotifier:
    def send(self, message: dict[str, Any]) -> bool:
        raise RuntimeError("the channel is unreachable")


def _source(session: Session) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="manual",
        name=f"alert probe {uuid4().hex[:8]}",
        enabled=True,
        configuration={},
        rate_limit_policy={},
    )
    session.add(source)
    session.commit()
    return source


def _run(
    session: Session,
    source: SourceDefinitionModel,
    status: str,
    *,
    finished_at: datetime | None = None,
) -> SourceRunModel:
    moment = finished_at or datetime.now(UTC)
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="SCHEDULED",
        status=status,
        started_at=moment - timedelta(seconds=1),
        finished_at=moment,
        error_code="UNKNOWN_EXTERNAL_ERROR" if status == "FAILED" else None,
        error_summary="probe failure" if status == "FAILED" else None,
        correlation_id="alert-probe",
    )
    session.add(run)
    session.commit()
    return run


def _incidents(session: Session, source_id: Any) -> list[SourceAlertIncidentModel]:
    return list(
        session.scalars(
            select(SourceAlertIncidentModel)
            .where(SourceAlertIncidentModel.source_definition_id == source_id)
            .order_by(SourceAlertIncidentModel.opened_at)
        )
    )


def _cleanup(session: Session, source: SourceDefinitionModel) -> None:
    session.execute(
        delete(SourceAlertIncidentModel).where(
            SourceAlertIncidentModel.source_definition_id == source.id
        )
    )
    session.execute(
        delete(SourceRunModel).where(SourceRunModel.source_definition_id == source.id)
    )
    session.execute(
        delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id)
    )
    session.commit()


def test_an_incident_is_announced_once_and_recovers_once() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    notifier = _RecordingNotifier()
    with Session(engine) as session:
        source = _source(session)
        service = SourceAlertService(session, notifier=notifier, threshold=3)
        try:
            for streak in (1, 2):
                run = _run(session, source, "FAILED")
                assert (
                    service.record_run_outcome(
                        source, run, consecutive_failures=streak
                    )
                    is None
                )
            assert notifier.messages == []

            third = _run(session, source, "FAILED")
            opened = service.record_run_outcome(source, third, consecutive_failures=3)
            assert opened is not None
            assert opened.alert_delivery == WEBHOOK
            assert opened.alert_sent_at is not None
            assert len(notifier.messages) == 1
            assert notifier.messages[0]["event"] == "source_alert"

            fourth = _run(session, source, "FAILED")
            assert (
                service.record_run_outcome(source, fourth, consecutive_failures=4) is None
            )
            assert len(notifier.messages) == 1

            success = _run(session, source, "SUCCEEDED")
            recovered = service.record_run_outcome(
                source, success, consecutive_failures=0
            )
            assert recovered is not None
            assert recovered.id == opened.id
            assert recovered.recovered_at is not None
            assert recovered.recovery_delivery == WEBHOOK
            assert [message["event"] for message in notifier.messages] == [
                "source_alert",
                "source_recovery",
            ]

            reopened = service.record_run_outcome(
                source, _run(session, source, "FAILED"), consecutive_failures=3
            )
            assert reopened is not None
            assert reopened.id != opened.id
            assert len(_incidents(session, source.id)) == 2
        finally:
            _cleanup(session, source)


def test_a_source_without_a_webhook_records_the_incident_anyway() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        service = SourceAlertService(session, notifier=None, threshold=3)
        try:
            incident = service.record_run_outcome(
                source, _run(session, source, "FAILED"), consecutive_failures=3
            )
            assert incident is not None
            assert incident.alert_delivery == LOG_ONLY
            assert service.open_incidents()
        finally:
            _cleanup(session, source)


def test_a_broken_channel_leaves_the_incident_open_and_unsent() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        service = SourceAlertService(
            session, notifier=_RaisingNotifier(), threshold=3
        )
        try:
            incident = service.record_run_outcome(
                source, _run(session, source, "FAILED"), consecutive_failures=3
            )
            assert incident is not None
            assert incident.alert_delivery == FAILED
            assert incident.alert_sent_at is None
            assert incident.recovered_at is None
        finally:
            _cleanup(session, source)


def test_a_rejected_message_is_recorded_as_a_failed_delivery() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        service = SourceAlertService(
            session, notifier=_RecordingNotifier(accepts=False), threshold=3
        )
        try:
            incident = service.record_run_outcome(
                source, _run(session, source, "FAILED"), consecutive_failures=3
            )
            assert incident is not None
            assert incident.alert_delivery == FAILED
        finally:
            _cleanup(session, source)


def test_a_partial_run_ends_the_incident_like_a_success() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        source = _source(session)
        service = SourceAlertService(session, notifier=_RecordingNotifier(), threshold=3)
        try:
            service.record_run_outcome(
                source, _run(session, source, "FAILED"), consecutive_failures=3
            )
            recovered = service.record_run_outcome(
                source, _run(session, source, "PARTIAL"), consecutive_failures=0
            )
            assert recovered is not None
            assert recovered.recovered_at is not None
            assert service.open_incidents() == []
        finally:
            _cleanup(session, source)
