"""Persistence adapter for the application pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.pipeline.models import ApplicationProcessModel, StageHistoryModel


class PipelineRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, application_id: UUID) -> ApplicationProcessModel | None:
        return (
            self.session.scalars(
                self._applications().where(ApplicationProcessModel.id == application_id)
            )
            .unique()
            .one_or_none()
        )

    def get_active(
        self,
        *,
        opportunity_id: UUID,
        profile_version_id: UUID,
    ) -> ApplicationProcessModel | None:
        return (
            self.session.scalars(
                self._applications().where(
                    ApplicationProcessModel.opportunity_id == opportunity_id,
                    ApplicationProcessModel.profile_version_id == profile_version_id,
                    ApplicationProcessModel.status == "ACTIVE",
                )
            )
            .unique()
            .one_or_none()
        )

    def list(
        self,
        *,
        opportunity_id: UUID | None = None,
        profile_version_id: UUID | None = None,
        status: str | None = None,
        stage: str | None = None,
        due_before: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ApplicationProcessModel], int]:
        filters = []
        if opportunity_id is not None:
            filters.append(ApplicationProcessModel.opportunity_id == opportunity_id)
        if profile_version_id is not None:
            filters.append(
                ApplicationProcessModel.profile_version_id == profile_version_id
            )
        if status is not None:
            filters.append(ApplicationProcessModel.status == status)
        if stage is not None:
            filters.append(ApplicationProcessModel.current_stage == stage)
        if due_before is not None:
            filters.append(ApplicationProcessModel.next_action_at <= due_before)
        items = list(
            self.session.scalars(
                self._applications()
                .where(*filters)
                .order_by(
                    ApplicationProcessModel.updated_at.desc(),
                    ApplicationProcessModel.id,
                )
                .offset(offset)
                .limit(limit)
            ).unique()
        )
        total = (
            self.session.scalar(
                select(func.count(ApplicationProcessModel.id)).where(*filters)
            )
            or 0
        )
        return items, total

    def add(
        self,
        *,
        opportunity_id: UUID,
        profile_version_id: UUID,
        stage: str,
        status: str,
        outcome: str | None,
        started_at: datetime,
        closed_at: datetime | None,
        applied_at: datetime | None,
        next_action: str | None,
        next_action_at: datetime | None,
        notes: str | None,
        history_notes: str | None,
    ) -> ApplicationProcessModel:
        application = ApplicationProcessModel(
            opportunity_id=opportunity_id,
            profile_version_id=profile_version_id,
            current_stage=stage,
            status=status,
            outcome=outcome,
            started_at=started_at,
            closed_at=closed_at,
            applied_at=applied_at,
            next_action=next_action,
            next_action_at=next_action_at,
            notes=notes,
            history=[
                StageHistoryModel(
                    from_stage=None,
                    to_stage=stage,
                    reason="started",
                    source="MANUAL",
                    notes=history_notes,
                    occurred_at=started_at,
                )
            ],
        )
        self.session.add(application)
        return application

    @staticmethod
    def add_history(
        application: ApplicationProcessModel,
        *,
        from_stage: str,
        to_stage: str,
        reason: str | None,
        notes: str | None,
        occurred_at: datetime,
        source: str = "MANUAL",
    ) -> StageHistoryModel:
        entry = StageHistoryModel(
            application_id=application.id,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
            source=source,
            notes=notes,
            occurred_at=occurred_at,
        )
        application.history.append(entry)
        return entry

    def history(self, application_id: UUID) -> Sequence[StageHistoryModel]:
        return self.session.scalars(
            select(StageHistoryModel)
            .where(StageHistoryModel.application_id == application_id)
            .order_by(StageHistoryModel.occurred_at, StageHistoryModel.id)
        ).all()

    @staticmethod
    def _applications() -> Select[tuple[ApplicationProcessModel]]:
        return select(ApplicationProcessModel).options(
            selectinload(ApplicationProcessModel.history)
        )
