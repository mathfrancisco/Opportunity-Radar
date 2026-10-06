"""Normalize immutable acquisition evidence into canonical opportunities."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import RawItemModel, SourceRunModel
from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY
from opportunity_radar.opportunities.domain import (
    SENIORITY_MAPPING_VERSION,
    SKILL_TAXONOMY_VERSION,
    CanonicalCandidate,
    CompensationPeriod,
    GrossNet,
    NormalizationError,
    NormalizationInput,
    OpportunityStatus,
    SkillClassification,
    build_candidate,
    recency_basis_of,
    seniority_classification,
)
from opportunity_radar.opportunities.duplicates import find_title_location_window_candidates
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityCompensationModel,
    OpportunityModel,
    OpportunitySkillModel,
    RelevanceMarkModel,
    SourceOccurrenceModel,
    SourceOccurrenceObservationModel,
)
from opportunity_radar.opportunities.repository import (
    OpportunityRepository,
    RawItemEvidence,
)
from opportunity_radar.opportunities.role_family import (
    ROLE_FAMILY_VERSION,
    RoleFamily,
    classify_role_family,
    departments_from_metadata,
)
from opportunity_radar.platform.config import get_settings
from opportunity_radar.platform.logging import get_logger

logger = get_logger("opportunity_radar.opportunities")

NORMALIZER_VERSION = "v6"


class PayloadExpiredError(NormalizationError):
    """Retention already purged the raw payload this pre-contract item needs.

    Card F17-06: an expired payload is never reconstructed by guesswork. The caller
    marks the item unavailable (a `FAILED` `NormalizationResultModel`, kept — never
    deleted — as history) and reports that only a fresh collection can fix it.
    """


class RawItemNotFoundError(LookupError):
    pass


class SourceRunNotFoundError(LookupError):
    pass


class OpportunityNotFoundError(LookupError):
    pass


class OpportunityVersionConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NormalizationBatch:
    processed: int
    succeeded: int
    review_required: int
    failed: int


class OpportunityService:
    def __init__(
        self,
        session: Session,
        repository: OpportunityRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or OpportunityRepository(session)

    @staticmethod
    def _content_rules_enabled() -> bool | frozenset[str]:
        # F48-15 / F50-02: default OFF; a rule is switched on only after it passes the
        # precision gate on the labelled set.
        return get_settings().content_rules

    def normalize(self, raw_item_id: UUID) -> NormalizationResultModel:
        existing = self.repository.normalization_result(raw_item_id, NORMALIZER_VERSION)
        if existing is not None:
            return existing

        evidence = self.repository.raw_item_evidence(raw_item_id)
        if evidence is None:
            raise RawItemNotFoundError(str(raw_item_id))
        if evidence.raw_item.item_metadata.get("source_proposal_candidate") is True:
            result = NormalizationResultModel(
                raw_item_id=raw_item_id,
                status="FAILED",
                normalizer_version=NORMALIZER_VERSION,
                identity_decision=None,
                reasons=[{"code": "SOURCE_PROPOSAL_CANDIDATE"}],
                error_summary=(
                    "source proposal candidates await F20-46 and cannot become opportunities"
                ),
            )
            self.session.add(result)
            self.session.commit()
            self.session.refresh(result)
            return result
        existing = self.repository.normalization_result(raw_item_id, NORMALIZER_VERSION)
        if existing is not None:
            return existing

        cosmetic_result = self._short_circuit_cosmetic_change(evidence.raw_item)
        if cosmetic_result is not None:
            return cosmetic_result
        try:
            normalization_input = _normalization_input(evidence)
            candidate = build_candidate(
                normalization_input, content_rules=self._content_rules_enabled()
            )
            if candidate.classification_reasons:
                # F48-15: seniority-v4 first (it replaces the v3 reason), then the
                # work-mode and allowed-countries evidence.
                seniority_reason, *content_reasons = candidate.classification_reasons
            else:
                _, seniority_reason = seniority_classification(
                    normalization_input.title,
                    normalization_input.metadata,
                    source_type=normalization_input.source_type,
                )
                content_reasons = []
        except PayloadExpiredError as error:
            result = NormalizationResultModel(
                raw_item_id=raw_item_id,
                status="FAILED",
                normalizer_version=NORMALIZER_VERSION,
                identity_decision=None,
                reasons=[{"code": "PAYLOAD_EXPIRED_RECOLLECTION_REQUIRED"}],
                error_summary=str(error),
            )
            self.session.add(result)
            self.session.commit()
            self.session.refresh(result)
            return result
        except (NormalizationError, TypeError, ValueError) as error:
            result = NormalizationResultModel(
                raw_item_id=raw_item_id,
                status="FAILED",
                normalizer_version=NORMALIZER_VERSION,
                identity_decision=None,
                reasons=[{"code": "INVALID_COLLECTED_ITEM_V1"}],
                error_summary=str(error),
            )
            self.session.add(result)
            self.session.commit()
            self.session.refresh(result)
            return result

        raw_item = evidence.raw_item
        external_id = _clean_optional(normalization_input.external_id)
        identity_locks = {f"fingerprint:{candidate.fingerprint_version}:{candidate.fingerprint}"}
        if external_id:
            identity_locks.add(f"external:{raw_item.source_definition_id}:{external_id}")
        if candidate.normalized_url:
            identity_locks.add(f"url:{candidate.normalized_url}")
        company_key = (
            str(candidate.company_id) if candidate.company_id else candidate.normalized_company_name
        )
        if company_key:
            identity_locks.add(f"review:{company_key}:{candidate.normalized_title}")
        self.repository.lock_candidate_identities(identity_locks)
        refresh_changed = False
        occurrence = self.repository.occurrence_by_external_identity(
            source_definition_id=raw_item.source_definition_id,
            external_id=external_id,
            normalized_url=candidate.normalized_url,
        )
        content_is_current = True
        created_opportunity = False
        if occurrence is not None:
            opportunity = occurrence.opportunity
            current_raw_item = self.session.get(RawItemModel, occurrence.raw_item_id)
            content_is_current = (
                current_raw_item is None
                or raw_item.fetched_at >= current_raw_item.fetched_at
            )
            previous_fingerprint = opportunity.fingerprint
            identity_changed = (
                previous_fingerprint != candidate.fingerprint
                or opportunity.fingerprint_version != candidate.fingerprint_version
            )
            # F48-09: the source's `external_id` *is* the identity. A new fingerprint for it
            # refreshes the opportunity; only another opportunity already owning that
            # fingerprint is a real dispute (the unique index would refuse it anyway).
            competing = (
                self.repository.opportunity_by_fingerprint(
                    fingerprint=candidate.fingerprint,
                    fingerprint_version=candidate.fingerprint_version,
                )
                if identity_changed
                else None
            )
            reasons: list[dict[str, Any]]
            if competing is not None and competing.id != opportunity.id:
                decision = "REVIEW"
                result_status = "REVIEW_REQUIRED"
                reasons = [
                    {
                        "code": "EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED",
                        "competing_opportunity_id": str(competing.id),
                        "candidate_fingerprint": candidate.fingerprint,
                        "candidate_fingerprint_version": candidate.fingerprint_version,
                    }
                ]
            else:
                decision = "REFRESHED"
                result_status = "SUCCEEDED"
                reasons = [{"code": "SAME_SOURCE_EXTERNAL_IDENTITY"}]
                if content_is_current:
                    refresh_changed = _refresh_opportunity(opportunity, candidate)
                    if opportunity.fingerprint != previous_fingerprint:
                        reasons = [{"code": "IDENTITY_REFRESHED_SAME_EXTERNAL_ID"}]
                        opportunity.closure_evidence = {
                            **(opportunity.closure_evidence or {}),
                            "identity_refresh": {
                                "previous_fingerprint": previous_fingerprint,
                                "fingerprint": opportunity.fingerprint,
                                "raw_item_id": str(raw_item.id),
                                "at": raw_item.fetched_at.isoformat(),
                            },
                        }
            if content_is_current:
                occurrence.raw_item_id = raw_item.id
                occurrence.source_url = candidate.source_url
                occurrence.normalized_source_url = candidate.normalized_url
                occurrence.last_seen_at = raw_item.fetched_at
                occurrence.last_seen_run_id = raw_item.source_run_id
                occurrence.source_published_at = candidate.published_at
                occurrence.source_updated_at = candidate.source_updated_at
                occurrence.source_valid_through = candidate.valid_through
        else:
            url_match = self.repository.opportunity_by_normalized_url(candidate.normalized_url)
            if url_match is not None:
                opportunity = url_match
                decision = "MERGED"
                result_status = "SUCCEEDED"
                reasons = [{"code": "SAME_NORMALIZED_URL"}]
            else:
                fingerprint_match = self.repository.opportunity_by_fingerprint(
                    fingerprint=candidate.fingerprint,
                    fingerprint_version=candidate.fingerprint_version,
                )
                if fingerprint_match is not None:
                    opportunity = fingerprint_match
                    decision = "MERGED"
                    result_status = "SUCCEEDED"
                    reasons = [{"code": "EXACT_VERSIONED_FINGERPRINT"}]
                else:
                    review_candidates = self.repository.identity_review_candidates(candidate)
                    opportunity = _new_opportunity(candidate, first_seen_at=raw_item.fetched_at)
                    self.session.add(opportunity)
                    created_opportunity = True
                    if review_candidates:
                        decision = "REVIEW"
                        result_status = "REVIEW_REQUIRED"
                        reasons = [
                            {
                                "code": "SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY",
                                "candidate_opportunity_ids": [
                                    str(item.id) for item in review_candidates
                                ],
                            }
                        ]
                    else:
                        decision = "NEW"
                        result_status = "SUCCEEDED"
                        reasons = [{"code": "NO_IDENTITY_MATCH"}]
            occurrence = SourceOccurrenceModel(
                opportunity=opportunity,
                raw_item_id=raw_item.id,
                source_definition_id=raw_item.source_definition_id,
                external_id=external_id,
                source_url=candidate.source_url,
                normalized_source_url=candidate.normalized_url,
                first_seen_at=raw_item.fetched_at,
                last_seen_at=raw_item.fetched_at,
                last_seen_run_id=raw_item.source_run_id,
                source_published_at=candidate.published_at,
                source_updated_at=candidate.source_updated_at,
                source_valid_through=candidate.valid_through,
            )
            self.session.add(occurrence)

        self.session.flush()
        enrichment_before = _enrichment_state(opportunity)
        enrichment_reasons = (
            _reconcile_enrichment(
                opportunity=opportunity,
                occurrence=occurrence,
                candidate=candidate,
                raw_item_id=raw_item.id,
            )
            if content_is_current
            else []
        )
        enrichment_changed = enrichment_before != _enrichment_state(opportunity)
        if enrichment_reasons:
            reasons.extend(enrichment_reasons)
            result_status = "REVIEW_REQUIRED"
        search_skills = _search_skills_text(opportunity.skills)
        search_skills_changed = opportunity.search_skills != search_skills
        opportunity.search_skills = search_skills

        # REFRESHED already bumps in `_refresh_opportunity`; do not bump twice.
        if (
            decision != "NEW"
            and not refresh_changed
            and (enrichment_changed or search_skills_changed)
        ):
            opportunity.version += 1

        if created_opportunity:
            # F20-26 / F48-09: a brand-new opportunity is the only case that introduces a
            # fresh duplicate pair — REFRESHED/MERGED reuse one already checked when created.
            # `REVIEW` (same company and title, other identity) also creates one and is where
            # a republished pair arrives; candidates stay PENDING, never auto-merged.
            find_title_location_window_candidates(self.session, opportunity)

        result = NormalizationResultModel(
            raw_item_id=raw_item.id,
            opportunity=opportunity,
            source_occurrence=occurrence,
            status=result_status,
            normalizer_version=NORMALIZER_VERSION,
            identity_decision=decision,
            reasons=[*reasons, seniority_reason, *content_reasons],
        )
        self.session.add(result)
        self.session.execute(
            update(SourceOccurrenceObservationModel)
            .where(
                SourceOccurrenceObservationModel.raw_item_id == raw_item.id,
                SourceOccurrenceObservationModel.source_occurrence_id.is_(None),
            )
            .values(source_occurrence_id=occurrence.id)
        )
        self._advance_occurrence_presence_from_observations(occurrence)
        self.session.commit()
        self.session.refresh(result)
        return result

    def _short_circuit_cosmetic_change(
        self, raw_item: RawItemModel
    ) -> NormalizationResultModel | None:
        """Record a cosmetic republish without re-running derived analysis."""
        if raw_item.semantic_hash is None or raw_item.semantic_hash_version is None:
            return None
        occurrence = self.repository.occurrence_by_external_identity(
            source_definition_id=raw_item.source_definition_id,
            external_id=raw_item.external_id,
            normalized_url=raw_item.canonical_url,
        )
        if occurrence is None or occurrence.raw_item_id == raw_item.id:
            return None
        previous = self.session.get(RawItemModel, occurrence.raw_item_id)
        if previous is None:
            return None
        previous_result = self.repository.normalization_result(previous.id, NORMALIZER_VERSION)
        if (
            previous.semantic_hash != raw_item.semantic_hash
            or previous.semantic_hash_version != raw_item.semantic_hash_version
            or previous.item_metadata.get("parser_version")
            != raw_item.item_metadata.get("parser_version")
            or previous_result is None
            or previous_result.status != "SUCCEEDED"
        ):
            return None
        # Replays can arrive after a newer fetch. Do not replace its current evidence.
        if raw_item.fetched_at is not None and raw_item.fetched_at > previous.fetched_at:
            occurrence.raw_item_id = raw_item.id
        result = NormalizationResultModel(
            raw_item_id=raw_item.id,
            opportunity=occurrence.opportunity,
            source_occurrence=occurrence,
            status="SUCCEEDED",
            normalizer_version=NORMALIZER_VERSION,
            identity_decision="REFRESHED",
            reasons=[{"code": "COSMETIC_CHANGE_SEMANTIC_HASH_UNCHANGED"}],
        )
        self.session.add(result)
        self.session.execute(
            update(SourceOccurrenceObservationModel)
            .where(
                SourceOccurrenceObservationModel.raw_item_id == raw_item.id,
                SourceOccurrenceObservationModel.source_occurrence_id.is_(None),
            )
            .values(source_occurrence_id=occurrence.id)
        )
        self._advance_occurrence_presence_from_observations(occurrence)
        self.session.commit()
        self.session.refresh(result)
        return result

    def _advance_occurrence_presence_from_observations(
        self, occurrence: SourceOccurrenceModel
    ) -> None:
        """Keep presence separate from whichever raw item currently supplies content."""
        latest = self.session.execute(
            select(
                SourceOccurrenceObservationModel.observed_at,
                SourceOccurrenceObservationModel.source_run_id,
            )
            .where(SourceOccurrenceObservationModel.source_occurrence_id == occurrence.id)
            .order_by(SourceOccurrenceObservationModel.observed_at.desc())
            .limit(1)
        ).one_or_none()
        if latest is not None and latest.observed_at > occurrence.last_seen_at:
            occurrence.last_seen_at = latest.observed_at
            occurrence.last_seen_run_id = latest.source_run_id

    def normalize_run(
        self, source_run_id: UUID
    ) -> list[tuple[RawItemModel, NormalizationResultModel]]:
        """Normalize what one run preserved, and answer item by item.

        The manual intake needs this shape: an operator who submitted three inputs wants
        to know what became of each, not how the whole backlog moved. Normalization is
        idempotent per raw item, so asking twice returns the recorded outcome.
        A run that preserved nothing — every input already known — answers an empty list.
        """
        if self.session.get(SourceRunModel, source_run_id) is None:
            raise SourceRunNotFoundError(source_run_id)
        return [
            (raw_item, self.normalize(raw_item.id))
            for raw_item in self.repository.run_raw_items(source_run_id)
        ]

    def normalize_pending(self, limit: int = 100) -> NormalizationBatch:
        if limit < 1 or limit > 500:
            raise ValueError("normalization batch limit must be between 1 and 500")
        results = [
            self.normalize(raw_item_id)
            for raw_item_id in self.repository.pending_raw_item_ids(limit, NORMALIZER_VERSION)
        ]
        return NormalizationBatch(
            processed=len(results),
            succeeded=sum(item.status == "SUCCEEDED" for item in results),
            review_required=sum(item.status == "REVIEW_REQUIRED" for item in results),
            failed=sum(item.status == "FAILED" for item in results),
        )

    def reconcile_run_closures(self, source_run_id: UUID) -> None:
        """Close jobs that vanished for two complete runs in a row, and reopen ones back.

        Only a complete run may change anything here: a partial or failed run tells us
        nothing about what the board still has, so absence from it is not evidence.
        """
        run = self.session.get(SourceRunModel, source_run_id)
        if run is None:
            raise SourceRunNotFoundError(source_run_id)
        if not run.complete:
            return
        source_definition_id = run.source_definition_id

        for occurrence in self.repository.occurrences_seen_in_run(
            source_definition_id, source_run_id
        ):
            opportunity = occurrence.opportunity
            if opportunity.lifecycle_status != OpportunityStatus.CLOSED.value:
                continue
            opportunity.lifecycle_status = OpportunityStatus.ACTIVE.value
            opportunity.closure_evidence = {
                **(opportunity.closure_evidence or {}),
                "reopened_by_run_id": str(source_run_id),
            }
            opportunity.version += 1

        previous_run_id = self.repository.previous_complete_run_id(
            source_definition_id, before_run_id=source_run_id
        )
        if previous_run_id is not None:
            for occurrence in self.repository.occurrences_missing_from_both_runs(
                source_definition_id,
                current_run_id=source_run_id,
                previous_complete_run_id=previous_run_id,
            ):
                opportunity = occurrence.opportunity
                current_status = OpportunityStatus(opportunity.lifecycle_status)
                if current_status is OpportunityStatus.CLOSED:
                    continue
                if not current_status.can_transition_to(OpportunityStatus.CLOSED):
                    continue
                # F48-11: a vanished occurrence closes nothing while another one
                # (in this or any source) is still live in its own source's latest
                # complete run.
                self.session.flush()
                if self.repository.opportunity_is_open_at_source(opportunity.id):
                    continue
                opportunity.lifecycle_status = OpportunityStatus.CLOSED.value
                opportunity.closure_evidence = {
                    "closed_by_run_ids": [str(previous_run_id), str(source_run_id)],
                }
                opportunity.version += 1

        self.session.commit()

    def mark_relevance(
        self,
        opportunity_id: UUID,
        *,
        relevant: bool,
        reason: str | None,
        note: str | None,
        profile_version_id: UUID | None,
    ) -> RelevanceMarkModel:
        """Record an operator judgement. Out of scope: it never feeds score or verdict."""
        opportunity = self.repository.get(opportunity_id)
        if opportunity is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        mark = self.repository.add_relevance_mark(
            opportunity_id,
            relevant=relevant,
            reason=reason,
            note=note,
            profile_version_id=profile_version_id,
        )
        self.session.commit()
        return mark

    def transition(
        self,
        opportunity_id: UUID,
        *,
        target: OpportunityStatus,
        expected_version: int,
    ) -> OpportunityModel:
        opportunity = self.repository.get(opportunity_id)
        if opportunity is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        if opportunity.version != expected_version:
            raise OpportunityVersionConflictError("opportunity version is stale")
        current = OpportunityStatus(opportunity.lifecycle_status)
        current.require_transition_to(target)
        updated_id = self.session.scalar(
            update(OpportunityModel)
            .where(
                OpportunityModel.id == opportunity_id,
                OpportunityModel.version == expected_version,
            )
            .values(
                lifecycle_status=target.value,
                version=OpportunityModel.version + 1,
            )
            .returning(OpportunityModel.id)
        )
        if updated_id is None:
            self.session.rollback()
            raise OpportunityVersionConflictError("opportunity version is stale")
        self.session.commit()
        updated = self.repository.get(opportunity_id)
        if updated is None:
            raise OpportunityNotFoundError(str(opportunity_id))
        return updated


def _reconcile_enrichment(
    *,
    opportunity: OpportunityModel,
    occurrence: SourceOccurrenceModel,
    candidate: CanonicalCandidate,
    raw_item_id: UUID,
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    compensation = candidate.compensation
    current_compensation = next(
        (item for item in opportunity.compensations if item.source_occurrence_id == occurrence.id),
        None,
    )
    if compensation is None:
        if current_compensation is not None:
            opportunity.compensations.remove(current_compensation)
    else:
        candidate_period = (compensation.period or CompensationPeriod.UNKNOWN).value
        candidate_gross_net = (compensation.gross_net or GrossNet.UNKNOWN).value
        if current_compensation is None:
            current_compensation = OpportunityCompensationModel(
                amount_min=compensation.minimum,
                amount_max=compensation.maximum,
                currency=compensation.currency,
                period=candidate_period,
                gross_net=candidate_gross_net,
                evidence_text=compensation.evidence,
                evidence_source=compensation.evidence_source,
                normalizer_version=NORMALIZER_VERSION,
                source_occurrence_id=occurrence.id,
                raw_item_id=raw_item_id,
            )
            opportunity.compensations.append(current_compensation)
        else:
            current_compensation.amount_min = compensation.minimum
            current_compensation.amount_max = compensation.maximum
            current_compensation.currency = compensation.currency
            current_compensation.period = candidate_period
            current_compensation.gross_net = candidate_gross_net
            current_compensation.evidence_text = compensation.evidence
            current_compensation.evidence_source = compensation.evidence_source
            current_compensation.normalizer_version = NORMALIZER_VERSION
            current_compensation.raw_item_id = raw_item_id

        conflicts = [
            item
            for item in opportunity.compensations
            if item is not current_compensation
            and _compensation_conflicts(current_compensation, item)
        ]
        if conflicts:
            reasons.append(
                {
                    "code": "CONFLICTING_COMPENSATION_EVIDENCE",
                    "current": _compensation_reason(current_compensation),
                    "conflicts": [_compensation_reason(item) for item in conflicts],
                }
            )

    _reconcile_skills(
        opportunity=opportunity,
        occurrence=occurrence,
        candidate=candidate,
        raw_item_id=raw_item_id,
    )
    return reasons


def _reconcile_skills(
    *,
    opportunity: OpportunityModel,
    occurrence: SourceOccurrenceModel,
    candidate: CanonicalCandidate,
    raw_item_id: UUID,
) -> None:
    """Replace what this occurrence says about the opportunity's skills with `candidate`'s."""
    occurrence_key = str(occurrence.id)
    candidate_skill_keys = {
        (skill.canonical_id, skill.taxonomy_version) for skill in candidate.skills
    }
    for skill in list(opportunity.skills):
        skill.evidence = [
            item
            for item in skill.evidence
            if not (
                isinstance(item, Mapping) and item.get("source_occurrence_id") == occurrence_key
            )
        ]
        skill_key = (skill.canonical_name, skill.taxonomy_version)
        if not skill.evidence and skill_key not in candidate_skill_keys:
            opportunity.skills.remove(skill)
        else:
            _refresh_skill_requirement(skill)
    by_key = {(skill.canonical_name, skill.taxonomy_version): skill for skill in opportunity.skills}
    for extracted in candidate.skills:
        evidence = {
            "raw_item_id": str(raw_item_id),
            "source_occurrence_id": str(occurrence.id),
            "text": extracted.evidence_text,
            "requirement": extracted.classification.value,
        }
        key = (extracted.canonical_id, extracted.taxonomy_version)
        current_skill = by_key.get(key)
        if current_skill is None:
            current_skill = OpportunitySkillModel(
                canonical_name=extracted.canonical_id,
                display_name=extracted.canonical_id,
                requirement=extracted.classification.value,
                evidence=[evidence],
                taxonomy_version=extracted.taxonomy_version,
                normalizer_version=NORMALIZER_VERSION,
            )
            opportunity.skills.append(current_skill)
            by_key[key] = current_skill
            continue
        current_skill.evidence = [*current_skill.evidence, evidence]
        _refresh_skill_requirement(current_skill)
        current_skill.normalizer_version = NORMALIZER_VERSION


def _enrichment_state(opportunity: OpportunityModel) -> tuple[object, ...]:
    """Snapshot every field `_reconcile_enrichment` can change for versioning."""
    compensations = tuple(
        (
            item.amount_min,
            item.amount_max,
            item.currency,
            item.period,
            item.gross_net,
            item.evidence_text,
            item.evidence_source,
            item.normalizer_version,
            item.source_occurrence_id,
            item.raw_item_id,
        )
        for item in opportunity.compensations
    )
    skills = tuple(
        (
            item.canonical_name,
            item.display_name,
            item.requirement,
            item.evidence,
            item.taxonomy_version,
            item.normalizer_version,
        )
        for item in opportunity.skills
    )
    return compensations, skills


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
    if left.currency is not None and right.currency is not None and left.currency != right.currency:
        return True
    if (
        left.period != CompensationPeriod.UNKNOWN.value
        and right.period != CompensationPeriod.UNKNOWN.value
        and left.period != right.period
    ):
        return True
    return (
        left.gross_net != GrossNet.UNKNOWN.value
        and right.gross_net != GrossNet.UNKNOWN.value
        and left.gross_net != right.gross_net
    )


def _refresh_skill_requirement(skill: OpportunitySkillModel) -> None:
    classifications = {
        str(item.get("requirement"))
        for item in skill.evidence
        if isinstance(item, Mapping)
        and item.get("requirement") not in {None, SkillClassification.UNKNOWN.value}
    }
    skill.requirement = (
        classifications.pop() if len(classifications) == 1 else SkillClassification.UNKNOWN.value
    )


def _compensation_reason(value: OpportunityCompensationModel) -> dict[str, Any]:
    return {
        "minimum": str(value.amount_min) if value.amount_min is not None else None,
        "maximum": str(value.amount_max) if value.amount_max is not None else None,
        "currency": value.currency,
        "period": value.period,
        "gross_net": value.gross_net,
        "evidence_source": value.evidence_source,
        "source_occurrence_id": str(value.source_occurrence_id),
        "raw_item_id": str(value.raw_item_id),
    }


def _normalization_input(evidence: RawItemEvidence) -> NormalizationInput:
    snapshot = evidence.raw_item.item_metadata.get(COLLECTED_ITEM_V1_KEY)
    if not isinstance(snapshot, Mapping):
        snapshot = _legacy_collected_item_v1(evidence)
    if snapshot.get("version") != 1:
        raise NormalizationError("raw item has an unsupported collected item version")
    if snapshot.get("source_type") != evidence.source_type:
        raise NormalizationError("collected_item_v1 source type does not match RawItem")
    metadata = snapshot.get("metadata", {})
    if not isinstance(metadata, Mapping):
        raise NormalizationError("collected_item_v1 metadata must be an object")
    external_id = _optional_string(snapshot, "external_id")
    url = _optional_string(snapshot, "url")
    if external_id != evidence.raw_item.external_id or url != evidence.raw_item.canonical_url:
        raise NormalizationError("collected_item_v1 identity does not match RawItem")
    return NormalizationInput(
        raw_item_id=evidence.raw_item.id,
        source_definition_id=evidence.raw_item.source_definition_id,
        source_type=evidence.source_type,
        external_id=external_id,
        url=url,
        title=_optional_string(snapshot, "title"),
        company_name=_optional_string(snapshot, "company_name"),
        location_text=_optional_string(snapshot, "location_text"),
        description=_optional_string(snapshot, "description"),
        published_at=_optional_datetime(snapshot, "published_at"),
        updated_at=_optional_datetime(snapshot, "updated_at"),
        valid_through=_optional_datetime(snapshot, "valid_through"),
        company_id=evidence.company_id,
        metadata=dict(metadata),
    )


def _legacy_collected_item_v1(evidence: RawItemEvidence) -> dict[str, Any]:
    """Adapt pre-contract RawItems without changing their immutable evidence."""
    raw_item = evidence.raw_item
    payload = raw_item.payload
    if payload is None:
        # Only pre-contract items reach here, and only they can be unreadable: retention
        # expires the body, so the adapter says so rather than reading an empty object,
        # or guessing at fields it can no longer see.
        raise PayloadExpiredError(
            "raw item payload is no longer retained by retention; it cannot be "
            "reconstructed by guesswork — a fresh collection of the same source is "
            "the only way to reprocess this item"
        )
    metadata = dict(raw_item.item_metadata)
    metadata.pop(COLLECTED_ITEM_V1_KEY, None)
    company_name = evidence.company_name or _mapping_string(
        evidence.source_configuration, "company_name"
    )
    title: str | None = None
    location_text: str | None = None
    description: str | None = None
    published_at: str | None = None
    updated_at: str | None = None

    if evidence.source_type == "ashby":
        title = _mapping_string(payload, "title")
        location_text = _mapping_string(payload, "location")
        description = _mapping_string(payload, "descriptionPlain")
        published_at = _mapping_string(payload, "publishedAt")
    elif evidence.source_type == "lever":
        title = _mapping_string(payload, "text")
        categories = payload.get("categories")
        if isinstance(categories, Mapping):
            location_text = _mapping_string(categories, "location")
        description = _mapping_string(payload, "descriptionPlain")
    elif evidence.source_type == "greenhouse":
        title = _mapping_string(payload, "title")
        location = payload.get("location")
        if isinstance(location, Mapping):
            location_text = _mapping_string(location, "name")
        description = _mapping_string(payload, "content")
        updated_at = _mapping_string(payload, "updated_at")
    elif evidence.source_type == "remotive":
        title = _mapping_string(payload, "title")
        company_name = _mapping_string(payload, "company_name") or company_name
        location_text = _mapping_string(payload, "candidate_required_location")
        description = _mapping_string(payload, "description")
        published_at = _mapping_string(payload, "publication_date")
    elif evidence.source_type == "manual":
        title = _mapping_string(metadata, "title")
        company_name = _mapping_string(metadata, "company_name") or company_name
        location_text = _mapping_string(metadata, "location_text")
        description = _mapping_string(payload, "text")
        encoded_content = _mapping_string(payload, "content_base64")
        if description is None and encoded_content is not None:
            try:
                description = b64decode(encoded_content, validate=True).decode(
                    "utf-8", errors="replace"
                )
            except (Base64Error, ValueError) as error:
                raise NormalizationError("legacy manual file content_base64 is invalid") from error
    else:
        raise NormalizationError(f"raw item from {evidence.source_type} requires collected_item_v1")

    return {
        "version": 1,
        "source_type": evidence.source_type,
        "external_id": raw_item.external_id,
        "url": raw_item.canonical_url,
        "title": title,
        "company_name": company_name,
        "location_text": location_text,
        "description": description,
        "published_at": published_at,
        "updated_at": updated_at,
        "metadata": metadata,
    }


def _mapping_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    return item if isinstance(item, str) else None


def _optional_string(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise NormalizationError(f"collected_item_v1 {key} must be a string")
    return item


def _optional_datetime(value: Mapping[str, Any], key: str) -> datetime | None:
    item = _optional_string(value, key)
    if item is None:
        return None
    try:
        parsed = datetime.fromisoformat(item.replace("Z", "+00:00"))
    except ValueError as error:
        raise NormalizationError(f"collected_item_v1 {key} must be an ISO datetime") from error
    if parsed.tzinfo is None:
        # Card F48-03 (decision 9): a date without a timezone is not evidence of a moment,
        # and inventing UTC would shift it by hours. The item keeps every other field and
        # recency falls back to the collection date, instead of failing the whole item.
        logger.warning(
            "collected_item_v1 datetime without timezone dropped",
            extra={"field": key},
        )
        return None
    return parsed


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _latest_occurrence_departments(session: Session, opportunity_id: UUID) -> tuple[str, ...]:
    """Departments from the raw item of the occurrence last seen, per the card's notes."""
    occurrence = session.execute(
        select(SourceOccurrenceModel)
        .where(SourceOccurrenceModel.opportunity_id == opportunity_id)
        .order_by(SourceOccurrenceModel.last_seen_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if occurrence is None:
        return ()
    raw_item = session.get(RawItemModel, occurrence.raw_item_id)
    if raw_item is None:
        return ()
    snapshot = raw_item.item_metadata.get(COLLECTED_ITEM_V1_KEY)
    if not isinstance(snapshot, Mapping):
        return ()
    metadata = snapshot.get("metadata")
    if not isinstance(metadata, Mapping):
        return ()
    return departments_from_metadata(metadata)


def reclassify_role_families(session: Session, *, batch_size: int = 500) -> dict[str, int]:
    """Classify every opportunity not yet on `ROLE_FAMILY_VERSION`.

    Card F17-02's retroactive job: title and department come from the RawItem
    `collected_item_v1` snapshot of the occurrence last seen, the same evidence
    normalization uses for a new item.
    """
    total = 0
    updated = 0
    unknown = 0
    query = (
        select(OpportunityModel.id)
        .where(
            OpportunityModel.role_family_version.is_(None)
            | (OpportunityModel.role_family_version != ROLE_FAMILY_VERSION)
        )
        .order_by(OpportunityModel.id)
    )
    for opportunity_id in session.scalars(query).all():
        opportunity = session.get(OpportunityModel, opportunity_id)
        if opportunity is None:
            continue
        total += 1
        departments = _latest_occurrence_departments(session, opportunity.id)
        decision = classify_role_family(
            title=opportunity.canonical_title,
            departments=departments,
            description=opportunity.description,
        )
        opportunity.role_family = decision.role_family.value
        opportunity.role_family_evidence = dict(decision.evidence) or None
        opportunity.role_family_version = decision.version
        updated += 1
        if decision.role_family is RoleFamily.UNKNOWN:
            unknown += 1
        if total % batch_size == 0:
            session.commit()
    session.commit()
    return {"total": total, "updated": updated, "unknown": unknown}


_CONTENT_FIELDS = ("seniority", "work_mode", "allowed_countries")
_CONTENT_REASON_CODES = {
    "SENIORITY_CLASSIFICATION": "seniority",
    "WORK_MODE_CLASSIFICATION": "work_mode",
    "ALLOWED_COUNTRIES_CLASSIFICATION": "allowed_countries",
}
_UNKNOWN_VALUE = "UNKNOWN"
_CONTENT_EXAMPLE_LIMIT = 50


def _content_values(
    seniority: str, work_mode: str, allowed_countries: Collection[str] | None
) -> dict[str, str]:
    return {
        "seniority": seniority,
        "work_mode": work_mode,
        "allowed_countries": ",".join(allowed_countries or ()) or _UNKNOWN_VALUE,
    }


def _content_rule(candidate: CanonicalCandidate, field: str) -> str | None:
    """The rule (or source) the candidate's evidence names for `field`, if it carries any."""
    for reason in candidate.classification_reasons:
        if _CONTENT_REASON_CODES.get(str(reason.get("code"))) == field:
            return reason.get("rule") or reason.get("source")
    return None


def reclassify_content(
    session: Session,
    *,
    rules: bool | frozenset[str],
    role_families: Collection[str] | None = None,
    batch_size: int = 500,
    limit: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Recompute seniority, work mode and allowed countries of existing opportunities (F50-02).

    The evidence is the one normalization uses: the `collected_item_v1` snapshot of the
    occurrence last seen, classified by `build_candidate` with the enabled `rules`. A
    posting whose values change gets them and its content evidence (the `reasons` of that
    raw item's normalization result) rewritten, and `version` bumped exactly once however
    many fields moved; one that does not change is not touched, so a second run reports
    zero changes. A new work mode also moves the fingerprint; if another opportunity owns the
    new one, the posting keeps its work mode and is reported under `fingerprint_collisions`
    (it keeps being reported on later runs). Each batch is its own transaction; without
    `apply` every batch rolls back and the report only says what an apply run would do.

    `allowed_countries_version` follows the value: it is rewritten only when the countries
    change, so a version label alone never costs a posting its evaluation.
    """
    if batch_size < 1:
        raise ValueError("batch size must be at least 1")
    repository = OpportunityRepository(session)
    query = select(OpportunityModel.id).where(OpportunityModel.description.is_not(None))
    if role_families is not None:
        query = query.where(OpportunityModel.role_family.in_(list(role_families)))
    query = query.order_by(OpportunityModel.id)
    if limit is not None:
        query = query.limit(limit)
    opportunity_ids = list(session.scalars(query).all())

    kinds = ("unchanged", "unknown_to_value", "value_to_other_value", "value_to_unknown")
    counts = {kind: Counter[str]() for kind in kinds}
    examples: dict[str, list[dict[str, Any]]] = {field: [] for field in _CONTENT_FIELDS}
    before = {field: Counter[str]() for field in _CONTENT_FIELDS}
    after = {field: Counter[str]() for field in _CONTENT_FIELDS}
    skipped = Counter[str]()
    changed_postings = 0
    evidence_rewritten = 0
    collisions = 0
    collision_examples: list[dict[str, Any]] = []
    # Who owns a (version, fingerprint) key as this run moves them; a dry run writes nothing,
    # so the run's own moves are tracked here to give both modes the same answer.
    owners: dict[tuple[str, str], UUID | None] = {}

    for start in range(0, len(opportunity_ids), batch_size):
        chunk = opportunity_ids[start : start + batch_size]
        try:
            for opportunity in session.scalars(
                select(OpportunityModel)
                .where(OpportunityModel.id.in_(chunk))
                .order_by(OpportunityModel.id)
            ).all():
                occurrence = session.scalar(
                    select(SourceOccurrenceModel)
                    .where(SourceOccurrenceModel.opportunity_id == opportunity.id)
                    .order_by(SourceOccurrenceModel.last_seen_at.desc())
                    .limit(1)
                )
                evidence = (
                    repository.raw_item_evidence(occurrence.raw_item_id) if occurrence else None
                )
                if occurrence is None or evidence is None:
                    skipped["no_evidence"] += 1
                    continue
                try:
                    candidate = build_candidate(
                        _normalization_input(evidence), content_rules=rules
                    )
                except (NormalizationError, TypeError, ValueError):
                    skipped["unreadable_evidence"] += 1
                    continue
                old = _content_values(
                    opportunity.seniority, opportunity.work_mode, opportunity.allowed_countries
                )
                new = _content_values(
                    candidate.seniority.value,
                    candidate.work_mode.value,
                    candidate.allowed_countries,
                )
                # A new work mode is a new fingerprint (F50-02 fix): refuse it when another
                # opportunity already owns that identity, and keep the posting's work mode.
                keep_work_mode = False
                if old["work_mode"] != new["work_mode"]:
                    key = (candidate.fingerprint_version, candidate.fingerprint)
                    if key in owners:
                        owner = owners[key]
                    else:
                        match = repository.opportunity_by_fingerprint(
                            fingerprint=candidate.fingerprint,
                            fingerprint_version=candidate.fingerprint_version,
                        )
                        owner = match.id if match is not None else None
                    if owner is not None and owner != opportunity.id:
                        keep_work_mode = True
                        collisions += 1
                        if len(collision_examples) < _CONTENT_EXAMPLE_LIMIT:
                            collision_examples.append(
                                {
                                    "id": str(opportunity.id),
                                    "competing_opportunity_id": str(owner),
                                    "old": old["work_mode"],
                                    "new": new["work_mode"],
                                }
                            )
                        new["work_mode"] = old["work_mode"]
                changed = False
                for field in _CONTENT_FIELDS:
                    before[field][old[field]] += 1
                    after[field][new[field]] += 1
                    if old[field] == new[field]:
                        counts["unchanged"][field] += 1
                        continue
                    changed = True
                    if old[field] == _UNKNOWN_VALUE:
                        kind = "unknown_to_value"
                    elif new[field] == _UNKNOWN_VALUE:
                        kind = "value_to_unknown"
                    else:
                        kind = "value_to_other_value"
                    counts[kind][field] += 1
                    if kind != "unknown_to_value" and len(examples[field]) < _CONTENT_EXAMPLE_LIMIT:
                        examples[field].append(
                            {
                                "id": str(opportunity.id),
                                "kind": kind,
                                "old": old[field],
                                "new": new[field],
                                "rule": _content_rule(candidate, field),
                            }
                        )
                if not changed:
                    continue
                changed_postings += 1
                moves_fingerprint = old["work_mode"] != new["work_mode"]
                if moves_fingerprint:
                    owners[(opportunity.fingerprint_version, opportunity.fingerprint)] = None
                    owners[(candidate.fingerprint_version, candidate.fingerprint)] = opportunity.id
                if not apply:
                    continue
                _apply_content_fields(opportunity, candidate, work_mode=not keep_work_mode)
                opportunity.version += 1
                if moves_fingerprint:
                    session.flush()
                result = repository.normalization_result(
                    occurrence.raw_item_id, NORMALIZER_VERSION
                )
                if result is not None:
                    # A kept work mode keeps the evidence that decided it.
                    rewritten = {
                        code
                        for code in _CONTENT_REASON_CODES
                        if not (keep_work_mode and code == "WORK_MODE_CLASSIFICATION")
                    }
                    result.reasons = [
                        reason
                        for reason in result.reasons
                        if not (isinstance(reason, Mapping) and reason.get("code") in rewritten)
                    ] + [
                        reason
                        for reason in candidate.classification_reasons
                        if reason.get("code") not in _CONTENT_REASON_CODES
                        or reason.get("code") in rewritten
                    ]
                    evidence_rewritten += 1
            if apply:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise

    return {
        "mode": "apply" if apply else "dry-run",
        "rules": "all" if rules is True else sorted(rules or ()),
        "role_families": sorted(role_families) if role_families is not None else None,
        "selected": len(opportunity_ids),
        "skipped": dict(skipped),
        "postings_changed": changed_postings,
        "version_bumps": changed_postings,
        "evidence_rewritten": evidence_rewritten if apply else None,
        "fingerprint_collisions": {"count": collisions, "examples": collision_examples},
        "fields": {
            field: {
                **{kind: counts[kind][field] for kind in kinds},
                "examples": examples[field],
                "distribution_before": dict(sorted(before[field].items())),
                "distribution_after": dict(sorted(after[field].items())),
            }
            for field in _CONTENT_FIELDS
        },
    }


def retag_skills(
    session: Session,
    *,
    batch_size: int = 500,
    limit: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Re-extract the skills of opportunities still tagged by an older taxonomy.

    The taxonomy version is stored on each skill row, so a new taxonomy only reaches a
    posting when it is normalized again. This redoes just the skills: for every opportunity
    with a skill row of another version, each of its occurrences is read from the evidence
    normalization uses and its skills are replaced, as normalization would. Nothing else
    about the posting is recomputed. An occurrence whose evidence is gone or unreadable
    keeps what it had said, so such a posting may keep old rows and is reported under
    `still_old`. A changed posting gets `search_skills` refreshed and `version` bumped once;
    a second run finds nothing to do for it. Each batch is its own transaction; without
    `apply` every batch rolls back.
    """
    if batch_size < 1:
        raise ValueError("batch size must be at least 1")
    repository = OpportunityRepository(session)
    query = (
        select(OpportunitySkillModel.opportunity_id)
        .where(OpportunitySkillModel.taxonomy_version != SKILL_TAXONOMY_VERSION)
        .distinct()
        .order_by(OpportunitySkillModel.opportunity_id)
    )
    if limit is not None:
        query = query.limit(limit)
    opportunity_ids = list(session.scalars(query).all())

    skipped = Counter[str]()
    rows_before = Counter[str]()
    rows_after = Counter[str]()
    changed = still_old = without_skills = 0
    for start in range(0, len(opportunity_ids), batch_size):
        chunk = opportunity_ids[start : start + batch_size]
        try:
            for opportunity in session.scalars(
                select(OpportunityModel)
                .where(OpportunityModel.id.in_(chunk))
                .order_by(OpportunityModel.id)
            ).all():
                rows_before.update(skill.taxonomy_version for skill in opportunity.skills)
                state = _enrichment_state(opportunity)[1]
                for occurrence in session.scalars(
                    select(SourceOccurrenceModel)
                    .where(SourceOccurrenceModel.opportunity_id == opportunity.id)
                    .order_by(SourceOccurrenceModel.id)
                ).all():
                    evidence = repository.raw_item_evidence(occurrence.raw_item_id)
                    if evidence is None:
                        skipped["no_evidence"] += 1
                        continue
                    try:
                        candidate = build_candidate(_normalization_input(evidence))
                    except (NormalizationError, TypeError, ValueError):
                        skipped["unreadable_evidence"] += 1
                        continue
                    _reconcile_skills(
                        opportunity=opportunity,
                        occurrence=occurrence,
                        candidate=candidate,
                        raw_item_id=occurrence.raw_item_id,
                    )
                rows_after.update(skill.taxonomy_version for skill in opportunity.skills)
                if any(
                    skill.taxonomy_version != SKILL_TAXONOMY_VERSION
                    for skill in opportunity.skills
                ):
                    still_old += 1
                if not opportunity.skills:
                    without_skills += 1
                if state != _enrichment_state(opportunity)[1]:
                    changed += 1
                    opportunity.search_skills = _search_skills_text(opportunity.skills)
                    opportunity.version += 1
            if apply:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise

    return {
        "mode": "apply" if apply else "dry-run",
        "taxonomy_version": SKILL_TAXONOMY_VERSION,
        "selected": len(opportunity_ids),
        "postings_changed": changed,
        "version_bumps": changed,
        "still_old": still_old,
        "left_without_skills": without_skills,
        "skipped_occurrences": dict(skipped),
        "skill_rows_before": dict(sorted(rows_before.items())),
        "skill_rows_after": dict(sorted(rows_after.items())),
    }


_SENIORITY_REASON_CODE = "SENIORITY_CLASSIFICATION"


def retag_seniority(
    session: Session,
    *,
    rules: bool | frozenset[str] = False,
    batch_size: int = 500,
    limit: int | None = None,
    apply: bool = False,
) -> dict[str, Any]:
    """Recompute the seniority of existing opportunities with the current mapping (F52-02).

    The mapping version lives in the evidence, not on the posting, so a new mapping only
    reaches a posting when it is normalized again. This redoes just the seniority, from the
    evidence normalization uses: the occurrence last seen, classified by `build_candidate`
    with the enabled `rules`. A posting whose level changes gets it rewritten and `version`
    bumped once; the worker then evaluates it again. The seniority evidence (the
    `SENIORITY_CLASSIFICATION` reason of that raw item's normalization result) is rewritten
    whenever it differs, level changed or not, so the mapping version it names is the one
    that produced the value; that alone does not bump `version`. A second run reports zero
    changes. Each batch is its own transaction; without `apply` every batch rolls back.
    """
    if batch_size < 1:
        raise ValueError("batch size must be at least 1")
    repository = OpportunityRepository(session)
    query = select(OpportunityModel.id).order_by(OpportunityModel.id)
    if limit is not None:
        query = query.limit(limit)
    opportunity_ids = list(session.scalars(query).all())

    skipped = Counter[str]()
    before = Counter[str]()
    after = Counter[str]()
    transitions = Counter[str]()
    examples: list[dict[str, Any]] = []
    changed = evidence_rewritten = 0
    for start in range(0, len(opportunity_ids), batch_size):
        chunk = opportunity_ids[start : start + batch_size]
        try:
            for opportunity in session.scalars(
                select(OpportunityModel)
                .where(OpportunityModel.id.in_(chunk))
                .order_by(OpportunityModel.id)
            ).all():
                occurrence = session.scalar(
                    select(SourceOccurrenceModel)
                    .where(SourceOccurrenceModel.opportunity_id == opportunity.id)
                    .order_by(SourceOccurrenceModel.last_seen_at.desc())
                    .limit(1)
                )
                evidence = (
                    repository.raw_item_evidence(occurrence.raw_item_id) if occurrence else None
                )
                if occurrence is None or evidence is None:
                    skipped["no_evidence"] += 1
                    continue
                try:
                    normalization_input = _normalization_input(evidence)
                    candidate = build_candidate(normalization_input, content_rules=rules)
                except (NormalizationError, TypeError, ValueError):
                    skipped["unreadable_evidence"] += 1
                    continue
                reason = next(
                    (
                        dict(item)
                        for item in candidate.classification_reasons
                        if item.get("code") == _SENIORITY_REASON_CODE
                    ),
                    None,
                )
                if reason is None:
                    _, reason = seniority_classification(
                        normalization_input.title,
                        normalization_input.metadata,
                        source_type=normalization_input.source_type,
                    )
                old, new = opportunity.seniority, candidate.seniority.value
                before[old] += 1
                after[new] += 1
                if old != new:
                    changed += 1
                    transitions[f"{old}->{new}"] += 1
                    if len(examples) < _CONTENT_EXAMPLE_LIMIT:
                        examples.append(
                            {
                                "id": str(opportunity.id),
                                "title": opportunity.canonical_title,
                                "old": old,
                                "new": new,
                                "range": reason.get("range"),
                            }
                        )
                    opportunity.seniority = new
                    opportunity.version += 1
                result = repository.normalization_result(
                    occurrence.raw_item_id, NORMALIZER_VERSION
                )
                if result is None:
                    continue
                stored = [
                    item
                    for item in result.reasons
                    if isinstance(item, Mapping) and item.get("code") == _SENIORITY_REASON_CODE
                ]
                if stored != [reason]:
                    # In place: the seniority reason keeps its position among the others.
                    kept: list[Any] = []
                    for item in result.reasons:
                        if isinstance(item, Mapping) and item.get("code") == _SENIORITY_REASON_CODE:
                            if reason not in kept:
                                kept.append(reason)
                        else:
                            kept.append(item)
                    result.reasons = kept if reason in kept else [*kept, reason]
                    evidence_rewritten += 1
            if apply:
                session.commit()
            else:
                session.rollback()
        except Exception:
            session.rollback()
            raise

    return {
        "mode": "apply" if apply else "dry-run",
        "mapping_version": SENIORITY_MAPPING_VERSION,
        "rules": "all" if rules is True else sorted(rules or ()),
        "selected": len(opportunity_ids),
        "skipped": dict(skipped),
        "postings_changed": changed,
        "version_bumps": changed,
        "evidence_rewritten": evidence_rewritten,
        "transitions": dict(sorted(transitions.items())),
        "distribution_before": dict(sorted(before.items())),
        "distribution_after": dict(sorted(after.items())),
        "examples": examples,
    }


def _search_skills_text(skills: list[OpportunitySkillModel]) -> str | None:
    """Denormalized skill names for `search_document` (F17-03): a generated column
    cannot read another table's rows, so this stays in sync here, on every
    normalization — first insert and every reprocessing alike."""
    names = sorted({skill.canonical_name.replace("_", " ") for skill in skills})
    return " ".join(names) or None


def _new_opportunity(candidate: CanonicalCandidate, *, first_seen_at: datetime) -> OpportunityModel:
    return OpportunityModel(
        fingerprint=candidate.fingerprint,
        fingerprint_version=candidate.fingerprint_version,
        canonical_title=candidate.original_title,
        normalized_title=candidate.normalized_title,
        canonical_company_id=candidate.company_id,
        company_name=candidate.company_name,
        normalized_company_name=candidate.normalized_company_name,
        location_text=candidate.location_text,
        normalized_location=candidate.normalized_location,
        work_mode=candidate.work_mode.value,
        seniority=candidate.seniority.value,
        contract_type=candidate.contract_type.value,
        description=candidate.description,
        lifecycle_status=OpportunityStatus.DISCOVERED.value,
        published_at=candidate.published_at,
        source_updated_at=candidate.source_updated_at,
        recency_basis=recency_basis_of(
            published_at=candidate.published_at,
            source_updated_at=candidate.source_updated_at,
        ).value,
        # Card F20-61: set once, from the same instant that seeds this opportunity's
        # first `SourceOccurrenceModel.first_seen_at` — never updated afterwards, so
        # it stays "when the radar first saw this", not "when it was last touched".
        first_seen_at=first_seen_at,
        valid_through=candidate.valid_through,
        recency_exempt_program=candidate.recency_exempt_program,
        role_family=candidate.role_family.value,
        role_family_evidence=dict(candidate.role_family_evidence) or None,
        role_family_version=candidate.role_family_version,
        allowed_countries=list(candidate.allowed_countries) or None,
        allowed_countries_version=(
            candidate.allowed_countries_version if candidate.allowed_countries else None
        ),
    )


def _set_if_changed(opportunity: OpportunityModel, field: str, value: Any) -> bool:
    if getattr(opportunity, field) == value:
        return False
    setattr(opportunity, field, value)
    return True


def _apply_rule_fields(opportunity: OpportunityModel, candidate: CanonicalCandidate) -> bool:
    """Recompute every rule-derived field, independent of source freshness.

    Card F17-06: "Reprocessar pela nova regra mesmo quando a fonte não fornece
    `source_updated_at`". Work mode, seniority, contract type, role area and allowed
    countries are rules applied to evidence the raw item already carries — a normalizer
    version bump must reach every raw item, `source_updated_at` or not. Returns whether
    anything actually changed, so an identical replay never claims a semantic change.
    """
    changed = False
    changed |= _set_if_changed(opportunity, "work_mode", candidate.work_mode.value)
    changed |= _set_if_changed(opportunity, "seniority", candidate.seniority.value)
    changed |= _set_if_changed(opportunity, "contract_type", candidate.contract_type.value)
    changed |= _set_if_changed(
        opportunity, "recency_exempt_program", candidate.recency_exempt_program
    )
    changed |= _set_if_changed(
        opportunity, "allowed_countries", list(candidate.allowed_countries) or None
    )
    changed |= _set_if_changed(
        opportunity,
        "allowed_countries_version",
        candidate.allowed_countries_version if candidate.allowed_countries else None,
    )
    changed |= _set_if_changed(opportunity, "role_family", candidate.role_family.value)
    changed |= _set_if_changed(
        opportunity,
        "role_family_evidence",
        dict(candidate.role_family_evidence) or None,
    )
    changed |= _set_if_changed(opportunity, "role_family_version", candidate.role_family_version)
    return changed


def _apply_content_fields(
    opportunity: OpportunityModel, candidate: CanonicalCandidate, *, work_mode: bool = True
) -> None:
    """Apply only the three description-aware fields (F50-02); the caller bumps `version`.

    Work mode is a fingerprint input, so it moves the fingerprint with it, to the value the
    candidate (hence a later normalization) carries; `work_mode=False` leaves both alone.
    """
    _set_if_changed(opportunity, "seniority", candidate.seniority.value)
    if work_mode and _set_if_changed(opportunity, "work_mode", candidate.work_mode.value):
        opportunity.fingerprint = candidate.fingerprint
        opportunity.fingerprint_version = candidate.fingerprint_version
    countries = list(candidate.allowed_countries) or None
    if _set_if_changed(opportunity, "allowed_countries", countries):
        opportunity.allowed_countries_version = (
            candidate.allowed_countries_version if countries else None
        )


def _apply_evidence_fields(opportunity: OpportunityModel, candidate: CanonicalCandidate) -> bool:
    """Apply the evidence-based fields (title, company, location, description,
    `published_at`/`source_updated_at`, fingerprint), gated by source freshness.

    Card F17-06: "Replay antigo não regride ... campos baseados em evidência mais
    recente". A candidate with no `source_updated_at` carries no ordering signal — the
    same raw item being reprocessed under a new rule, not a different, possibly older,
    one — so it applies normally. A candidate strictly older than what the opportunity
    already recorded is the one case this refuses: an out-of-order replay must never
    regress content a fresher raw item already established.
    """
    if (
        candidate.source_updated_at is not None
        and opportunity.source_updated_at is not None
        and candidate.source_updated_at < opportunity.source_updated_at
    ):
        return False
    changed = False
    changed |= _set_if_changed(opportunity, "canonical_title", candidate.original_title)
    changed |= _set_if_changed(opportunity, "normalized_title", candidate.normalized_title)
    changed |= _set_if_changed(opportunity, "canonical_company_id", candidate.company_id)
    changed |= _set_if_changed(opportunity, "company_name", candidate.company_name)
    changed |= _set_if_changed(
        opportunity, "normalized_company_name", candidate.normalized_company_name
    )
    changed |= _set_if_changed(opportunity, "location_text", candidate.location_text)
    changed |= _set_if_changed(opportunity, "normalized_location", candidate.normalized_location)
    changed |= _set_if_changed(opportunity, "description", candidate.description)
    changed |= _set_if_changed(opportunity, "published_at", candidate.published_at)
    changed |= _set_if_changed(opportunity, "source_updated_at", candidate.source_updated_at)
    changed |= _set_if_changed(
        opportunity,
        "recency_basis",
        recency_basis_of(
            published_at=candidate.published_at,
            source_updated_at=candidate.source_updated_at,
        ).value,
    )
    changed |= _set_if_changed(opportunity, "valid_through", candidate.valid_through)
    changed |= _set_if_changed(opportunity, "fingerprint", candidate.fingerprint)
    changed |= _set_if_changed(opportunity, "fingerprint_version", candidate.fingerprint_version)
    return changed


def _refresh_opportunity(opportunity: OpportunityModel, candidate: CanonicalCandidate) -> bool:
    """Reprocess one opportunity from a raw item's evidence.

    Two independent decisions, per the card's "Reprocessamento e limites semânticos":
    rule-derived fields always recompute; evidence-based fields only ever advance, never
    regress under an out-of-order replay. `version` — and therefore matching/index/vector
    invalidation — bumps only when a field's *value* actually changed, so an identical
    replay creates no reanalysis wave.
    """
    rules_changed = _apply_rule_fields(opportunity, candidate)
    evidence_changed = _apply_evidence_fields(opportunity, candidate)
    changed = rules_changed or evidence_changed
    if changed:
        opportunity.version += 1
    return changed
