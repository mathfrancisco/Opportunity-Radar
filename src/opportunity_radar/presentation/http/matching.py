"""HTTP contract for deterministic, explainable matching."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.matching.analysis import (
    SemanticAnalysisPort,
    claim_text,
    item_evidence,
)
from opportunity_radar.matching.models import (
    MatchAnalysisModel,
    MatchAssessmentModel,
    MatchFactorModel,
)
from opportunity_radar.matching.service import (
    AnalysisInProgressError,
    MatchingService,
    MatchNotFoundError,
    MatchOpportunityNotFoundError,
)
from opportunity_radar.presentation.http.dependencies import (
    get_analysis_adapter,
    get_session,
)
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


class AnalysisMetricsResponse(BaseModel):
    total_ms: int | None
    load_ms: int | None
    prompt_tokens: int | None
    prompt_eval_ms: int | None
    output_tokens: int | None
    eval_ms: int | None
    prompt_chars: int | None = None
    prompt_tokens_estimate: int | None = None


class AnalysisClaimResponse(BaseModel):
    """An `analysis-v2` strength or risk: the claim and the passage behind it, if any."""

    claim: str
    evidence: str | None
    source: str | None


class AnalysisContextRefResponse(BaseModel):
    """A decided posting the prompt received as context (card F16-11), as it stood."""

    opportunity_id: UUID
    content_version: int | None = None
    decision: str
    decided_at: str | None = None
    similarity: float | None = None


class MatchAnalysisResponse(BaseModel):
    """Advisory layer. Carries no score, verdict or eligibility by construction.

    `strengths` and `risks` are strings under `analysis-v1` and claims with evidence from
    `analysis-v2` on; `schema_version` says which, and old rows stay readable as written.
    """

    id: UUID
    assessment_id: UUID
    status: str
    failure_code: str | None
    detail: str | None
    summary: str | None
    strengths: list[AnalysisClaimResponse | str]
    risks: list[AnalysisClaimResponse | str]
    inferences: list[str]
    unknowns: list[str]
    recommended_review: bool | None
    model_id: str | None
    prompt_version: str | None
    schema_version: str
    cache_key: str
    key_version: str | None = None
    payload_hash: str | None = None
    context_refs: list[AnalysisContextRefResponse] = []
    analyzed_at: str
    created_at: str
    metrics: AnalysisMetricsResponse | None = None



class AnalyzeMatchBody(BaseModel):
    refresh: bool = False


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
    is_stale: bool
    assessed_at: str
    created_at: str
    factors: list[MatchFactorResponse]
    analysis: MatchAnalysisResponse | None = None


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
        service = MatchingService(session)
        assessment = service.evaluate(
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
    return _assessment_response(assessment, is_stale=service.is_stale(assessment))


@router.get("", response_model=MatchAssessmentListResponse)
def list_matches(
    opportunity_id: UUID | None = None,
    profile_version_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> MatchAssessmentListResponse:
    service = MatchingService(session)
    items, total = service.list(
        opportunity_id=opportunity_id,
        profile_version_id=profile_version_id,
        offset=offset,
        limit=limit,
    )
    return MatchAssessmentListResponse(
        items=[
            _assessment_response(item, is_stale=service.is_stale(item))
            for item in items
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/{assessment_id}/analysis", response_model=MatchAnalysisResponse)
async def analyze_match(
    assessment_id: UUID,
    body: AnalyzeMatchBody | None = None,
    session: Session = Depends(get_session),
    adapter: SemanticAnalysisPort = Depends(get_analysis_adapter),
) -> MatchAnalysisResponse:
    """200 whenever this call owned the analysis: a degraded model is a status, not an error.

    The one exception is a live claim held elsewhere. Returning the previous analysis there
    would present stale state as the answer to this request, so the conflict is explicit.
    """
    try:
        analysis = await MatchingService(session).analyze(
            assessment_id,
            adapter,
            refresh=body.refresh if body is not None else False,
        )
    except MatchNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "match_not_found", "message": "Match assessment not found."},
        ) from error
    except AnalysisInProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "analysis_in_progress",
                "message": "This assessment is already being analyzed.",
            },
        ) from error
    return _analysis_response(analysis)


@router.get("/{assessment_id}", response_model=MatchAssessmentResponse)
def get_match(
    assessment_id: UUID,
    session: Session = Depends(get_session),
) -> MatchAssessmentResponse:
    try:
        service = MatchingService(session)
        assessment = service.get(assessment_id)
        return _assessment_response(assessment, is_stale=service.is_stale(assessment))
    except MatchNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "match_not_found", "message": "Match assessment not found."},
        ) from error


def _assessment_response(
    assessment: MatchAssessmentModel, *, is_stale: bool = False
) -> MatchAssessmentResponse:
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
        is_stale=is_stale,
        assessed_at=assessment.assessed_at.isoformat(),
        created_at=assessment.created_at.isoformat(),
        factors=[
            _factor_response(item)
            for item in sorted(assessment.factors, key=lambda value: value.factor_code)
        ],
        analysis=_latest_analysis_response(assessment),
    )


def _latest_analysis_response(
    assessment: MatchAssessmentModel,
) -> MatchAnalysisResponse | None:
    if not assessment.analyses:
        return None
    latest = max(assessment.analyses, key=lambda item: (item.analyzed_at, item.id))
    return _analysis_response(latest)


def _analysis_response(analysis: MatchAnalysisModel) -> MatchAnalysisResponse:
    return MatchAnalysisResponse(
        id=analysis.id,
        assessment_id=analysis.assessment_id,
        status=analysis.status,
        failure_code=analysis.failure_code,
        detail=analysis.detail,
        summary=analysis.summary,
        strengths=[_item_response(item) for item in analysis.strengths],
        risks=[_item_response(item) for item in analysis.risks],
        inferences=[str(item) for item in analysis.inferences],
        unknowns=[str(item) for item in analysis.unknowns],
        recommended_review=analysis.recommended_review,
        model_id=analysis.model_id,
        prompt_version=analysis.prompt_version,
        schema_version=analysis.schema_version,
        cache_key=analysis.cache_key,
        key_version=analysis.key_version,
        payload_hash=analysis.payload_hash,
        context_refs=[
            AnalysisContextRefResponse(**ref)
            for ref in analysis.context_refs or []
            if isinstance(ref, dict)
        ],
        analyzed_at=analysis.analyzed_at.isoformat(),
        created_at=analysis.created_at.isoformat(),
        metrics=(
            AnalysisMetricsResponse(
                total_ms=analysis.total_ms,
                load_ms=analysis.load_ms,
                prompt_tokens=analysis.prompt_tokens,
                prompt_eval_ms=analysis.prompt_eval_ms,
                output_tokens=analysis.output_tokens,
                eval_ms=analysis.eval_ms,
                prompt_chars=analysis.prompt_chars,
                prompt_tokens_estimate=analysis.prompt_tokens_estimate,
            )
            if analysis.total_ms is not None or analysis.prompt_tokens is not None
            else None
        ),
    )


def _item_response(item: Any) -> AnalysisClaimResponse | str:
    if isinstance(item, dict):
        evidence, source = item_evidence(item)
        return AnalysisClaimResponse(claim=claim_text(item), evidence=evidence, source=source)
    return str(item)


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
