"""Expire old raw payloads without losing the record that they were ever collected.

Retention removes the body, never the envelope: the source, the run, the identity, the
hash and the occurrence all stay, so an opportunity can still be traced to the acquisition
that produced it a year later. What is lost is the ability to reprocess, and that loss is
written down — an expiry the history does not mention would read as content that was never
collected in the first place.

Only items that are finished with are eligible. A raw item still waiting to be normalised
by the current normalizer has pending work against its payload, and pending work outranks
the calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    PayloadRetentionEventModel,
    RawItemModel,
    RawItemPayloadModel,
)
from opportunity_radar.opportunities.models import NormalizationResultModel
from opportunity_radar.opportunities.service import NORMALIZER_VERSION
from opportunity_radar.platform.logging import get_logger

#: Twelve months, as the roadmap's default policy. Configurable per deployment.
DEFAULT_RETENTION_DAYS = 365
RETENTION_POLICY_VERSION = "retention-v1"

logger = get_logger("opportunity_radar.operations.retention")


@dataclass(frozen=True, slots=True)
class RetentionOutcome:
    examined: int
    expired: int
    policy_version: str
    retention_days: int
    cutoff: datetime


class PayloadRetentionService:
    def __init__(
        self,
        session: Session,
        *,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        policy_version: str = RETENTION_POLICY_VERSION,
        batch_size: int = 500,
        normalizer_version: str = NORMALIZER_VERSION,
    ) -> None:
        if retention_days <= 0:
            raise ValueError("retention_days must be positive")
        self.session = session
        self.retention_days = retention_days
        self.policy_version = policy_version
        self.batch_size = max(1, batch_size)
        self.normalizer_version = normalizer_version

    def expire_due_payloads(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> RetentionOutcome:
        """Expire one batch of eligible payloads. Safe to call again at any point."""
        moment = now or datetime.now(UTC)
        cutoff = moment - timedelta(days=self.retention_days)
        rows = self.session.execute(
            self._eligible(cutoff).limit(limit or self.batch_size)
        ).all()
        expired = 0
        for payload_record, payload_hash, source_definition_id in rows:
            payload_record.payload = None
            payload_record.expired_at = moment
            payload_record.retention_policy_version = self.policy_version
            self.session.add(
                PayloadRetentionEventModel(
                    raw_item_id=payload_record.raw_item_id,
                    expired_at=moment,
                    retention_policy_version=self.policy_version,
                    retention_days=self.retention_days,
                    payload_hash=payload_hash,
                    source_definition_id=source_definition_id,
                )
            )
            expired += 1
        if expired:
            self.session.commit()
            logger.info(
                "raw payloads expired",
                extra={
                    "job": "retention",
                    "expired": expired,
                    "policy_version": self.policy_version,
                    "retention_days": self.retention_days,
                    "cutoff": cutoff.isoformat(),
                },
            )
        return RetentionOutcome(
            examined=len(rows),
            expired=expired,
            policy_version=self.policy_version,
            retention_days=self.retention_days,
            cutoff=cutoff,
        )

    def _eligible(self, cutoff: datetime) -> Select[Any]:
        terminal_normalization = exists().where(
            and_(
                NormalizationResultModel.raw_item_id == RawItemPayloadModel.raw_item_id,
                NormalizationResultModel.normalizer_version == self.normalizer_version,
            )
        )
        already_recorded = exists().where(
            PayloadRetentionEventModel.raw_item_id == RawItemPayloadModel.raw_item_id
        )
        return (
            select(
                RawItemPayloadModel,
                RawItemModel.payload_hash,
                RawItemModel.source_definition_id,
            )
            .join(RawItemModel, RawItemModel.id == RawItemPayloadModel.raw_item_id)
            .where(
                RawItemPayloadModel.payload.is_not(None),
                RawItemPayloadModel.stored_at <= cutoff,
                terminal_normalization,
                ~already_recorded,
            )
            .order_by(RawItemPayloadModel.stored_at, RawItemPayloadModel.raw_item_id)
        )


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "RETENTION_POLICY_VERSION",
    "PayloadRetentionService",
    "RetentionOutcome",
]
