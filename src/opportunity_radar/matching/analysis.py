"""Structured semantic-analysis contract for matching.

This module is pure: it owns the analysis value object, its output schema, the cache
key and the degradation states. It knows nothing about Ollama or HTTP — adapters do.

The analysis is advisory only. It carries no score, no eligibility and no disqualifier,
so a model can never override the deterministic result in `domain.py`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from opportunity_radar.matching.domain import EligibilityStatus, Verdict

ANALYSIS_SCHEMA_VERSION = "analysis-v1"

MAX_SUMMARY_LENGTH = 2000
MAX_ITEMS = 20
MAX_ITEM_LENGTH = 500


class AnalysisStatus(StrEnum):
    """Semantic layer state of an assessment whose rules already completed."""

    AI_PENDING = "AI_PENDING"
    AI_COMPLETED = "AI_COMPLETED"
    AI_FAILED = "AI_FAILED"
    AI_SKIPPED = "AI_SKIPPED"


class AnalysisFailureCode(StrEnum):
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INVALID_JSON = "INVALID_JSON"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"


class AnalysisError(Exception):
    """Classified failure of the semantic layer. Never fatal to the deterministic flow."""

    def __init__(
        self,
        code: AnalysisFailureCode,
        summary: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(summary)
        self.code = code
        self.summary = summary
        self.retryable = retryable


@dataclass(frozen=True)
class SemanticAnalysis:
    """Validated model output. Advisory fields only."""

    summary: str
    strengths: tuple[str, ...]
    risks: tuple[str, ...]
    inferences: tuple[str, ...]
    unknowns: tuple[str, ...]
    recommended_review: bool
    model_id: str
    prompt_version: str
    schema_version: str = ANALYSIS_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "strengths": list(self.strengths),
            "risks": list(self.risks),
            "inferences": list(self.inferences),
            "unknowns": list(self.unknowns),
            "recommended_review": self.recommended_review,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class AnalysisOutcome:
    """What callers persist: either a validated analysis or a classified degradation."""

    status: AnalysisStatus
    analysis: SemanticAnalysis | None = None
    failure_code: AnalysisFailureCode | None = None
    detail: str | None = None

    @property
    def degraded(self) -> bool:
        return self.status is not AnalysisStatus.AI_COMPLETED


@dataclass(frozen=True)
class AnalysisRequest:
    """Inputs an adapter needs to build a prompt and a cache key.

    Snapshots are the same immutable dictionaries persisted on the assessment, so an
    analysis is reproducible from stored state alone.
    """

    opportunity_id: UUID
    opportunity_content_version: int
    profile_version_id: UUID
    rules_version: str
    taxonomy_version: str
    eligibility: EligibilityStatus
    verdict: Verdict
    score: Decimal
    opportunity_snapshot: Mapping[str, Any] = field(default_factory=dict)
    profile_snapshot: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisPolicy:
    """Section 50 of docs/20-matching-scoring.md: skip the expensive layer when it adds nothing."""

    skip_verdicts: frozenset[Verdict] = frozenset({Verdict.INELIGIBLE, Verdict.LOW_MATCH})
    skip_ineligible: bool = True
    minimum_score: Decimal = Decimal("0")

    def should_analyze(self, request: AnalysisRequest) -> bool:
        if self.skip_ineligible and request.eligibility is EligibilityStatus.INELIGIBLE:
            return False
        if request.verdict in self.skip_verdicts:
            return False
        return request.score >= self.minimum_score


# JSON Schema for the structured output. Exposed as data so the versioned prompt artifact
# in prompts/opportunity_analysis/<version>/output.schema.json can be generated from it
# instead of drifting from this validator.
OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "OpportunityAnalysis",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "strengths",
        "risks",
        "inferences",
        "unknowns",
        "recommended_review",
    ],
    "properties": {
        "summary": {"type": "string", "maxLength": MAX_SUMMARY_LENGTH},
        "strengths": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {"type": "string", "maxLength": MAX_ITEM_LENGTH},
        },
        "risks": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {"type": "string", "maxLength": MAX_ITEM_LENGTH},
        },
        "inferences": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {"type": "string", "maxLength": MAX_ITEM_LENGTH},
        },
        "unknowns": {
            "type": "array",
            "maxItems": MAX_ITEMS,
            "items": {"type": "string", "maxLength": MAX_ITEM_LENGTH},
        },
        "recommended_review": {"type": "boolean"},
    },
}

_ARRAY_FIELDS = ("strengths", "risks", "inferences", "unknowns")


def parse_analysis(
    payload: Any,
    *,
    model_id: str,
    prompt_version: str,
) -> SemanticAnalysis:
    """Validate raw model output against the contract.

    Unknown keys are rejected rather than ignored: a model must not be able to smuggle a
    score, an eligibility verdict or a disqualifier into persisted state.
    """
    if not isinstance(payload, dict):
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            "analysis payload must be a JSON object",
            retryable=True,
        )
    unexpected = sorted(set(payload) - set(OUTPUT_SCHEMA["properties"]))
    if unexpected:
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            f"analysis payload has unexpected fields: {', '.join(unexpected)}",
            retryable=True,
        )
    missing = sorted(set(OUTPUT_SCHEMA["required"]) - set(payload))
    if missing:
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            f"analysis payload is missing fields: {', '.join(missing)}",
            retryable=True,
        )

    summary = payload["summary"]
    if not isinstance(summary, str) or not summary.strip():
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            "analysis summary must be a non-empty string",
            retryable=True,
        )
    if len(summary) > MAX_SUMMARY_LENGTH:
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            "analysis summary exceeds the maximum length",
            retryable=True,
        )

    recommended_review = payload["recommended_review"]
    if not isinstance(recommended_review, bool):
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            "analysis recommended_review must be a boolean",
            retryable=True,
        )

    values: dict[str, tuple[str, ...]] = {
        name: _string_list(payload[name], name) for name in _ARRAY_FIELDS
    }
    return SemanticAnalysis(
        summary=summary.strip(),
        strengths=values["strengths"],
        risks=values["risks"],
        inferences=values["inferences"],
        unknowns=values["unknowns"],
        recommended_review=recommended_review,
        model_id=model_id,
        prompt_version=prompt_version,
    )


def _string_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            f"analysis {field_name} must be an array",
            retryable=True,
        )
    if len(value) > MAX_ITEMS:
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            f"analysis {field_name} exceeds {MAX_ITEMS} items",
            retryable=True,
        )
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise AnalysisError(
                AnalysisFailureCode.SCHEMA_MISMATCH,
                f"analysis {field_name} must contain strings only",
                retryable=True,
            )
        if len(item) > MAX_ITEM_LENGTH:
            raise AnalysisError(
                AnalysisFailureCode.SCHEMA_MISMATCH,
                f"analysis {field_name} has an item above the maximum length",
                retryable=True,
            )
        stripped = item.strip()
        if stripped:
            items.append(stripped)
    return tuple(items)


def analysis_cache_key(
    request: AnalysisRequest,
    *,
    model_id: str,
    prompt_version: str,
    schema_version: str = ANALYSIS_SCHEMA_VERSION,
) -> str:
    """Cache key from section 40: every component that can change the answer.

    Deliberately excludes the assessment id and the assessment timestamp, so two runs over
    equivalent inputs hit the same entry.
    """
    payload = {
        "opportunity_id": str(request.opportunity_id),
        "opportunity_content_version": request.opportunity_content_version,
        "profile_version_id": str(request.profile_version_id),
        "rules_version": request.rules_version,
        "taxonomy_version": request.taxonomy_version,
        "prompt_version": prompt_version,
        "model_id": model_id,
        "schema_version": schema_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SemanticAnalysisPort(Protocol):
    """What the matching application depends on. Implemented by adapters."""

    async def analyze(self, request: AnalysisRequest) -> AnalysisOutcome:
        ...


class NullAnalysisAdapter:
    """Adapter used when the semantic layer is disabled. Always degrades cleanly."""

    async def analyze(self, request: AnalysisRequest) -> AnalysisOutcome:
        del request
        return AnalysisOutcome(
            status=AnalysisStatus.AI_SKIPPED,
            detail="semantic analysis is disabled",
        )


def skipped_outcome(reason: str) -> AnalysisOutcome:
    return AnalysisOutcome(status=AnalysisStatus.AI_SKIPPED, detail=reason)


def failed_outcome(error: AnalysisError) -> AnalysisOutcome:
    return AnalysisOutcome(
        status=AnalysisStatus.AI_FAILED,
        failure_code=error.code,
        detail=error.summary,
    )


def completed_outcome(analysis: SemanticAnalysis) -> AnalysisOutcome:
    return AnalysisOutcome(status=AnalysisStatus.AI_COMPLETED, analysis=analysis)


__all__: Sequence[str] = (
    "ANALYSIS_SCHEMA_VERSION",
    "OUTPUT_SCHEMA",
    "AnalysisError",
    "AnalysisFailureCode",
    "AnalysisOutcome",
    "AnalysisPolicy",
    "AnalysisRequest",
    "AnalysisStatus",
    "NullAnalysisAdapter",
    "SemanticAnalysis",
    "SemanticAnalysisPort",
    "analysis_cache_key",
    "completed_outcome",
    "failed_outcome",
    "parse_analysis",
    "skipped_outcome",
)
