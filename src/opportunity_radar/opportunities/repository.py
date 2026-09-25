"""Persistence queries for canonical opportunities and their provenance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.opportunities.domain import CanonicalCandidate
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
)


@dataclass(frozen=True, slots=True)
class RawItemEvidence:
    raw_item: RawItemModel
    source_type: str
    company_id: UUID | None
    company_name: str | None
    source_configuration: dict[str, object]


class OpportunityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def raw_item_evidence(self, raw_item_id: UUID) -> RawItemEvidence | None:
        row = self.session.execute(
            select(
                RawItemModel,
                SourceDefinitionModel.source_type,
                CompanySource.company_id,
                Company.canonical_name,
                SourceDefinitionModel.configuration,
            )
            .join(
                SourceDefinitionModel,
                SourceDefinitionModel.id == RawItemModel.source_definition_id,
            )
            .outerjoin(
                CompanySource,
                CompanySource.id == SourceDefinitionModel.company_source_id,
            )
            .outerjoin(Company, Company.id == CompanySource.company_id)
            .where(RawItemModel.id == raw_item_id)
            .with_for_update(of=RawItemModel)
        ).one_or_none()
        if row is None:
            return None
        return RawItemEvidence(
            raw_item=row[0],
            source_type=row[1],
            company_id=row[2],
            company_name=row[3],
            source_configuration=dict(row[4] or {}),
        )

    def normalization_result(
        self, raw_item_id: UUID, normalizer_version: str
    ) -> NormalizationResultModel | None:
        return self.session.scalar(
            select(NormalizationResultModel)
            .where(
                NormalizationResultModel.raw_item_id == raw_item_id,
                NormalizationResultModel.normalizer_version == normalizer_version,
            )
            .options(
                joinedload(NormalizationResultModel.opportunity),
                joinedload(NormalizationResultModel.source_occurrence),
            )
        )

    def lock_candidate_identities(self, identities: set[str]) -> None:
        """Serialize competing resolutions sharing any strong identity signal."""
        for identity in sorted(identities):
            digest = hashlib.sha256(identity.encode("utf-8")).digest()
            lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
            self.session.execute(
                select(func.pg_advisory_xact_lock(lock_key))
            ).scalar_one()

    def run_raw_items(self, source_run_id: UUID) -> list[RawItemModel]:
        """The evidence one run preserved, in the order it arrived."""
        return list(
            self.session.scalars(
                select(RawItemModel)
                .where(RawItemModel.source_run_id == source_run_id)
                .order_by(RawItemModel.fetched_at, RawItemModel.id)
            ).unique()
        )

    def pending_raw_item_ids(
        self, limit: int, normalizer_version: str
    ) -> list[UUID]:
        return list(
            self.session.scalars(
                select(RawItemModel.id)
                .outerjoin(
                    NormalizationResultModel,
                    (
                        NormalizationResultModel.raw_item_id == RawItemModel.id
                    )
                    & (
                        NormalizationResultModel.normalizer_version
                        == normalizer_version
                    ),
                )
                .where(NormalizationResultModel.id.is_(None))
                .order_by(RawItemModel.fetched_at, RawItemModel.id)
                .limit(limit)
            )
        )

    def occurrence_by_external_identity(
        self,
        *,
        source_definition_id: UUID,
        external_id: str | None,
        normalized_url: str | None,
    ) -> SourceOccurrenceModel | None:
        if external_id:
            identity_filter = SourceOccurrenceModel.external_id == external_id
        elif normalized_url:
            identity_filter = (
                SourceOccurrenceModel.normalized_source_url == normalized_url
            )
        else:
            return None
        return self.session.scalar(
            select(SourceOccurrenceModel)
            .where(
                SourceOccurrenceModel.source_definition_id == source_definition_id,
                identity_filter,
            )
            .options(joinedload(SourceOccurrenceModel.opportunity))
        )

    def opportunity_by_normalized_url(
        self, normalized_url: str | None
    ) -> OpportunityModel | None:
        if normalized_url is None:
            return None
        return self.session.scalars(
            select(OpportunityModel)
            .join(SourceOccurrenceModel)
            .where(SourceOccurrenceModel.normalized_source_url == normalized_url)
            .options(selectinload(OpportunityModel.occurrences))
        ).unique().first()

    def opportunity_by_fingerprint(
        self, *, fingerprint: str, fingerprint_version: str
    ) -> OpportunityModel | None:
        return self.session.scalar(
            select(OpportunityModel)
            .where(
                OpportunityModel.fingerprint == fingerprint,
                OpportunityModel.fingerprint_version == fingerprint_version,
            )
            .options(selectinload(OpportunityModel.occurrences))
        )

    def identity_review_candidates(
        self, candidate: CanonicalCandidate, limit: int = 5
    ) -> list[OpportunityModel]:
        company_filter = (
            OpportunityModel.canonical_company_id == candidate.company_id
            if candidate.company_id is not None
            else OpportunityModel.normalized_company_name
            == candidate.normalized_company_name
        )
        if candidate.company_id is None and candidate.normalized_company_name is None:
            return []
        return list(
            self.session.scalars(
                select(OpportunityModel)
                .where(
                    company_filter,
                    OpportunityModel.normalized_title == candidate.normalized_title,
                    or_(
                        OpportunityModel.fingerprint != candidate.fingerprint,
                        OpportunityModel.fingerprint_version
                        != candidate.fingerprint_version,
                    ),
                )
                .order_by(OpportunityModel.created_at.desc())
                .limit(limit)
            )
        )

    def previous_complete_run_id(
        self, source_definition_id: UUID, *, before_run_id: UUID
    ) -> UUID | None:
        """The complete run immediately preceding `before_run_id` for this source."""
        before_started_at = (
            select(SourceRunModel.started_at)
            .where(SourceRunModel.id == before_run_id)
            .scalar_subquery()
        )
        return self.session.scalar(
            select(SourceRunModel.id)
            .where(
                SourceRunModel.source_definition_id == source_definition_id,
                SourceRunModel.complete.is_(True),
                SourceRunModel.id != before_run_id,
                SourceRunModel.started_at < before_started_at,
            )
            .order_by(SourceRunModel.started_at.desc())
            .limit(1)
        )

    def occurrences_missing_from_both_runs(
        self,
        source_definition_id: UUID,
        *,
        current_run_id: UUID,
        previous_complete_run_id: UUID,
    ) -> list[SourceOccurrenceModel]:
        """Occurrences of this source last seen in neither of the two latest complete runs."""
        return list(
            self.session.scalars(
                select(SourceOccurrenceModel)
                .where(
                    SourceOccurrenceModel.source_definition_id == source_definition_id,
                    SourceOccurrenceModel.last_seen_run_id.is_not(None),
                    SourceOccurrenceModel.last_seen_run_id != current_run_id,
                    SourceOccurrenceModel.last_seen_run_id != previous_complete_run_id,
                )
                .options(joinedload(SourceOccurrenceModel.opportunity))
            )
        )

    def occurrences_seen_in_run(
        self, source_definition_id: UUID, run_id: UUID
    ) -> list[SourceOccurrenceModel]:
        return list(
            self.session.scalars(
                select(SourceOccurrenceModel)
                .where(
                    SourceOccurrenceModel.source_definition_id == source_definition_id,
                    SourceOccurrenceModel.last_seen_run_id == run_id,
                )
                .options(joinedload(SourceOccurrenceModel.opportunity))
            )
        )

    def get(self, opportunity_id: UUID) -> OpportunityModel | None:
        return self.session.scalar(
            select(OpportunityModel)
            .where(OpportunityModel.id == opportunity_id)
            .options(
                selectinload(OpportunityModel.occurrences),
                selectinload(OpportunityModel.normalization_results),
                selectinload(OpportunityModel.compensations),
                selectinload(OpportunityModel.skills),
            )
        )

    def add_relevance_mark(
        self,
        opportunity_id: UUID,
        *,
        relevant: bool,
        reason: str | None,
        note: str | None,
        profile_version_id: UUID | None,
    ) -> RelevanceMarkModel:
        """Append a judgement. History is never updated or deleted (F17-01)."""
        mark = RelevanceMarkModel(
            opportunity_id=opportunity_id,
            relevant=relevant,
            reason=reason,
            note=note,
            profile_version_id=profile_version_id,
        )
        self.session.add(mark)
        self.session.flush()
        return mark

    def current_relevance_mark(
        self, opportunity_id: UUID
    ) -> RelevanceMarkModel | None:
        return self.session.scalar(
            select(RelevanceMarkModel)
            .where(RelevanceMarkModel.opportunity_id == opportunity_id)
            .order_by(
                RelevanceMarkModel.marked_at.desc(), RelevanceMarkModel.id.desc()
            )
            .limit(1)
        )

    def relevance_mark_history(
        self, opportunity_id: UUID
    ) -> list[RelevanceMarkModel]:
        return list(
            self.session.scalars(
                select(RelevanceMarkModel)
                .where(RelevanceMarkModel.opportunity_id == opportunity_id)
                .order_by(RelevanceMarkModel.marked_at.desc())
            )
        )

    def list(
        self,
        *,
        offset: int,
        limit: int,
        lifecycle_status: str | None = None,
        work_mode: str | None = None,
        company_id: UUID | None = None,
    ) -> tuple[list[OpportunityModel], int]:
        filters = []
        if lifecycle_status:
            filters.append(OpportunityModel.lifecycle_status == lifecycle_status)
        if work_mode:
            filters.append(OpportunityModel.work_mode == work_mode)
        if company_id:
            filters.append(OpportunityModel.canonical_company_id == company_id)
        items = list(
            self.session.scalars(
                select(OpportunityModel)
                .where(*filters)
                .options(
                    selectinload(OpportunityModel.occurrences),
                    selectinload(OpportunityModel.compensations),
                    selectinload(OpportunityModel.skills),
                )
                .order_by(
                    OpportunityModel.published_at.desc().nullslast(),
                    OpportunityModel.created_at.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
        )
        total = self.session.scalar(
            select(func.count(OpportunityModel.id)).where(*filters)
        ) or 0
        return items, total
