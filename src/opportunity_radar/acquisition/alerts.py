"""Alerting for sources that stopped working, and the recovery that closes the episode.

Three consecutive failures are what separates a source that is down from a source that
had a bad minute, so the incident — not the run — is what gets announced. While an
incident is open the same source announces nothing further: a board that is offline for a
day would otherwise send one message per pass, which trains the operator to ignore them.

Delivery is best effort in the strongest sense: the webhook is a report about collection,
never a participant in it. An unreachable channel is recorded on the incident and logged,
and the collection outcome is exactly what it would have been with no channel configured.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    SourceAlertIncidentModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.platform.logging import get_logger

#: Consecutive failed runs before a source is considered down.
ALERT_FAILURE_THRESHOLD = 3

WEBHOOK = "WEBHOOK"
LOG_ONLY = "LOG_ONLY"
FAILED = "FAILED"

#: Run outcomes that end a failure streak. `PARTIAL` persisted something, so it resets the
#: streak for the same reason the collection backoff treats it as progress.
_RECOVERY_STATUSES = ("SUCCEEDED", "PARTIAL")

logger = get_logger("opportunity_radar.acquisition.alerts")


class SourceAlertNotifier(Protocol):
    """Sends one alert message. Returns whether the channel accepted it."""

    def send(self, message: dict[str, Any]) -> bool: ...


@dataclass(frozen=True, slots=True)
class WebhookNotifier:
    url: str
    timeout_seconds: float = 5.0

    def send(self, message: dict[str, Any]) -> bool:
        request = Request(  # noqa: S310 - the URL is operator-configured, not user input
            self.url,
            data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                return 200 <= response.status < 300
        except (URLError, OSError, ValueError):
            return False


def build_source_alert_notifier(
    webhook_url: str | None, *, timeout_seconds: float = 5.0
) -> SourceAlertNotifier | None:
    """No configured channel is a supported operating state, not a missing dependency."""
    if not webhook_url or not webhook_url.strip():
        return None
    return WebhookNotifier(webhook_url.strip(), timeout_seconds=timeout_seconds)


class SourceAlertService:
    def __init__(
        self,
        session: Session,
        *,
        notifier: SourceAlertNotifier | None = None,
        threshold: int = ALERT_FAILURE_THRESHOLD,
    ) -> None:
        self.session = session
        self.notifier = notifier
        self.threshold = max(1, threshold)

    def open_incidents(self) -> list[SourceAlertIncidentModel]:
        return list(
            self.session.scalars(
                select(SourceAlertIncidentModel)
                .where(SourceAlertIncidentModel.recovered_at.is_(None))
                .order_by(SourceAlertIncidentModel.opened_at)
            )
        )

    def record_run_outcome(
        self,
        source: SourceDefinitionModel,
        run: SourceRunModel,
        *,
        consecutive_failures: int,
        now: datetime | None = None,
    ) -> SourceAlertIncidentModel | None:
        """Decide what this run changed about the source being up, and announce only that.

        Called after the run is committed, so an alert can never be the reason a run is
        rolled back.
        """
        moment = now or datetime.now(UTC)
        open_incident = self._open_incident(source.id)
        if run.status in _RECOVERY_STATUSES:
            if open_incident is None:
                return None
            return self._close(open_incident, source, run, moment)
        if run.status != "FAILED":
            # PENDING, RUNNING and CANCELLED decided nothing about the source.
            return None
        if open_incident is not None or consecutive_failures < self.threshold:
            return None
        return self._open(source, run, consecutive_failures, moment)

    def record_pagination_gap(
        self,
        source: SourceDefinitionModel,
        run: SourceRunModel,
        *,
        items_seen: int,
        items_announced: int,
        now: datetime | None = None,
    ) -> None:
        """Announce that a run read fewer items than the source said it had.

        One message per run: this is a fact about that run's pagination, not an ongoing
        state like a source being down, so it carries no incident lifecycle of its own.
        """
        moment = now or datetime.now(UTC)
        self._deliver(
            {
                "event": "source_pagination_gap",
                "source_definition_id": str(source.id),
                "source_name": source.name,
                "source_type": source.source_type,
                "run_id": str(run.id),
                "items_seen": items_seen,
                "items_announced": items_announced,
                "detected_at": moment.isoformat(),
                "correlation_id": run.correlation_id,
            },
            event="source_pagination_gap",
            source=source,
            incident_id=run.id,
        )

    def _open_incident(self, source_id: UUID) -> SourceAlertIncidentModel | None:
        return self.session.scalar(
            select(SourceAlertIncidentModel).where(
                SourceAlertIncidentModel.source_definition_id == source_id,
                SourceAlertIncidentModel.recovered_at.is_(None),
            )
        )

    def _open(
        self,
        source: SourceDefinitionModel,
        run: SourceRunModel,
        consecutive_failures: int,
        moment: datetime,
    ) -> SourceAlertIncidentModel | None:
        incident = SourceAlertIncidentModel(
            source_definition_id=source.id,
            opened_at=moment,
            opened_by_run_id=run.id,
            consecutive_failures=consecutive_failures,
            error_code=run.error_code,
            error_summary=run.error_summary,
            correlation_id=run.correlation_id,
        )
        self.session.add(incident)
        try:
            self.session.flush()
        except IntegrityError:
            # Another pass opened the incident first; one episode, one message.
            self.session.rollback()
            return None
        delivery = self._deliver(
            {
                "event": "source_alert",
                "incident_id": str(incident.id),
                "source_definition_id": str(source.id),
                "source_name": source.name,
                "source_type": source.source_type,
                "consecutive_failures": consecutive_failures,
                "error_code": run.error_code,
                "error_summary": run.error_summary,
                "opened_at": moment.isoformat(),
                "correlation_id": run.correlation_id,
            },
            event="source_alert",
            source=source,
            incident_id=incident.id,
        )
        incident.alert_delivery = delivery
        incident.alert_sent_at = moment if delivery != FAILED else None
        self.session.commit()
        return incident

    def _close(
        self,
        incident: SourceAlertIncidentModel,
        source: SourceDefinitionModel,
        run: SourceRunModel,
        moment: datetime,
    ) -> SourceAlertIncidentModel:
        incident.recovered_at = moment
        incident.recovered_by_run_id = run.id
        delivery = self._deliver(
            {
                "event": "source_recovery",
                "incident_id": str(incident.id),
                "source_definition_id": str(source.id),
                "source_name": source.name,
                "source_type": source.source_type,
                "opened_at": incident.opened_at.isoformat(),
                "recovered_at": moment.isoformat(),
                "run_status": run.status,
                "items_persisted": run.items_persisted,
                "correlation_id": run.correlation_id,
            },
            event="source_recovery",
            source=source,
            incident_id=incident.id,
        )
        incident.recovery_delivery = delivery
        incident.recovery_sent_at = moment if delivery != FAILED else None
        self.session.commit()
        return incident

    def _deliver(
        self,
        message: dict[str, Any],
        *,
        event: str,
        source: SourceDefinitionModel,
        incident_id: UUID,
    ) -> str:
        context = {
            "job": "alert",
            "event": event,
            "incident_id": str(incident_id),
            "source_id": str(source.id),
            "source_name": source.name,
        }
        if self.notifier is None:
            # The case still has to be visible, which is why it is recorded rather than
            # skipped: the doctor reads this state to say the channel is not configured.
            logger.warning("source alert has no webhook configured", extra=context)
            return LOG_ONLY
        try:
            accepted = self.notifier.send(message)
        except Exception:
            logger.exception("source alert webhook raised", extra=context)
            return FAILED
        if not accepted:
            logger.warning("source alert webhook rejected the message", extra=context)
            return FAILED
        logger.info("source alert delivered", extra=context)
        return WEBHOOK


__all__ = [
    "ALERT_FAILURE_THRESHOLD",
    "FAILED",
    "LOG_ONLY",
    "WEBHOOK",
    "SourceAlertNotifier",
    "SourceAlertService",
    "WebhookNotifier",
    "build_source_alert_notifier",
]
