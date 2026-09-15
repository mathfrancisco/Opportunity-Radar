"""Normalize immutable acquisition evidence into canonical opportunities."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY
from opportunity_radar.opportunities.domain import (
    CanonicalCandidate,
    NormalizationError,
    NormalizationInput,
    OpportunityStatus,
    build_candidate,
)
from opportunity_radar.opportunities.models import (
    NormalizationResultModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.opportunities.repository import (
    OpportunityRepository,
    RawItemEvidence,
)

NORMALIZER_VERSION = "v1"


class RawItemNotFoundError(LookupError):
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

    def normalize(self, raw_item_id: UUID) -> NormalizationResultModel:
        existing = self.repository.normalization_result(
            raw_item_id, NORMALIZER_VERSION
        )
        if existing is not None:
            return existing

        evidence = self.repository.raw_item_evidence(raw_item_id)
        if evidence is None:
            raise RawItemNotFoundError(str(raw_item_id))
        existing = self.repository.normalization_result(
            raw_item_id, NORMALIZER_VERSION
        )
        if existing is not None:
            return existing
        try:
            normalization_input = _normalization_input(evidence)
            candidate = build_candidate(normalization_input)
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
        identity_locks = {
            f"fingerprint:{candidate.fingerprint_version}:{candidate.fingerprint}"
        }
        if external_id:
            identity_locks.add(
                f"external:{raw_item.source_definition_id}:{external_id}"
            )
        if candidate.normalized_url:
            identity_locks.add(f"url:{candidate.normalized_url}")
        company_key = (
            str(candidate.company_id)
            if candidate.company_id
            else candidate.normalized_company_name
        )
        if company_key:
            identity_locks.add(
                f"review:{company_key}:{candidate.normalized_title}"
            )
        self.repository.lock_candidate_identities(identity_locks)
        occurrence = self.repository.occurrence_by_external_identity(
            source_definition_id=raw_item.source_definition_id,
            external_id=external_id,
            normalized_url=candidate.normalized_url,
        )
        if occurrence is not None:
            opportunity = occurrence.opportunity
            if (
                opportunity.fingerprint == candidate.fingerprint
                and opportunity.fingerprint_version == candidate.fingerprint_version
            ):
                decision = "REFRESHED"
                result_status = "SUCCEEDED"
                reasons: list[dict[str, Any]] = [
                    {"code": "SAME_SOURCE_EXTERNAL_IDENTITY"}
                ]
                _refresh_opportunity(opportunity, candidate)
            else:
                decision = "REVIEW"
                result_status = "REVIEW_REQUIRED"
                reasons = [
                    {"code": "EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED"}
                ]
            occurrence.raw_item_id = raw_item.id
            occurrence.source_url = candidate.source_url
            occurrence.normalized_source_url = candidate.normalized_url
            occurrence.last_seen_at = raw_item.fetched_at
            occurrence.source_published_at = candidate.published_at
            occurrence.source_updated_at = candidate.source_updated_at
        else:
            url_match = self.repository.opportunity_by_normalized_url(
                candidate.normalized_url
            )
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
                    review_candidates = self.repository.identity_review_candidates(
                        candidate
                    )
                    opportunity = _new_opportunity(candidate)
                    self.session.add(opportunity)
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
                source_published_at=candidate.published_at,
                source_updated_at=candidate.source_updated_at,
            )
            self.session.add(occurrence)

        result = NormalizationResultModel(
            raw_item_id=raw_item.id,
            opportunity=opportunity,
            source_occurrence=occurrence,
            status=result_status,
            normalizer_version=NORMALIZER_VERSION,
            identity_decision=decision,
            reasons=reasons,
        )
        self.session.add(result)
        self.session.commit()
        self.session.refresh(result)
        return result

    def normalize_pending(self, limit: int = 100) -> NormalizationBatch:
        if limit < 1 or limit > 500:
            raise ValueError("normalization batch limit must be between 1 and 500")
        results = [
            self.normalize(raw_item_id)
            for raw_item_id in self.repository.pending_raw_item_ids(
                limit, NORMALIZER_VERSION
            )
        ]
        return NormalizationBatch(
            processed=len(results),
            succeeded=sum(item.status == "SUCCEEDED" for item in results),
            review_required=sum(
                item.status == "REVIEW_REQUIRED" for item in results
            ),
            failed=sum(item.status == "FAILED" for item in results),
        )

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
    if (
        external_id != evidence.raw_item.external_id
        or url != evidence.raw_item.canonical_url
    ):
        raise NormalizationError("collected_item_v1 identity does not match RawItem")
    return NormalizationInput(
        raw_item_id=evidence.raw_item.id,
        source_definition_id=evidence.raw_item.source_definition_id,
        external_id=external_id,
        url=url,
        title=_optional_string(snapshot, "title"),
        company_name=_optional_string(snapshot, "company_name"),
        location_text=_optional_string(snapshot, "location_text"),
        description=_optional_string(snapshot, "description"),
        published_at=_optional_datetime(snapshot, "published_at"),
        updated_at=_optional_datetime(snapshot, "updated_at"),
        company_id=evidence.company_id,
        metadata=dict(metadata),
    )


def _legacy_collected_item_v1(evidence: RawItemEvidence) -> dict[str, Any]:
    """Adapt pre-contract RawItems without changing their immutable evidence."""
    raw_item = evidence.raw_item
    payload = raw_item.payload
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
                raise NormalizationError(
                    "legacy manual file content_base64 is invalid"
                ) from error
    else:
        raise NormalizationError(
            f"raw item from {evidence.source_type} requires collected_item_v1"
        )

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
        raise NormalizationError(
            f"collected_item_v1 {key} must be an ISO datetime"
        ) from error
    if parsed.tzinfo is None:
        raise NormalizationError(f"collected_item_v1 {key} must include a timezone")
    return parsed


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _new_opportunity(candidate: CanonicalCandidate) -> OpportunityModel:
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
    )


def _refresh_opportunity(
    opportunity: OpportunityModel, candidate: CanonicalCandidate
) -> None:
    if candidate.source_updated_at is None:
        return
    if (
        opportunity.source_updated_at is not None
        and candidate.source_updated_at < opportunity.source_updated_at
    ):
        return
    opportunity.canonical_title = candidate.original_title
    opportunity.normalized_title = candidate.normalized_title
    opportunity.canonical_company_id = candidate.company_id
    opportunity.company_name = candidate.company_name
    opportunity.normalized_company_name = candidate.normalized_company_name
    opportunity.location_text = candidate.location_text
    opportunity.normalized_location = candidate.normalized_location
    opportunity.work_mode = candidate.work_mode.value
    opportunity.seniority = candidate.seniority.value
    opportunity.contract_type = candidate.contract_type.value
    opportunity.description = candidate.description
    opportunity.published_at = candidate.published_at
    opportunity.source_updated_at = candidate.source_updated_at
    opportunity.fingerprint = candidate.fingerprint
    opportunity.fingerprint_version = candidate.fingerprint_version
    opportunity.version += 1
