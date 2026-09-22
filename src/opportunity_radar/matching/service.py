"""Application service for reproducible deterministic matching."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from opportunity_radar.companies.models import Company
from opportunity_radar.matching import currency
from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisOutcome,
    AnalysisRequest,
    AnalysisStatus,
    SemanticAnalysisPort,
    analysis_cache_key,
)
from opportunity_radar.matching.domain import (
    CompanyPriority,
    CompensationEvidenceSnapshot,
    CompensationSnapshot,
    EligibilityStatus,
    MatchFactor,
    MatchResult,
    OpportunitySnapshot,
    ProfileSnapshot,
    ProfileWorkAuthorization,
    Verdict,
    default_rule_set,
    evaluate_match,
)
from opportunity_radar.matching.models import MatchAnalysisModel, MatchAssessmentModel
from opportunity_radar.matching.repository import (
    AnalysisRecord,
    AssessmentRecord,
    FactorRecord,
    SqlAlchemyMatchingRepository,
)
from opportunity_radar.opportunities.domain import (
    SKILL_TAXONOMY_VERSION,
    CompensationPeriod,
    ContractType,
    OpportunityStatus,
    Seniority,
    WorkMode,
)
from opportunity_radar.opportunities.models import (
    OpportunityCompensationModel,
    OpportunityModel,
    OpportunitySkillModel,
)
from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.profile.domain import ProfileNotFoundError, ProfileVersion
from opportunity_radar.profile.service import ProfileService

RULES_VERSION = "matching-v1"

# Section 50: the semantic layer is spent where it can still change a decision. A verdict
# the rules already settled downwards gets no model time.
DEFAULT_ANALYSIS_VERDICTS: tuple[str, ...] = (
    Verdict.HIGH_PRIORITY.value,
    Verdict.RECOMMENDED.value,
    Verdict.WATCHLIST.value,
    Verdict.REVIEW_REQUIRED.value,
)
DEFAULT_ANALYSIS_COOLDOWN = timedelta(hours=1)
DEFAULT_ANALYSIS_ATTEMPT_WINDOW = timedelta(hours=24)
DEFAULT_ANALYSIS_MAX_ATTEMPTS = 3
DEFAULT_ANALYSIS_CLAIM_LEASE = timedelta(minutes=15)


class MatchNotFoundError(LookupError):
    pass


class MatchOpportunityNotFoundError(LookupError):
    pass


class AnalysisInProgressError(RuntimeError):
    """Another holder — the job or the manual action — owns this analysis right now."""


class MatchingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = SqlAlchemyMatchingRepository(session)

    def evaluate(
        self,
        opportunity_id: UUID,
        *,
        profile_version_id: UUID | None = None,
    ) -> MatchAssessmentModel:
        opportunity = OpportunityRepository(self.session).get(opportunity_id)
        if opportunity is None:
            raise MatchOpportunityNotFoundError(str(opportunity_id))
        profile_service = ProfileService(self.session)
        profile = (
            profile_service.get_version(profile_version_id)
            if profile_version_id is not None
            else profile_service.get_active()
        )
        assessed_at = datetime.now(UTC)
        taxonomy_version, opportunity_snapshot, profile_snapshot, input_hash = (
            self._evaluation_identity(opportunity, profile, assessed_at)
        )
        existing = self.repository.get_existing(
            input_hash=input_hash,
        )
        if existing is not None:
            return existing

        result = evaluate_match(
            opportunity_snapshot,
            profile_snapshot,
            default_rule_set(RULES_VERSION),
            assessed_at=assessed_at,
        )
        assessment = self.repository.add(
            _assessment_record(
                result,
                opportunity_snapshot,
                profile_snapshot,
                taxonomy_version,
                input_hash,
                assessed_at,
            ),
            [_factor_record(factor) for factor in result.factors],
        )
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.repository.get_existing(
                input_hash=input_hash,
            )
            if existing is None:
                raise
            return existing
        loaded = self.repository.get(assessment.id)
        assert loaded is not None
        return loaded

    def pending_evaluation_ids(self, *, limit: int, now: datetime | None = None) -> list[UUID]:
        """Eligible opportunities with no assessment for the current identity today.

        Asked in SQL against the identity components rather than by rebuilding a snapshot
        hash per opportunity: the read model has to ask the same question over the whole
        catalogue, and a rule that only one side can express is a rule the two sides will
        eventually disagree on.
        """
        profile = ProfileService(self.session).get_active()
        reference_date = currency.reference_day(now or datetime.now(UTC))
        assessment = aliased(MatchAssessmentModel)
        already_evaluated = (
            select(literal(1))
            .where(
                assessment.opportunity_id == OpportunityModel.id,
                assessment.opportunity_version == OpportunityModel.version,
                assessment.profile_version_id == profile.id,
                assessment.rules_version == RULES_VERSION,
                assessment.taxonomy_version == currency.opportunity_taxonomy_version(),
                currency.assessment_reference_day(assessment.assessed_at)
                == reference_date,
            )
            .exists()
        )
        return list(
            self.session.scalars(
                select(OpportunityModel.id)
                .where(
                    OpportunityModel.lifecycle_status.in_(("DISCOVERED", "ACTIVE")),
                    ~already_evaluated,
                )
                .order_by(OpportunityModel.created_at, OpportunityModel.id)
                .limit(limit)
            )
        )

    def evaluation_identity(
        self,
        opportunity: OpportunityModel,
        profile: ProfileVersion,
        *,
        assessed_at: datetime,
    ) -> currency.EvaluationIdentity:
        """The identity the worker and the read model both compare against."""
        return currency.EvaluationIdentity.build(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            profile_version_id=profile.id,
            rules_version=RULES_VERSION,
            taxonomy_version=_taxonomy_version(opportunity),
            assessed_at=assessed_at,
        )

    def current_assessment(self, opportunity_id: UUID) -> MatchAssessmentModel | None:
        """The most recent assessment that still describes the current inputs, if any.

        The ORM twin of what the Inbox resolves in SQL. Returning `None` means every
        stored assessment is stale, not that the opportunity was never scored.
        """
        opportunity = OpportunityRepository(self.session).get(opportunity_id)
        if opportunity is None:
            raise MatchOpportunityNotFoundError(str(opportunity_id))
        profile = ProfileService(self.session).get_active()
        identity = self.evaluation_identity(
            opportunity, profile, assessed_at=datetime.now(UTC)
        )
        assessments, _ = self.repository.list(opportunity_id=opportunity_id, limit=200)
        return next(
            (item for item in assessments if identity.describes(item)),
            None,
        )

    def is_stale(self, assessment: MatchAssessmentModel) -> bool:
        """Whether an assessment still describes the active matching inputs."""
        opportunity = OpportunityRepository(self.session).get(assessment.opportunity_id)
        if opportunity is None:
            return True
        try:
            profile = ProfileService(self.session).get_active()
        except ProfileNotFoundError:
            return True
        return self.evaluation_identity(
            opportunity, profile, assessed_at=datetime.now(UTC)
        ).is_stale(assessment)

    def _evaluation_identity(
        self,
        opportunity: OpportunityModel,
        profile: ProfileVersion,
        assessed_at: datetime,
    ) -> tuple[str, OpportunitySnapshot, ProfileSnapshot, str]:
        taxonomy_version = _taxonomy_version(opportunity)
        opportunity_snapshot = _opportunity_snapshot(self.session, opportunity, profile)
        profile_snapshot = _profile_snapshot(profile)
        return (
            taxonomy_version,
            opportunity_snapshot,
            profile_snapshot,
            _input_hash(
                opportunity_snapshot,
                profile_snapshot,
                rules_version=RULES_VERSION,
                taxonomy_version=taxonomy_version,
                reference_date=assessed_at.date().isoformat(),
            ),
        )

    def get(self, assessment_id: UUID) -> MatchAssessmentModel:
        assessment = self.repository.get(assessment_id)
        if assessment is None:
            raise MatchNotFoundError(str(assessment_id))
        return assessment

    async def analyze(
        self,
        assessment_id: UUID,
        adapter: SemanticAnalysisPort,
        *,
        refresh: bool = False,
        owner: str = "manual",
        lease: timedelta = DEFAULT_ANALYSIS_CLAIM_LEASE,
    ) -> MatchAnalysisModel:
        """Attach the advisory semantic layer to an assessment that already concluded.

        Section 44 of the roadmap: the deterministic decision is read, never rewritten.
        Whatever the model does — answer, time out, disappear — this returns a persisted
        row and the assessment keeps its score, verdict and factors untouched.

        The claim is what keeps the job and the manual action from prompting the same
        assessment twice. It is taken after the cache lookup, so a reader of an already
        completed analysis never waits on a claim it does not need.
        """
        self.get(assessment_id)  # Fail on an unknown assessment before taking a claim.
        if not refresh:
            cached = self.repository.get_completed_analysis(assessment_id)
            if cached is not None:
                return cached

        now = datetime.now(UTC)
        if not self.repository.acquire_analysis_claim(
            assessment_id, owner=owner, now=now, lease=lease
        ):
            self.session.rollback()
            raise AnalysisInProgressError(str(assessment_id))
        # The claim is only exclusive once other transactions can see it.
        self.session.commit()
        try:
            if not refresh:
                # The previous holder may have completed while we waited for the lease.
                cached = self.repository.get_completed_analysis(assessment_id)
                if cached is not None:
                    return cached

            request = _analysis_request(self.get(assessment_id))
            outcome = await adapter.analyze(request)
            cache_key = analysis_cache_key(
                request,
                model_id=adapter.model,
                prompt_version=adapter.prompt_version,
            )
            analysis = self.repository.add_analysis(
                _analysis_record(
                    assessment_id=assessment_id,
                    cache_key=cache_key,
                    outcome=outcome,
                    analyzed_at=datetime.now(UTC),
                )
            )
            self.session.commit()
            self.session.refresh(analysis)
            return analysis
        finally:
            # Releasing must succeed even when the body failed, so the assessment is not
            # retired from the queue until the lease would have expired on its own.
            self.session.rollback()
            self.repository.release_analysis_claim(assessment_id, owner=owner)
            self.session.commit()

    def pending_analysis_ids(
        self,
        *,
        limit: int,
        eligible_verdicts: Sequence[str] = DEFAULT_ANALYSIS_VERDICTS,
        cooldown: timedelta = DEFAULT_ANALYSIS_COOLDOWN,
        attempt_window: timedelta = DEFAULT_ANALYSIS_ATTEMPT_WINDOW,
        max_attempts: int = DEFAULT_ANALYSIS_MAX_ATTEMPTS,
        now: datetime | None = None,
    ) -> list[UUID]:
        """Current assessments whose semantic layer is eligible and off cooldown."""
        return list(
            self.repository.pending_analysis_ids(
                eligible_verdicts=eligible_verdicts,
                limit=limit,
                now=now or datetime.now(UTC),
                cooldown=cooldown,
                attempt_window=attempt_window,
                max_attempts=max_attempts,
            )
        )

    def latest_analysis(self, assessment_id: UUID) -> MatchAnalysisModel | None:
        return self.repository.latest_analysis(assessment_id)

    def list(
        self,
        *,
        opportunity_id: UUID | None = None,
        profile_version_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[MatchAssessmentModel], int]:
        return self.repository.list(
            opportunity_id=opportunity_id,
            profile_version_id=profile_version_id,
            offset=offset,
            limit=limit,
        )


def _opportunity_snapshot(
    session: Session,
    opportunity: OpportunityModel,
    profile: ProfileVersion,
) -> OpportunitySnapshot:
    priority_value = None
    if opportunity.canonical_company_id is not None:
        priority_value = session.scalar(
            select(Company.priority).where(Company.id == opportunity.canonical_company_id)
        )
    priority = _optional_enum(CompanyPriority, priority_value)
    compensation, compensation_conflict, compensation_candidates = (
        _opportunity_compensation(opportunity)
    )
    skills = sorted(opportunity.skills, key=lambda item: item.canonical_name)
    return OpportunitySnapshot(
        opportunity_id=opportunity.id,
        content_version=opportunity.version,
        status=OpportunityStatus(opportunity.lifecycle_status),
        work_mode=WorkMode(opportunity.work_mode),
        seniority=Seniority(opportunity.seniority),
        contract_types=_known_contracts((opportunity.contract_type,)),
        required_skills=tuple(
            item.canonical_name for item in skills if item.requirement == "REQUIRED"
        ),
        preferred_skills=tuple(
            item.canonical_name for item in skills if item.requirement == "PREFERRED"
        ),
        skill_evidence_refs=_skill_evidence_refs(skills),
        company_priority=priority,
        compensation=compensation,
        compensation_candidates=compensation_candidates,
        compensation_conflict=compensation_conflict,
        published_at=opportunity.published_at,
        evidence_refs=(f"opportunity:{opportunity.id}:version:{opportunity.version}",),
    )


def _profile_snapshot(profile: ProfileVersion) -> ProfileSnapshot:
    preferences = profile.snapshot.preferences
    profile_compensation = None
    if (
        preferences.compensation_min is not None
        or preferences.compensation_max is not None
    ):
        profile_compensation = CompensationSnapshot(
            minimum=preferences.compensation_min,
            maximum=preferences.compensation_max,
            currency=(
                preferences.compensation_currency.upper()
                if preferences.compensation_currency
                else None
            ),
            period=_optional_enum(
                CompensationPeriod, preferences.compensation_period
            ),
        )
    return ProfileSnapshot(
        profile_version_id=profile.id,
        skills=tuple(sorted(skill.canonical_name for skill in profile.snapshot.skills)),
        countries=tuple(sorted(preferences.countries)),
        accepted_work_modes=_known_work_modes(preferences.work_modes),
        accepted_contract_types=_known_contracts(preferences.contracts),
        compensation=profile_compensation,
        work_authorization=(
            ProfileWorkAuthorization.REQUIRES_SPONSORSHIP
            if preferences.sponsorship_required
            else ProfileWorkAuthorization.UNKNOWN
        ),
        evidence_refs=(f"profile-version:{profile.id}",),
    )


def _opportunity_compensation(opportunity: OpportunityModel) -> tuple[
    CompensationSnapshot | None,
    bool,
    tuple[CompensationEvidenceSnapshot, ...],
]:
    candidates = sorted(
        opportunity.compensations,
        key=lambda item: str(item.source_occurrence_id),
    )
    evidence = tuple(
        CompensationEvidenceSnapshot(
            minimum=item.amount_min,
            maximum=item.amount_max,
            currency=item.currency,
            period=item.period,
            gross_net=item.gross_net,
            evidence_text=item.evidence_text,
            evidence_source=item.evidence_source,
            source_occurrence_id=item.source_occurrence_id,
            raw_item_id=item.raw_item_id,
        )
        for item in candidates
    )
    if not candidates:
        return None, False, evidence
    if any(
        _compensation_conflicts(left, right)
        for index, left in enumerate(candidates)
        for right in candidates[index + 1 :]
    ):
        return None, True, evidence
    minimum = next(
        (item.amount_min for item in candidates if item.amount_min is not None), None
    )
    maximum = next(
        (item.amount_max for item in candidates if item.amount_max is not None), None
    )
    currency = next(
        (item.currency for item in candidates if item.currency is not None), None
    )
    known_period = next(
        (
            item.period
            for item in candidates
            if item.period != CompensationPeriod.UNKNOWN.value
        ),
        None,
    )
    return (
        CompensationSnapshot(
            minimum=minimum,
            maximum=maximum,
            currency=currency.upper() if currency else None,
            period=_optional_enum(CompensationPeriod, known_period),
        ),
        False,
        evidence,
    )


def _compensation_conflicts(
    left: OpportunityCompensationModel,
    right: OpportunityCompensationModel,
) -> bool:
    if (
        left.amount_min is not None
        and right.amount_min is not None
        and left.amount_min != right.amount_min
    ):
        return True
    if (
        left.amount_max is not None
        and right.amount_max is not None
        and left.amount_max != right.amount_max
    ):
        return True
    merged_min = left.amount_min if left.amount_min is not None else right.amount_min
    merged_max = left.amount_max if left.amount_max is not None else right.amount_max
    if merged_min is not None and merged_max is not None and merged_min > merged_max:
        return True
    if left.currency and right.currency and left.currency != right.currency:
        return True
    if (
        left.period != "UNKNOWN"
        and right.period != "UNKNOWN"
        and left.period != right.period
    ):
        return True
    return (
        left.gross_net != "UNKNOWN"
        and right.gross_net != "UNKNOWN"
        and left.gross_net != right.gross_net
    )


def _taxonomy_version(opportunity: OpportunityModel) -> str:
    versions = sorted({skill.taxonomy_version for skill in opportunity.skills})
    return "+".join(versions) if versions else SKILL_TAXONOMY_VERSION


def _skill_evidence_refs(
    skills: list[OpportunitySkillModel],
) -> tuple[str, ...]:
    refs: set[str] = set()
    for skill in skills:
        for evidence in skill.evidence:
            encoded = json.dumps(
                evidence,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            raw_item_id = evidence.get("raw_item_id") if isinstance(evidence, dict) else None
            refs.add(
                f"raw-item:{raw_item_id or 'unknown'}:skill:{skill.canonical_name}:"
                f"sha256:{digest}"
            )
    return tuple(sorted(refs))


def _assessment_record(
    result: MatchResult,
    opportunity: OpportunitySnapshot,
    profile: ProfileSnapshot,
    taxonomy_version: str,
    input_hash: str,
    assessed_at: datetime,
) -> AssessmentRecord:
    eligibility_details = tuple(
        {
            "code": item.code,
            "result": item.result.value,
            "reason": item.reason,
            "evidence_refs": list(item.evidence_refs),
            "confidence": str(item.confidence),
            "severity": item.severity,
        }
        for item in result.eligibility.filters
    )
    return AssessmentRecord(
        opportunity_id=result.opportunity_id,
        opportunity_version=result.opportunity_content_version,
        profile_version_id=result.profile_version_id,
        input_hash=input_hash,
        rules_version=result.rules_version,
        taxonomy_version=taxonomy_version,
        opportunity_snapshot=_snapshot_dict(opportunity),
        profile_snapshot=_snapshot_dict(profile),
        eligibility=result.eligibility.status.value,
        eligibility_details=eligibility_details,
        verdict=result.verdict.value,
        score=result.score,
        confidence=result.confidence,
        assessed_at=assessed_at,
    )


def _analysis_request(assessment: MatchAssessmentModel) -> AnalysisRequest:
    """Build the prompt input from persisted state only, so an analysis is reproducible."""
    return AnalysisRequest(
        opportunity_id=assessment.opportunity_id,
        opportunity_content_version=assessment.opportunity_version,
        profile_version_id=assessment.profile_version_id,
        rules_version=assessment.rules_version,
        taxonomy_version=assessment.taxonomy_version,
        eligibility=EligibilityStatus(assessment.eligibility),
        verdict=Verdict(assessment.verdict),
        score=assessment.score,
        opportunity_snapshot=assessment.opportunity_snapshot,
        profile_snapshot=assessment.profile_snapshot,
    )


def _analysis_record(
    *,
    assessment_id: UUID,
    cache_key: str,
    outcome: AnalysisOutcome,
    analyzed_at: datetime,
) -> AnalysisRecord:
    analysis = outcome.analysis
    if outcome.status is not AnalysisStatus.AI_COMPLETED or analysis is None:
        return AnalysisRecord(
            assessment_id=assessment_id,
            cache_key=cache_key,
            status=outcome.status.value,
            schema_version=ANALYSIS_SCHEMA_VERSION,
            analyzed_at=analyzed_at,
            failure_code=outcome.failure_code.value if outcome.failure_code else None,
            detail=outcome.detail,
        )
    return AnalysisRecord(
        assessment_id=assessment_id,
        cache_key=cache_key,
        status=outcome.status.value,
        schema_version=analysis.schema_version,
        analyzed_at=analyzed_at,
        summary=analysis.summary,
        strengths=analysis.strengths,
        risks=analysis.risks,
        inferences=analysis.inferences,
        unknowns=analysis.unknowns,
        recommended_review=analysis.recommended_review,
        model_id=analysis.model_id,
        prompt_version=analysis.prompt_version,
    )


def _input_hash(
    opportunity: OpportunitySnapshot,
    profile: ProfileSnapshot,
    *,
    rules_version: str,
    taxonomy_version: str,
    reference_date: str,
) -> str:
    payload = {
        "opportunity": _snapshot_dict(opportunity),
        "profile": _snapshot_dict(profile),
        "rules_version": rules_version,
        "taxonomy_version": taxonomy_version,
        "reference_date": reference_date,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _factor_record(factor: MatchFactor) -> FactorRecord:
    return FactorRecord(
        factor_code=factor.factor_code,
        weight=factor.weight,
        raw_score=factor.raw_score,
        contribution=factor.contribution,
        status=factor.status.value,
        confidence=factor.confidence,
        missing_policy=factor.missing_policy.value,
        explanation=factor.explanation,
        evidence_refs=factor.evidence_refs,
    )


def _snapshot_dict(snapshot: OpportunitySnapshot | ProfileSnapshot) -> dict[str, Any]:
    if isinstance(snapshot, OpportunitySnapshot):
        return {
            "opportunity_id": str(snapshot.opportunity_id),
            "content_version": snapshot.content_version,
            "status": snapshot.status.value,
            "work_mode": snapshot.work_mode.value,
            "seniority": snapshot.seniority.value,
            "allowed_countries": list(snapshot.allowed_countries),
            "contract_types": [item.value for item in snapshot.contract_types],
            "required_skills": list(snapshot.required_skills),
            "preferred_skills": list(snapshot.preferred_skills),
            "skill_evidence_refs": list(snapshot.skill_evidence_refs),
            "company_priority": (
                snapshot.company_priority.value if snapshot.company_priority else None
            ),
            "compensation": _compensation_dict(snapshot.compensation),
            "compensation_candidates": [
                _compensation_evidence_dict(item)
                for item in snapshot.compensation_candidates
            ],
            "compensation_conflict": snapshot.compensation_conflict,
            "work_authorization": snapshot.work_authorization.value,
            "timezone_overlap_hours": (
                str(snapshot.timezone_overlap_hours)
                if snapshot.timezone_overlap_hours is not None
                else None
            ),
            "required_timezone_overlap_hours": (
                str(snapshot.required_timezone_overlap_hours)
                if snapshot.required_timezone_overlap_hours is not None
                else None
            ),
            "published_at": (
                snapshot.published_at.isoformat() if snapshot.published_at else None
            ),
            "evidence_refs": list(snapshot.evidence_refs),
        }
    return {
        "profile_version_id": str(snapshot.profile_version_id),
        "skills": list(snapshot.skills),
        "countries": list(snapshot.countries),
        "accepted_work_modes": [item.value for item in snapshot.accepted_work_modes],
        "accepted_contract_types": [
            item.value for item in snapshot.accepted_contract_types
        ],
        "accepted_seniorities": [item.value for item in snapshot.accepted_seniorities],
        "compensation": _compensation_dict(snapshot.compensation),
        "work_authorization": snapshot.work_authorization.value,
        "evidence_refs": list(snapshot.evidence_refs),
    }


def _compensation_dict(value: CompensationSnapshot | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "minimum": str(value.minimum) if value.minimum is not None else None,
        "maximum": str(value.maximum) if value.maximum is not None else None,
        "currency": value.currency,
        "period": value.period.value if value.period else None,
    }


def _compensation_evidence_dict(
    value: CompensationEvidenceSnapshot,
) -> dict[str, Any]:
    return {
        "minimum": str(value.minimum) if value.minimum is not None else None,
        "maximum": str(value.maximum) if value.maximum is not None else None,
        "currency": value.currency,
        "period": value.period,
        "gross_net": value.gross_net,
        "evidence_text": value.evidence_text,
        "evidence_source": value.evidence_source,
        "source_occurrence_id": str(value.source_occurrence_id),
        "raw_item_id": str(value.raw_item_id),
    }


EnumType = TypeVar("EnumType", bound=StrEnum)


def _optional_enum(enum_type: type[EnumType], value: str | None) -> EnumType | None:
    if value is None:
        return None
    try:
        return enum_type(value.strip().upper())
    except ValueError:
        return None


def _known_work_modes(values: tuple[str, ...]) -> tuple[WorkMode, ...]:
    return tuple(
        item
        for value in values
        if (item := _optional_enum(WorkMode, value)) is not None
        and item is not WorkMode.UNKNOWN
    )


def _known_contracts(values: tuple[str, ...]) -> tuple[ContractType, ...]:
    return tuple(
        item
        for value in values
        if (item := _optional_enum(ContractType, value)) is not None
        and item is not ContractType.UNKNOWN
    )
