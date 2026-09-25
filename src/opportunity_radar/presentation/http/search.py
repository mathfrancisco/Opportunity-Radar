"""HTTP API over the opportunity embeddings: similar postings and search by meaning.

Card F16-10. A router of its own, and not a path under `/opportunities/...` for the
search: `GET /opportunities/{opportunity_id}` is declared first and would capture
`/opportunities/semantic-search`, answering 422. `/opportunities/{id}/similar` has one
segment more, so it does not collide.

Search by meaning is available through the API only. Whether it becomes a mode of the
Inbox is the gate's decision (SPEC 36, section 7.4); until then nothing here stands in
the way of the full-text search, and a missing model is a 503 of this route alone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.search_filters import OpportunityFilters
from opportunity_radar.opportunities.domain import OpportunityStatus, Seniority, WorkMode
from opportunity_radar.opportunities.embeddings import (
    QUERY_INSTRUCTION_VERSION,
    EmbeddingError,
    EmbeddingFailureCode,
    OllamaEmbeddingAdapter,
    RelatedOpportunity,
    describe_opportunities,
    embedding_coverage,
    semantic_search_ids,
    similar_opportunities,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.config import Settings, get_settings
from opportunity_radar.presentation.http.dependencies import (
    get_embedding_adapter,
    get_session,
)

router = APIRouter(tags=["search"])


class RelatedOpportunityResponse(BaseModel):
    id: UUID
    title: str
    company_name: str | None
    #: The latest assessment against the active profile; `None` when there is none.
    verdict: str | None
    #: 1 − cosine distance: 1 is the same direction, 0 unrelated.
    similarity: float


class SimilarOpportunitiesResponse(BaseModel):
    opportunity_id: UUID
    #: `no_embedding`: this posting has no current vector yet, so there is nothing to
    #: compare from. Not an error; the next embedding pass fills it.
    status: Literal["ok", "no_embedding"]
    model: str
    items: list[RelatedOpportunityResponse]


class IndexCoverageResponse(BaseModel):
    current: int
    eligible: int
    complete: bool


class SemanticSearchResponse(BaseModel):
    items: list[RelatedOpportunityResponse]
    limit: int
    offset: int
    model: str
    query_instruction_version: str
    #: A partial index answers from the postings it has; the reader is told how many.
    index: IndexCoverageResponse


@router.get(
    "/opportunities/{opportunity_id}/similar",
    response_model=SimilarOpportunitiesResponse,
)
def list_similar_opportunities(
    opportunity_id: UUID,
    limit: int = Query(default=5, ge=1, le=20),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SimilarOpportunitiesResponse:
    if session.get(OpportunityModel, opportunity_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "opportunity_not_found", "message": "Opportunity not found."},
        )
    model = settings.ollama_model_embedding
    related = similar_opportunities(session, opportunity_id, model=model, limit=limit)
    return SimilarOpportunitiesResponse(
        opportunity_id=opportunity_id,
        status="no_embedding" if related is None else "ok",
        model=model,
        items=[_related_response(item) for item in related or ()],
    )


@router.get("/search/semantic", response_model=SemanticSearchResponse)
def search_by_meaning(
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    company_id: UUID | None = None,
    lifecycle_status: OpportunityStatus | None = None,
    published_after: datetime | None = None,
    work_mode: list[WorkMode] = Query(default=[]),
    seniority: list[Seniority] = Query(default=[]),
    session: Session = Depends(get_session),
    adapter: OllamaEmbeddingAdapter | None = Depends(get_embedding_adapter),
) -> SemanticSearchResponse:
    query = q.strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "empty_query", "message": "The query is blank."},
        )
    if adapter is None:
        raise _unavailable(EmbeddingFailureCode.DISABLED, "embedding is switched off")
    try:
        vector = adapter.embed_query(query)
    except EmbeddingError as error:
        raise _unavailable(error.code, error.detail) from error
    filters = OpportunityFilters(
        company_id=company_id,
        lifecycle_status=lifecycle_status.value if lifecycle_status else None,
        published_after=published_after,
        work_modes=tuple(item.value for item in work_mode),
        seniorities=tuple(item.value for item in seniority),
    )
    ranked = semantic_search_ids(
        session, vector, model=adapter.model, filters=filters, limit=limit, offset=offset
    )
    coverage = embedding_coverage(session, model=adapter.model)
    return SemanticSearchResponse(
        items=[_related_response(item) for item in describe_opportunities(session, ranked)],
        limit=limit,
        offset=offset,
        model=adapter.model,
        query_instruction_version=QUERY_INSTRUCTION_VERSION,
        index=IndexCoverageResponse(
            current=coverage.current,
            eligible=coverage.eligible,
            complete=coverage.complete,
        ),
    )


def _unavailable(code: EmbeddingFailureCode, message: str) -> HTTPException:
    """A classified 503: the search is unavailable, the rest of the API is not."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "semantic_search_unavailable",
            "reason": code.value,
            "message": message,
        },
    )


def _related_response(item: RelatedOpportunity) -> RelatedOpportunityResponse:
    return RelatedOpportunityResponse(
        id=item.id,
        title=item.title,
        company_name=item.company_name,
        verdict=item.verdict,
        similarity=item.similarity,
    )
