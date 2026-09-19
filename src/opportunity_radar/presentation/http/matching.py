"""HTTP contract for deterministic, explainable matching."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.matching.models import MatchAssessmentModel, MatchFactorModel
from opportunity_radar.matching.service import (
    MatchNotFoundError,
    MatchOpportunityNotFoundError,
    MatchingService,
)
from opportunity_radar.presentation.http.dependencies import get_session
from opportunity_radar.profile.domain import ProfileNotFoundError

router = APIRouter(prefix="/matches", tags=["matching"])


class EvaluateMatchBody(BaseModel):
    opportunity_id: UUID
    profile_version_id: UUID | None = None


class MatchFactorResponse(BaseModel):
    factor_code: str
    weight: str
    raw_score: str | None
    contribution: str
    status: str
    confidence: str
    missing_policy: str
    explanation: str
    evidence_refs: list[Any]


class MatchAssessmentResponse(BaseModel):
    id: UUID
    opportunity_id: UUID
    opportunity_version: int
    profile_version_id: UUID
    input_hash: str
    rules_version: str
    taxonomy_version: str
    opportunity_snapshot: dict[str, Any]
    profile_snapshot: dict[str, Any]
    eligibility: str
    eligibility_details: list[Any]
    status: str
    verdict: str
    score: str
    confidence: str
    assessed_at: str
    created_at: str
    factors: list[MatchFactorResponse]


class MatchAssessmentListResponse(BaseModel):
    items: list[MatchAssessmentResponse]
    total: int
    offset: int
    limit: int


@router.post("/evaluate", response_model=MatchAssessmentResponse)
def evaluate_match(
    body: EvaluateMatchBody,
    session: Session = Depends(get_session),
) -> MatchAssessmentResponse:
    try:
        assessment = MatchingService(session).evaluate(
            body.opportunity_id,
            profile_version_id=body.profile_version_id,
        )
    except MatchOpportunityNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "opportunity_not_found",
                "message": "Opportunity not found.",
            },
        ) from error
    except ProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "profile_not_found", "message": str(error)},
        ) from error
    return _assessment_response(assessment)


@router.get("", response_model=MatchAssessmentListResponse)
def list_matches(
    opportunity_id: UUID | None = None,
    profile_version_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> MatchAssessmentListResponse:
    items, total = MatchingService(session).list(
        opportunity_id=opportunity_id,
        profile_version_id=profile_version_id,
        offset=offset,
        limit=limit,
    )
    return MatchAssessmentListResponse(
        items=[_assessment_response(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{assessment_id}", response_model=MatchAssessmentResponse)
def get_match(
    assessment_id: UUID,
    session: Session = Depends(get_session),
) -> MatchAssessmentResponse:
    try:
        return _assessment_response(MatchingService(session).get(assessment_id))
    except MatchNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "match_not_found", "message": "Match assessment not found."},
        ) from error


def _assessment_response(assessment: MatchAssessmentModel) -> MatchAssessmentResponse:
    return MatchAssessmentResponse(
        id=assessment.id,
        opportunity_id=assessment.opportunity_id,
        opportunity_version=assessment.opportunity_version,
        profile_version_id=assessment.profile_version_id,
        input_hash=assessment.input_hash,
        rules_version=assessment.rules_version,
        taxonomy_version=assessment.taxonomy_version,
        opportunity_snapshot=assessment.opportunity_snapshot,
        profile_snapshot=assessment.profile_snapshot,
        eligibility=assessment.eligibility,
        eligibility_details=assessment.eligibility_details,
        status=assessment.status,
        verdict=assessment.verdict,
        score=str(assessment.score),
        confidence=str(assessment.confidence),
        assessed_at=assessment.assessed_at.isoformat(),
        created_at=assessment.created_at.isoformat(),
        factors=[
            _factor_response(item)
            for item in sorted(assessment.factors, key=lambda value: value.factor_code)
        ],
    )


def _factor_response(factor: MatchFactorModel) -> MatchFactorResponse:
    return MatchFactorResponse(
        factor_code=factor.factor_code,
        weight=str(factor.weight),
        raw_score=str(factor.raw_score) if factor.raw_score is not None else None,
        contribution=str(factor.contribution),
        status=factor.status,
        confidence=str(factor.confidence),
        missing_policy=factor.missing_policy,
        explanation=factor.explanation,
        evidence_refs=factor.evidence_refs,
    )
