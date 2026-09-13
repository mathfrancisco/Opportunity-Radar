"""Persistence queries for Acquisition."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceCheckpointModel,
    SourceDefinitionModel,
    SourceRunModel,
)


class AcquisitionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_source(self, source_id: UUID) -> SourceDefinitionModel | None:
        return self.session.scalar(
            select(SourceDefinitionModel)
            .where(SourceDefinitionModel.id == source_id)
            .options(selectinload(SourceDefinitionModel.checkpoint))
        )

    def list_sources(
        self, *, offset: int, limit: int
    ) -> tuple[list[SourceDefinitionModel], int]:
        statement = select(SourceDefinitionModel).order_by(SourceDefinitionModel.name)
        sources = list(self.session.scalars(statement.offset(offset).limit(limit)))
        total = self.session.scalar(select(func.count(SourceDefinitionModel.id))) or 0
        return sources, total

    def get_run(self, run_id: UUID) -> SourceRunModel | None:
        return self.session.scalar(
            select(SourceRunModel)
            .where(SourceRunModel.id == run_id)
            .options(selectinload(SourceRunModel.source_definition))
        )

    def list_runs(
        self, *, offset: int, limit: int, source_id: UUID | None = None
    ) -> tuple[list[SourceRunModel], int]:
        filters = (
            []
            if source_id is None
            else [SourceRunModel.source_definition_id == source_id]
        )
        statement = (
            select(SourceRunModel)
            .where(*filters)
            .options(selectinload(SourceRunModel.source_definition))
            .order_by(SourceRunModel.started_at.desc(), SourceRunModel.id.desc())
        )
        runs = list(self.session.scalars(statement.offset(offset).limit(limit)))
        total = (
            self.session.scalar(select(func.count(SourceRunModel.id)).where(*filters))
            or 0
        )
        return runs, total

    def identical_raw_item_exists(
        self, *, source_id: UUID, identity_key: str, payload_hash: str
    ) -> bool:
        return self.session.scalar(
            select(RawItemModel.id).where(
                RawItemModel.source_definition_id == source_id,
                RawItemModel.identity_key == identity_key,
                RawItemModel.payload_hash == payload_hash,
            )
        ) is not None

    def checkpoint(self, source_id: UUID) -> SourceCheckpointModel | None:
        return self.session.get(SourceCheckpointModel, source_id)
