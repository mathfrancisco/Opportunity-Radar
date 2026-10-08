"""Persistence queries for canonical opportunities and their provenance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.domain import normalize_name
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.opportunities.domain import DEFAULT_RECENCY_WINDOW_DAYS, CanonicalCandidate
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


def recency_reference_expression() -> Any:
    """SQL side of `domain.recency_reference` (card F48-16): the same
    `published_at ?? source_updated_at ?? first_seen_at` order, as a COALESCE."""
    return func.coalesce(
        OpportunityModel.published_at,
        OpportunityModel.source_updated_at,
        OpportunityModel.first_seen_at,
    )


def posting_group_key() -> Any:
    """Card F48-10: `(company, normalized title, source)` of one posting, as one string.

    The same job listed once per city has one row per city (each with its own URL), so
    the Inbox shows the group once while nothing is merged, closed or rewritten. The
    source is the opportunity's first occurrence source (by id); an opportunity with no
    occurrence is its own group, so nothing ever collapses without evidence of a shared
    source. A company without a canonical id groups by its lower-cased name.
    """
    source = (
        select(func.min(cast(SourceOccurrenceModel.source_definition_id, String)))
        .where(SourceOccurrenceModel.opportunity_id == OpportunityModel.id)
        .correlate(OpportunityModel)
        .scalar_subquery()
    )
    return func.concat_ws(
        "|",
        func.coalesce(
            cast(OpportunityModel.canonical_company_id, String),
            func.concat("name:", func.lower(func.coalesce(OpportunityModel.company_name, ""))),
        ),
        OpportunityModel.normalized_title,
        func.coalesce(source, func.concat("id:", cast(OpportunityModel.id, String))),
    )


def open_at_source_condition() -> Any:
    """Some occurrence of the opportunity was seen in the latest complete run of *its own*
    source (`last_seen_run_id` equals that run), whatever its age. Shared by the Inbox
    "Abertas na fonte" lens (F48-16) and run closures (F48-11)."""
    latest_complete_run = (
        select(SourceRunModel.id)
        .where(
            SourceRunModel.source_definition_id == SourceOccurrenceModel.source_definition_id,
            SourceRunModel.complete.is_(True),
        )
        .order_by(SourceRunModel.started_at.desc())
        .limit(1)
        .correlate(SourceOccurrenceModel)
        .scalar_subquery()
    )
    return (
        select(SourceOccurrenceModel.id)
        .where(
            SourceOccurrenceModel.opportunity_id == OpportunityModel.id,
            SourceOccurrenceModel.last_seen_run_id == latest_complete_run,
        )
        .exists()
    )


def recency_condition(*, now: datetime, window_days: int) -> Any:
    """SQL side of `domain.recency_decision` (cards F20-61, F48-16): reference date inside
    the window, OR a time-boxed program, OR a still-open `valid_through`. One definition,
    shared by `/opportunities` and the Inbox (`dashboard.queries._recency_condition`);
    `tests/backend/dashboard/test_recency_mirror_integration.py` compares it with the
    pure function over the same input grid."""
    within_window = recency_reference_expression() >= now - timedelta(days=window_days)
    has_open_deadline = and_(
        OpportunityModel.valid_through.is_not(None),
        OpportunityModel.valid_through > now,
    )
    return or_(within_window, OpportunityModel.recency_exempt_program.is_(True), has_open_deadline)


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
        configuration = dict(row[4] or {})
        company_id, company_name = row[2], row[3]
        if company_id is None:
            # Proposed sources (F20-53/60/71) are not linked to a CompanySource; the
            # company they were proposed for is recorded by name in their configuration.
            configured = configuration.get("company_name")
            if isinstance(configured, str) and configured.strip():
                company = self.session.scalar(
                    select(Company).where(Company.normalized_name == normalize_name(configured))
                )
                if company is not None:
                    company_id, company_name = company.id, company.canonical_name
        return RawItemEvidence(
            raw_item=row[0],
            source_type=row[1],
            company_id=company_id,
            company_name=company_name,
            source_configuration=configuration,
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
            self.session.execute(select(func.pg_advisory_xact_lock(lock_key))).scalar_one()

    def run_raw_items(self, source_run_id: UUID) -> list[RawItemModel]:
        """The evidence one run preserved, in the order it arrived."""
        return list(
            self.session.scalars(
                select(RawItemModel)
                .where(
                    RawItemModel.source_run_id == source_run_id,
                    RawItemModel.item_metadata["source_proposal_candidate"]
                    .as_boolean()
                    .is_not(True),
                )
                .order_by(RawItemModel.fetched_at, RawItemModel.id)
            ).unique()
        )

    def pending_raw_item_ids(self, limit: int, normalizer_version: str) -> list[UUID]:
        return list(
            self.session.scalars(
                select(RawItemModel.id)
                .outerjoin(
                    NormalizationResultModel,
                    (NormalizationResultModel.raw_item_id == RawItemModel.id)
                    & (NormalizationResultModel.normalizer_version == normalizer_version),
                )
                .where(NormalizationResultModel.id.is_(None))
                .where(
                    RawItemModel.item_metadata["source_proposal_candidate"]
                    .as_boolean()
                    .is_not(True)
                )
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
            identity_filter = SourceOccurrenceModel.normalized_source_url == normalized_url
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

    def opportunity_by_normalized_url(self, normalized_url: str | None) -> OpportunityModel | None:
        if normalized_url is None:
            return None
        return (
            self.session.scalars(
                select(OpportunityModel)
                .join(SourceOccurrenceModel)
                .where(SourceOccurrenceModel.normalized_source_url == normalized_url)
                .options(selectinload(OpportunityModel.occurrences))
            )
            .unique()
            .first()
        )

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
            else OpportunityModel.normalized_company_name == candidate.normalized_company_name
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
                        OpportunityModel.fingerprint_version != candidate.fingerprint_version,
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

    def posting_group_siblings(
        self, opportunity: OpportunityModel
    ) -> list[tuple[OpportunityModel, str | None]]:
        """Other postings in this opportunity's `posting_group_key()`, each with the URL of
        its first occurrence. Read only (F48-10): siblings are never merged or closed."""
        key = (
            select(posting_group_key())
            .where(OpportunityModel.id == opportunity.id)
            .scalar_subquery()
        )
        siblings = list(
            self.session.scalars(
                select(OpportunityModel)
                .where(
                    OpportunityModel.id != opportunity.id,
                    OpportunityModel.normalized_title == opportunity.normalized_title,
                    posting_group_key() == key,
                )
                .order_by(OpportunityModel.location_text.nulls_last(), OpportunityModel.id)
            )
        )
        if not siblings:
            return []
        urls: dict[UUID, str] = {
            opportunity_id: source_url
            for opportunity_id, source_url in self.session.execute(
                select(
                    SourceOccurrenceModel.opportunity_id,
                    func.min(SourceOccurrenceModel.source_url),
                )
                .where(SourceOccurrenceModel.opportunity_id.in_([item.id for item in siblings]))
                .group_by(SourceOccurrenceModel.opportunity_id)
            )
        }
        return [(item, urls.get(item.id)) for item in siblings]

    def opportunity_is_open_at_source(self, opportunity_id: UUID) -> bool:
        """Whether any occurrence was seen in the latest complete run of its own source."""
        return bool(
            self.session.scalar(
                select(OpportunityModel.id).where(
                    OpportunityModel.id == opportunity_id, open_at_source_condition()
                )
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
        owner_sub: str,
    ) -> RelevanceMarkModel:
        """Append a judgement. History is never updated or deleted (F17-01)."""
        mark = RelevanceMarkModel(
            owner_sub=owner_sub,
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
        self, opportunity_id: UUID, *, owner_sub: str | None = None
    ) -> RelevanceMarkModel | None:
        return self.session.scalar(
            select(RelevanceMarkModel)
            .where(
                RelevanceMarkModel.opportunity_id == opportunity_id,
                *([RelevanceMarkModel.owner_sub == owner_sub] if owner_sub is not None else []),
            )
            .order_by(RelevanceMarkModel.marked_at.desc(), RelevanceMarkModel.id.desc())
            .limit(1)
        )

    def relevance_mark_history(
        self, opportunity_id: UUID, *, owner_sub: str | None = None
    ) -> list[RelevanceMarkModel]:
        return list(
            self.session.scalars(
                select(RelevanceMarkModel)
                .where(
                    RelevanceMarkModel.opportunity_id == opportunity_id,
                    *([RelevanceMarkModel.owner_sub == owner_sub] if owner_sub is not None else []),
                )
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
        #: Card F20-61: the server's own default, absent a caller override, is
        #: filtered — a plain listing agrees with `/inbox`'s own default.
        only_recent: bool = True,
        now: datetime | None = None,
        recency_window_days: int = DEFAULT_RECENCY_WINDOW_DAYS,
    ) -> tuple[list[OpportunityModel], int]:
        filters = []
        if lifecycle_status:
            filters.append(OpportunityModel.lifecycle_status == lifecycle_status)
        if work_mode:
            filters.append(OpportunityModel.work_mode == work_mode)
        if company_id:
            filters.append(OpportunityModel.canonical_company_id == company_id)
        if only_recent:
            filters.append(
                recency_condition(now=now or datetime.now(UTC), window_days=recency_window_days)
            )
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
        total = self.session.scalar(select(func.count(OpportunityModel.id)).where(*filters)) or 0
        return items, total
