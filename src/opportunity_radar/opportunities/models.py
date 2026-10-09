"""SQLAlchemy persistence models for the Opportunities context."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from opportunity_radar.acquisition.models import RawItemPayloadModel
from opportunity_radar.platform.database import Base

SCHEMA = "opportunities"


class OpportunityModel(Base):
    __tablename__ = "opportunity"
    __table_args__ = (
        UniqueConstraint(
            "fingerprint_version",
            "fingerprint",
            name="uq_opportunity_fingerprint_version_value",
        ),
        CheckConstraint(
            "work_mode IN ('REMOTE', 'HYBRID', 'ONSITE', 'UNKNOWN')",
            name="ck_opportunity_work_mode",
        ),
        CheckConstraint(
            "seniority IN ('INTERN', 'JUNIOR', 'MID', 'SENIOR', 'LEAD', "
            "'STAFF', 'MANAGER', 'DIRECTOR', 'UNKNOWN')",
            name="ck_opportunity_seniority",
        ),
        CheckConstraint(
            "contract_type IN ('FULL_TIME', 'PART_TIME', 'CONTRACT', 'TEMPORARY', "
            "'INTERNSHIP', 'UNKNOWN')",
            name="ck_opportunity_contract_type",
        ),
        CheckConstraint(
            "lifecycle_status IN ('DISCOVERED', 'ACTIVE', 'STALE', 'CLOSED', "
            "'ARCHIVED', 'REJECTED')",
            name="ck_opportunity_lifecycle_status",
        ),
        CheckConstraint("version > 0", name="ck_opportunity_version_positive"),
        CheckConstraint(
            "recency_basis IN ('published', 'updated', 'first_seen')",
            name="ck_opportunity_recency_basis",
        ),
        CheckConstraint(
            "role_family IN ('SOFTWARE_ENGINEERING', 'DATA', 'INFRASTRUCTURE', "
            "'SECURITY', 'QA', 'PRODUCT', 'DESIGN', 'SALES', 'MARKETING', "
            "'OPERATIONS', 'PEOPLE', 'FINANCE', 'LEGAL', 'SUPPORT', 'OTHER', "
            "'UNKNOWN')",
            name="ck_opportunity_role_family",
        ),
        Index(
            "ix_opportunity_company_status",
            "canonical_company_id",
            "lifecycle_status",
        ),
        Index("ix_opportunity_published", "published_at"),
        Index("ix_opportunity_first_seen", "first_seen_at"),
        Index("ix_opportunity_valid_through", "valid_through"),
        Index("ix_opportunity_role_family", "role_family"),
        # Both created by their own migrations (F17-06, F17-03) with a GIN index the ORM
        # never declared, which made `alembic check` propose dropping them (F20 sanity
        # pass) even though nothing about either column or index has actually changed.
        Index(
            "ix_opportunity_allowed_countries",
            "allowed_countries",
            postgresql_using="gin",
        ),
        Index(
            "ix_opportunity_search_document",
            "search_document",
            postgresql_using="gin",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_version: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_company_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("company_radar.company.id", ondelete="SET NULL"),
    )
    company_name: Mapped[str | None] = mapped_column(String(255))
    normalized_company_name: Mapped[str | None] = mapped_column(String(255))
    location_text: Mapped[str | None] = mapped_column(String(512))
    normalized_location: Mapped[str | None] = mapped_column(String(512))
    work_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    seniority: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    contract_type: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    description: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False, default="DISCOVERED")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the radar first saw this opportunity (`SourceOccurrenceModel.first_seen_at`
    #: of the occurrence that created it), set once at creation and never updated
    #: afterwards. Card F20-61's recency fallback when `published_at` is `None` — an
    #: estimate of "seen", never presented as a real publication date.
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now()
    )
    #: Card F48-16: which date the recency reference came from — `published` when
    #: `published_at` exists, `updated` when only `source_updated_at` does, `first_seen`
    #: otherwise. Kept in step with those two columns by the normalizer; the UI marks the
    #: date "estimada" whenever it is not `published`.
    recency_basis: Mapped[str] = mapped_column(
        String(16), nullable=False, default="first_seen", server_default="first_seen"
    )
    #: Explicit application-window deadline (schema.org `JobPosting.validThrough`,
    #: card F20-61), threaded from the collector when it exposes one (today only
    #: `jobposting.py`). `None` for every other collector — never fabricated. A
    #: future date is a recency-filter exception on its own, independent of
    #: `contract_type` or age.
    valid_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Recency-filter exception signal (card F20-61): a time-boxed entry program
    #: (estágio/trainee/early-careers/residência), which stays open far longer than a
    #: single senior/mid role and should not disappear from the default listing after
    #: 14 days. Never a matching/scoring input.
    recency_exempt_program: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: Evidence for the last automatic close/reopen: the two consecutive complete run ids
    #: that closed it, or the run id that brought it back. `None` until either happens.
    closure_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: Area of the posting (`role_family.py`, card F17-02), `UNKNOWN` when the rules found
    #: no single area. Never a matching factor, only an Inbox filter.
    role_family: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    #: `rule`, `term` and `origin` that decided `role_family`. `None` for rows created
    #: before this card, until the retroactive job reclassifies them.
    role_family_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: Version of the rules that produced `role_family`. `None` until classified.
    role_family_version: Mapped[str | None] = mapped_column(String(32))
    #: ISO 3166-1 alpha-2 codes (or `regions.ANY_COUNTRY`) the `regions-v1` table
    #: resolved from `location_text`. `None` means unknown — never read as "no country
    #: allowed": office location is never allowed country (card F17-06).
    allowed_countries: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    #: Version of the `regions-v1` table that produced `allowed_countries`. `None` until
    #: resolved.
    allowed_countries_version: Mapped[str | None] = mapped_column(String(32))
    #: Skill names, space-joined, kept in sync with `skills` (F17-03). Feeds the
    #: generated `search_document` column, which cannot reach another table's rows.
    search_skills: Mapped[str | None] = mapped_column(Text)
    #: Generated `tsvector`: title (A), company (A), skills+area (B), description (C),
    #: location (D), `portuguese` and `english` combined. `Computed(...)` tells the ORM
    #: this is a Postgres `GENERATED ALWAYS` column (migration 0028): never send it in an
    #: INSERT/UPDATE — Postgres rejects any explicit value for it, even `NULL`. The
    #: expression string here is documentation only; the migration is the source of truth.
    search_document: Mapped[Any | None] = mapped_column(TSVECTOR, Computed("NULL", persisted=True))
    #: Set once a `DuplicateCandidateModel` is confirmed and this opportunity is the one
    #: absorbed (F20-26). `None` for a survivor or an opportunity with no known duplicate.
    duplicate_of: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="SET NULL"),
    )
    occurrences: Mapped[list["SourceOccurrenceModel"]] = relationship(
        back_populates="opportunity", foreign_keys="SourceOccurrenceModel.opportunity_id"
    )
    normalization_results: Mapped[list["NormalizationResultModel"]] = relationship(
        back_populates="opportunity"
    )
    compensations: Mapped[list["OpportunityCompensationModel"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    skills: Mapped[list["OpportunitySkillModel"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class RelevanceMarkModel(Base):
    """One operator judgement of an opportunity, append-only.

    The current mark is the most recent row for the `opportunity_id`. Never updated or
    deleted, so precision can be recomputed against any past profile version. F17-01;
    out of scope: this table never feeds the score or the verdict.
    """

    __tablename__ = "relevance_mark"
    __table_args__ = (
        CheckConstraint(
            "reason IS NULL OR reason IN "
            "('AREA', 'SENIORITY', 'LOCATION', 'COMPANY', 'COMPENSATION', 'OTHER')",
            name="ck_relevance_mark_reason",
        ),
        Index("ix_relevance_mark_opportunity_marked_at", "opportunity_id", "marked_at"),
        Index("ix_relevance_mark_owner_sub", "owner_sub"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    #: Set exclusively from the validated server-side Clerk identity.
    owner_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    relevant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(Text)
    profile_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profile.profile_version.id", ondelete="SET NULL"),
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opportunity: Mapped[OpportunityModel] = relationship()


class DuplicateCandidateModel(Base):
    """A pair of opportunities that the detection rule says may be the same posting.

    Never merges anything by itself (F20-26): a row here is a suggestion until an
    operator confirms or rejects it. `opportunity_id` is always the smaller of the two
    ids in the pair, so the same pair is never stored twice in either order.
    """

    __tablename__ = "duplicate_candidate"
    __table_args__ = (
        CheckConstraint(
            "rule IN ('title_location_window', 'embedding')",
            name="ck_duplicate_candidate_rule",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'REJECTED')",
            name="ck_duplicate_candidate_status",
        ),
        CheckConstraint(
            "opportunity_id < duplicate_opportunity_id",
            name="ck_duplicate_candidate_ordered_pair",
        ),
        UniqueConstraint(
            "opportunity_id",
            "duplicate_opportunity_id",
            name="uq_duplicate_candidate_pair",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    duplicate_opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: `opportunity.version`/`duplicate_opportunity.version` at the moment this pair was
    #: last rejected (F20-26 merge contract). `None` unless `status == "REJECTED"`. The
    #: rejection only suppresses this pair while both versions still match; a material
    #: change on either side makes it suggestible again.
    rejected_version_opportunity: Mapped[int | None] = mapped_column(Integer)
    rejected_version_duplicate_opportunity: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SourceOccurrenceModel(Base):
    __tablename__ = "source_occurrence"
    __table_args__ = (
        UniqueConstraint("raw_item_id", name="uq_source_occurrence_raw_item"),
        Index(
            "uq_source_occurrence_source_external",
            "source_definition_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
        Index(
            "uq_source_occurrence_source_url_fallback",
            "source_definition_id",
            "normalized_source_url",
            unique=True,
            postgresql_where=text("external_id IS NULL AND normalized_source_url IS NOT NULL"),
        ),
        Index("ix_source_occurrence_source_url", "source_url"),
        Index("ix_source_occurrence_normalized_url", "normalized_source_url"),
        Index("ix_source_occurrence_opportunity", "opportunity_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    # RESTRICT, matching migration 20260914_0005 and every cleanup helper in the test
    # suite that deletes an occurrence before its raw item without deleting this row
    # explicitly (e.g. `tests/backend/acquisition/test_tavily_proposals.py::_purge`,
    # which assumes this FK, not `SourceOccurrenceObservationModel.raw_item_id` below,
    # is the one that cascades). Was briefly mismatched with the DB during the F20 sanity
    # pass (docs/44-roadmap-fase-20/validacao-pendente.md §5) before this was corrected
    # back rather than migrated, once the test failures it would have caused were traced.
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_definition_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_definition.id", ondelete="RESTRICT"),
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(512))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    normalized_source_url: Mapped[str | None] = mapped_column(String(2048))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    #: The run that last saw this occurrence, seeded by every normalization that touches
    #: it. Closure compares this against the two most recent complete runs of the source.
    last_seen_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_run.id", ondelete="SET NULL"),
    )
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Explicit application-window deadline for this occurrence's source (card
    #: F20-61), same contract as `Opportunity.valid_through` — `None` unless the
    #: collector exposes one.
    source_valid_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When retention expired the raw body this occurrence came from, and `None` while it
    #: is still there. Read as a column rather than through the payload relationship so a
    #: list of occurrences never drags every raw payload into memory to answer it.
    payload_expired_at: Mapped[datetime | None] = column_property(
        select(RawItemPayloadModel.expired_at)
        .where(RawItemPayloadModel.raw_item_id == raw_item_id)
        .correlate_except(RawItemPayloadModel)
        .scalar_subquery()
    )
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="occurrences")
    normalization_results: Mapped[list["NormalizationResultModel"]] = relationship(
        back_populates="source_occurrence"
    )
    compensation_evidence: Mapped[list["OpportunityCompensationModel"]] = relationship(
        back_populates="source_occurrence"
    )
    observations: Mapped[list["SourceOccurrenceObservationModel"]] = relationship(
        back_populates="source_occurrence"
    )


class SourceOccurrenceObservationModel(Base):
    __tablename__ = "source_occurrence_observation"
    __table_args__ = (
        UniqueConstraint(
            "raw_item_id", "source_run_id", name="uq_source_occurrence_observation_raw_item_run"
        ),
        Index("ix_source_occurrence_observation_raw_item", "raw_item_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # Normalization may not have run yet; raw evidence and run identity still prove the
    # observation. It is linked to an occurrence when one exists.
    source_occurrence_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.source_occurrence.id", ondelete="SET NULL")
    )
    source_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.source_run.id", ondelete="CASCADE"),
        nullable=False,
    )
    # CASCADE, matching migration 20260926_0041 (see the sibling comment on
    # `SourceOccurrenceModel.raw_item_id` above for why this was checked against the test
    # suite's cleanup helpers rather than assumed).
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    content_hash_matched: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_occurrence: Mapped[SourceOccurrenceModel | None] = relationship(
        back_populates="observations"
    )


class NormalizationResultModel(Base):
    __tablename__ = "normalization_result"
    __table_args__ = (
        UniqueConstraint(
            "raw_item_id",
            "normalizer_version",
            name="uq_normalization_result_raw_version",
        ),
        CheckConstraint(
            "status IN ('SUCCEEDED', 'REVIEW_REQUIRED', 'FAILED')",
            name="ck_normalization_result_status",
        ),
        CheckConstraint(
            "identity_decision IN ('NEW', 'MERGED', 'REFRESHED', 'REVIEW')",
            name="ck_normalization_result_identity_decision",
        ),
        CheckConstraint(
            "(status = 'FAILED' AND error_summary IS NOT NULL "
            "AND identity_decision IS NULL AND opportunity_id IS NULL "
            "AND source_occurrence_id IS NULL) "
            "OR (status IN ('SUCCEEDED', 'REVIEW_REQUIRED') "
            "AND error_summary IS NULL AND identity_decision IS NOT NULL "
            "AND opportunity_id IS NOT NULL "
            "AND source_occurrence_id IS NOT NULL)",
            name="ck_normalization_result_outcome",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opportunity_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
    )
    source_occurrence_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.source_occurrence.id", ondelete="CASCADE"),
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_decision: Mapped[str | None] = mapped_column(String(16))
    reasons: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    error_summary: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opportunity: Mapped[OpportunityModel | None] = relationship(
        back_populates="normalization_results"
    )
    source_occurrence: Mapped[SourceOccurrenceModel | None] = relationship(
        back_populates="normalization_results"
    )


class OpportunityCompensationModel(Base):
    __tablename__ = "opportunity_compensation"
    __table_args__ = (
        UniqueConstraint(
            "source_occurrence_id",
            name="uq_opportunity_compensation_source_occurrence",
        ),
        CheckConstraint(
            "amount_min IS NOT NULL OR amount_max IS NOT NULL",
            name="ck_opportunity_compensation_amount_present",
        ),
        CheckConstraint(
            "amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max",
            name="ck_opportunity_compensation_range",
        ),
        CheckConstraint(
            "period IN ('YEAR', 'MONTH', 'WEEK', 'DAY', 'HOUR', 'UNKNOWN')",
            name="ck_opportunity_compensation_period",
        ),
        CheckConstraint(
            "gross_net IN ('GROSS', 'NET', 'UNKNOWN')",
            name="ck_opportunity_compensation_gross_net",
        ),
        Index("ix_opportunity_compensation_currency_period", "currency", "period"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    gross_net: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    evidence_text: Mapped[str | None] = mapped_column(Text)
    evidence_source: Mapped[str | None] = mapped_column(String(512))
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_occurrence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.source_occurrence.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_item_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("acquisition.raw_item.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="compensations")
    source_occurrence: Mapped[SourceOccurrenceModel] = relationship(
        back_populates="compensation_evidence"
    )


class OpportunitySkillModel(Base):
    __tablename__ = "opportunity_skill"
    __table_args__ = (
        UniqueConstraint(
            "opportunity_id",
            "canonical_name",
            "taxonomy_version",
            name="uq_opportunity_skill_opportunity_name_taxonomy",
        ),
        CheckConstraint(
            "requirement IN ('REQUIRED', 'PREFERRED', 'UNKNOWN')",
            name="ck_opportunity_skill_requirement",
        ),
        Index("ix_opportunity_skill_requirement", "requirement"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    requirement: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    evidence: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    opportunity: Mapped[OpportunityModel] = relationship(back_populates="skills")
