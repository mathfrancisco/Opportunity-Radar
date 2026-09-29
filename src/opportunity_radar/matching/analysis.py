"""Structured semantic-analysis contract for matching.

This module is pure: it owns the analysis value object, its output schema, the cache
key and the degradation states. It knows nothing about Groq or HTTP — adapters do.

The analysis is advisory only. It carries no score, no eligibility and no disqualifier,
so a model can never override the deterministic result in `domain.py`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from opportunity_radar.matching.domain import EligibilityStatus, Verdict
from opportunity_radar.matching.text import TokenCalibration

ANALYSIS_SCHEMA_VERSION = "analysis-v1"
#: Strengths and risks become `{claim, evidence, source}` objects (card F16-07).
ANALYSIS_SCHEMA_V2 = "analysis-v2"
#: Identity of an analysis from card F16-08: the payload actually sent, the prompt's
#: content, the model and every option that changes the answer. Rows keyed before it
#: have `key_version` NULL and are never reused as if they were keyed by it.
#: Bumped to v3 (card F20-16): `options` now carries the provider and the model chain,
#: so an analysis under one provider/model never collides with another keyed under the
#: same v2 digest.
ANALYSIS_KEY_VERSION = "analysis-key-v3"
#: Where a quoted piece of evidence may come from in the payload that was sent.
CLAIM_SOURCES = ("posting", "profile")

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
    # Not even the fixed parts of the prompt fit the window: the call is never sent.
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"


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
        # What the call cost when the model did answer, even if the answer was unusable:
        # a schema mismatch after 40 seconds is a different problem from one after 2.
        self.metrics: AnalysisMetrics | None = None


@dataclass(frozen=True)
class AnalysisMetrics:
    """What one model call cost, as the server reported it. Durations in milliseconds.

    Every field is optional: an adapter that does not report a number leaves it absent,
    and absent is shown as unavailable, never as zero.
    """

    total_ms: int | None = None
    load_ms: int | None = None
    prompt_tokens: int | None = None
    prompt_eval_ms: int | None = None
    output_tokens: int | None = None
    eval_ms: int | None = None
    # Measured before sending: the gap between the estimate and `prompt_tokens` is how
    # well the characters-per-token ratio is calibrated.
    prompt_chars: int | None = None
    prompt_tokens_estimate: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "prompt_chars": self.prompt_chars,
            "prompt_tokens_estimate": self.prompt_tokens_estimate,
            "total_ms": self.total_ms,
            "load_ms": self.load_ms,
            "prompt_tokens": self.prompt_tokens,
            "prompt_eval_ms": self.prompt_eval_ms,
            "output_tokens": self.output_tokens,
            "eval_ms": self.eval_ms,
        }


@dataclass(frozen=True)
class Claim:
    """One strength or risk under `analysis-v2`, with the passage that supports it.

    `evidence` is copied from the payload that was sent, in the block `source` names. A
    claim without evidence is an inference and says so with both fields null; the
    validator refuses anything in between.
    """

    claim: str
    evidence: str | None = None
    source: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"claim": self.claim, "evidence": self.evidence, "source": self.source}


#: A strength or risk: plain text under `analysis-v1`, a `Claim` from `analysis-v2` on.
AnalysisItem = str | Claim


def claim_text(item: Any) -> str:
    """The statement of an item, whichever schema produced it (stored JSON included)."""
    if isinstance(item, Claim):
        return item.claim
    if isinstance(item, Mapping):
        return str(item.get("claim") or "")
    return str(item)


def item_evidence(item: Any) -> tuple[str | None, str | None]:
    """`(evidence, source)` of an item; `(None, None)` for an `analysis-v1` string."""
    if isinstance(item, Claim):
        return item.evidence, item.source
    if isinstance(item, Mapping):
        evidence, source = item.get("evidence"), item.get("source")
        return (
            evidence if isinstance(evidence, str) else None,
            source if isinstance(source, str) else None,
        )
    return None, None


def _item_json(item: AnalysisItem) -> Any:
    return item.as_dict() if isinstance(item, Claim) else item


@dataclass(frozen=True)
class SemanticAnalysis:
    """Validated model output. Advisory fields only."""

    summary: str
    strengths: tuple[AnalysisItem, ...]
    risks: tuple[AnalysisItem, ...]
    inferences: tuple[str, ...]
    unknowns: tuple[str, ...]
    recommended_review: bool
    model_id: str
    prompt_version: str
    schema_version: str = ANALYSIS_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "strengths": [_item_json(item) for item in self.strengths],
            "risks": [_item_json(item) for item in self.risks],
            "inferences": list(self.inferences),
            "unknowns": list(self.unknowns),
            "recommended_review": self.recommended_review,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }

    def evidence(self) -> list[tuple[str, str | None]]:
        """Every quoted passage with the block it claims to come from."""
        quoted = (item_evidence(item) for item in (*self.strengths, *self.risks))
        return [(evidence, source) for evidence, source in quoted if evidence is not None]


@dataclass(frozen=True)
class AnalysisOutcome:
    """What callers persist: either a validated analysis or a classified degradation."""

    status: AnalysisStatus
    analysis: SemanticAnalysis | None = None
    failure_code: AnalysisFailureCode | None = None
    detail: str | None = None
    metrics: AnalysisMetrics | None = None

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
    # Calibrated from this model's recorded analyses; `None` falls back to the default.
    # It enters the key only through what it changes: the description it lets through.
    tokens_per_char: float | None = None
    # The measured calibration of this model and prompt (card F16-05). When present, its
    # conservative ratio and margin replace `tokens_per_char` and the default margin.
    calibration: TokenCalibration | None = None
    # The posting as the assessment saw it: title, company, location and the raw
    # description, which the adapter cleans and fits (card F16-07). `None` for prompts
    # that do not read the posting.
    posting: Mapping[str, Any] | None = None
    # The profile's recent experiences and projects, without contact data (card F16-07).
    profile_history: Mapping[str, Any] | None = None
    # Decided postings similar to this one, already cut to a small fixed number (card
    # F16-11). Snapshot values, never ids to be resolved later.
    similar_decisions: Sequence[Mapping[str, Any]] | None = None


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

MAX_EVIDENCE_LENGTH = 300

_CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claim", "evidence", "source"],
    "properties": {
        "claim": {"type": "string", "maxLength": MAX_ITEM_LENGTH},
        "evidence": {"type": ["string", "null"], "maxLength": MAX_EVIDENCE_LENGTH},
        "source": {"enum": [*CLAIM_SOURCES, None]},
    },
}

# `analysis-v2`: the same closed object, with strengths and risks carrying the passage of
# the payload that supports each one. Still no score, eligibility or verdict.
OUTPUT_SCHEMA_V2: dict[str, Any] = {
    **OUTPUT_SCHEMA,
    "properties": {
        **OUTPUT_SCHEMA["properties"],
        "strengths": {"type": "array", "maxItems": MAX_ITEMS, "items": _CLAIM_SCHEMA},
        "risks": {"type": "array", "maxItems": MAX_ITEMS, "items": _CLAIM_SCHEMA},
    },
}

#: The schema each version validates against. A prompt declares its version in metadata.
OUTPUT_SCHEMAS: dict[str, dict[str, Any]] = {
    ANALYSIS_SCHEMA_VERSION: OUTPUT_SCHEMA,
    ANALYSIS_SCHEMA_V2: OUTPUT_SCHEMA_V2,
}

_ARRAY_FIELDS = ("strengths", "risks", "inferences", "unknowns")
_CLAIM_FIELDS = ("strengths", "risks")


def parse_analysis(
    payload: Any,
    *,
    model_id: str,
    prompt_version: str,
    schema_version: str = ANALYSIS_SCHEMA_VERSION,
    evidence_sources: Mapping[str, str] | None = None,
) -> SemanticAnalysis:
    """Validate raw model output against the contract of `schema_version`.

    Unknown keys are rejected rather than ignored: a model must not be able to smuggle a
    score, an eligibility verdict or a disqualifier into persisted state.

    From `analysis-v2` on, every quoted `evidence` must appear in the block of the payload
    its `source` names (`evidence_sources`, the texts that were actually sent). A passage
    that is not there was invented, and an invented quote is a mismatch, not an answer.
    Presence is all code can check: whether the passage supports the claim — a negation,
    an optional requirement — is the human rubric of the evaluation set.
    """
    schema = OUTPUT_SCHEMAS.get(schema_version)
    if schema is None:
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            f"unknown analysis schema version {schema_version!r}",
        )
    if not isinstance(payload, dict):
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            "analysis payload must be a JSON object",
            retryable=True,
        )
    unexpected = sorted(set(payload) - set(schema["properties"]))
    if unexpected:
        raise AnalysisError(
            AnalysisFailureCode.SCHEMA_MISMATCH,
            f"analysis payload has unexpected fields: {', '.join(unexpected)}",
            retryable=True,
        )
    missing = sorted(set(schema["required"]) - set(payload))
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

    with_claims = schema_version != ANALYSIS_SCHEMA_VERSION
    items: dict[str, tuple[AnalysisItem, ...]] = {}
    for name in _ARRAY_FIELDS:
        if with_claims and name in _CLAIM_FIELDS:
            items[name] = _claim_list(payload[name], name, evidence_sources or {})
        else:
            items[name] = _string_list(payload[name], name)
    return SemanticAnalysis(
        summary=summary.strip(),
        strengths=items["strengths"],
        risks=items["risks"],
        inferences=tuple(str(item) for item in items["inferences"]),
        unknowns=tuple(str(item) for item in items["unknowns"]),
        recommended_review=recommended_review,
        model_id=model_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
    )


_EDGE_PUNCTUATION = " \t\n\"'“”‘’«».,;:!?()[]{}…-–—"
_WHITESPACE = re.compile(r"\s+")


def normalize_evidence(text: str) -> str:
    """Lowercase, whitespace collapsed, punctuation at the edges removed (card F16-07)."""
    return _WHITESPACE.sub(" ", text.casefold()).strip(_EDGE_PUNCTUATION)


def _claim_list(
    value: Any, field_name: str, sources: Mapping[str, str]
) -> tuple[AnalysisItem, ...]:
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
    normalized_sources = {name: normalize_evidence(text) for name, text in sources.items()}
    claims: list[AnalysisItem] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"claim", "evidence", "source"}:
            raise AnalysisError(
                AnalysisFailureCode.SCHEMA_MISMATCH,
                f"analysis {field_name} items must be objects with claim, evidence and source",
                retryable=True,
            )
        claim, evidence, source = item["claim"], item["evidence"], item["source"]
        if not isinstance(claim, str) or len(claim) > MAX_ITEM_LENGTH:
            raise AnalysisError(
                AnalysisFailureCode.SCHEMA_MISMATCH,
                f"analysis {field_name} has an invalid claim",
                retryable=True,
            )
        if not claim.strip():
            continue
        if (evidence is None) != (source is None):
            # A source without a passage, or a passage without a source, is an inference
            # dressed as a fact: exactly what the schema exists to keep apart.
            raise AnalysisError(
                AnalysisFailureCode.SCHEMA_MISMATCH,
                f"analysis {field_name} pairs evidence and source inconsistently",
            )
        if evidence is not None:
            if (
                not isinstance(evidence, str)
                or len(evidence) > MAX_EVIDENCE_LENGTH
                or source not in CLAIM_SOURCES
            ):
                raise AnalysisError(
                    AnalysisFailureCode.SCHEMA_MISMATCH,
                    f"analysis {field_name} has invalid evidence or source",
                )
            quoted = normalize_evidence(evidence)
            if not quoted or quoted not in normalized_sources.get(str(source), ""):
                # Deterministic decoding would invent the same passage again, so a retry
                # would only spend another call.
                raise AnalysisError(
                    AnalysisFailureCode.SCHEMA_MISMATCH,
                    f"analysis {field_name} quotes evidence absent from the {source} block",
                )
            claims.append(Claim(claim=claim.strip(), evidence=evidence.strip(), source=source))
        else:
            claims.append(Claim(claim=claim.strip()))
    return tuple(claims)


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


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def analysis_key(
    request: AnalysisRequest,
    *,
    model_id: str,
    prompt_version: str,
    schema_version: str,
    prompt_digest: str,
    payload_hash: str,
    options: Mapping[str, Any],
) -> str:
    """`ANALYSIS_KEY_VERSION`: the one definition the service, the adapter and the table share.

    The payload hash covers what the model read — the posting as cleaned and cut, the
    profile history, the retrieved decisions, the deterministic result — so a different
    cut or a changed decision is a different analysis. The prompt digest covers the
    wording and the schema, not just the version label, and `options` every inference
    setting that changes the answer. `keep_alive` is deliberately absent: it changes how
    long the model stays loaded, not what it says.
    """
    return _digest(
        {
            "key_version": ANALYSIS_KEY_VERSION,
            "opportunity_id": str(request.opportunity_id),
            "opportunity_content_version": request.opportunity_content_version,
            "profile_version_id": str(request.profile_version_id),
            "rules_version": request.rules_version,
            "taxonomy_version": request.taxonomy_version,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "prompt_digest": prompt_digest,
            "schema_version": schema_version,
            "options": dict(options),
            "payload_hash": payload_hash,
        }
    )


def payload_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _strings(item)]
    return []


def evidence_sources(payload: Mapping[str, Any]) -> dict[str, str]:
    """The texts evidence may quote, by source, from the payload as it was sent.

    `posting` is the posting block plus the structured opportunity snapshot derived from
    it; `profile` is the profile block. The deterministic result and retrieved decisions
    are deliberately not sources: a claim cannot be evidenced by the verdict it comments.
    """
    return {
        "posting": "\n".join(
            _strings(payload.get("posting")) + _strings(payload.get("opportunity"))
        ),
        "profile": "\n".join(_strings(payload.get("profile"))),
    }


@dataclass(frozen=True)
class PreparedAnalysis:
    """Everything decided before the call: what is sent, what it costs, what it is keyed by.

    Built by the adapter, because only the adapter knows the prompt, the window and the
    options; read by the service to look the key up before any call is made, and stored
    with the row so an answer can be audited against the exact payload it came from.
    """

    cache_key: str
    payload_hash: str
    payload: Mapping[str, Any]
    inference: Mapping[str, Any]
    size: AnalysisMetrics
    system: str = ""
    user_content: str = ""
    prompt_budget: int | None = None
    # Not even the fixed parts of the prompt fit the budget: nothing is sent.
    overflow: bool = False
    # The texts evidence may quote, by source, exactly as they were sent.
    evidence_sources: Mapping[str, str] = field(default_factory=dict)
    # Retrieved decisions actually sent, as references to store (card F16-11).
    context_refs: tuple[Mapping[str, Any], ...] = ()
    key_version: str = ANALYSIS_KEY_VERSION
    schema_version: str = ANALYSIS_SCHEMA_VERSION


class SemanticAnalysisPort(Protocol):
    """What the matching application depends on. Implemented by adapters.

    `prepare` is separate from `analyze` so the caller can key, look up and persist an
    analysis by the payload that would be sent without sending it. `requires` says which
    inputs beyond the stored snapshots the prompt reads, so the caller only loads those.
    """

    @property
    def model(self) -> str:
        ...

    @property
    def prompt_version(self) -> str:
        ...

    @property
    def requires(self) -> frozenset[str]:
        ...

    def prepare(self, request: AnalysisRequest) -> PreparedAnalysis:
        ...

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        prepared: PreparedAnalysis | None = None,
        use_cache: bool = True,
    ) -> AnalysisOutcome:
        ...

    async def warm_up(self, *, only_if_idle: bool = False) -> AnalysisMetrics | None:
        """Load the model ahead of the queue. Never raises; `None` when nothing loaded."""
        ...

    async def describe(self) -> Mapping[str, Any]:
        """Server version and the digest behind the model tag, as far as they are known.

        Never raises. Later `prepare` calls record what this found, so a tag re-pulled
        with other weights is visible in the rows and is not reused across (F16-08).
        """
        ...


class NullAnalysisAdapter:
    """Adapter used when the semantic layer is disabled. Always degrades cleanly."""

    @property
    def model(self) -> str:
        return "disabled"

    @property
    def prompt_version(self) -> str:
        return "disabled"

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    def prepare(self, request: AnalysisRequest) -> PreparedAnalysis:
        payload = {
            "opportunity": dict(request.opportunity_snapshot),
            "profile": dict(request.profile_snapshot),
        }
        payload_hash = _digest(payload)
        return PreparedAnalysis(
            cache_key=analysis_key(
                request,
                model_id=self.model,
                prompt_version=self.prompt_version,
                schema_version=ANALYSIS_SCHEMA_VERSION,
                prompt_digest="disabled",
                payload_hash=payload_hash,
                options={},
            ),
            payload_hash=payload_hash,
            payload=payload,
            inference={"model": self.model},
            size=AnalysisMetrics(),
        )

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        prepared: PreparedAnalysis | None = None,
        use_cache: bool = True,
    ) -> AnalysisOutcome:
        del request, prepared, use_cache
        return AnalysisOutcome(
            status=AnalysisStatus.AI_SKIPPED,
            detail="semantic analysis is disabled",
        )

    async def warm_up(self, *, only_if_idle: bool = False) -> AnalysisMetrics | None:
        del only_if_idle
        return None

    async def describe(self) -> Mapping[str, Any]:
        return {}


def skipped_outcome(reason: str) -> AnalysisOutcome:
    return AnalysisOutcome(status=AnalysisStatus.AI_SKIPPED, detail=reason)


def failed_outcome(error: AnalysisError) -> AnalysisOutcome:
    return AnalysisOutcome(
        status=AnalysisStatus.AI_FAILED,
        failure_code=error.code,
        detail=error.summary,
        metrics=error.metrics,
    )


def completed_outcome(
    analysis: SemanticAnalysis, metrics: AnalysisMetrics | None = None
) -> AnalysisOutcome:
    return AnalysisOutcome(
        status=AnalysisStatus.AI_COMPLETED, analysis=analysis, metrics=metrics
    )


__all__: Sequence[str] = (
    "ANALYSIS_KEY_VERSION",
    "ANALYSIS_SCHEMA_V2",
    "ANALYSIS_SCHEMA_VERSION",
    "CLAIM_SOURCES",
    "OUTPUT_SCHEMA",
    "OUTPUT_SCHEMAS",
    "OUTPUT_SCHEMA_V2",
    "AnalysisError",
    "AnalysisFailureCode",
    "AnalysisItem",
    "AnalysisMetrics",
    "AnalysisOutcome",
    "AnalysisPolicy",
    "AnalysisRequest",
    "AnalysisStatus",
    "Claim",
    "NullAnalysisAdapter",
    "PreparedAnalysis",
    "SemanticAnalysis",
    "SemanticAnalysisPort",
    "analysis_cache_key",
    "analysis_key",
    "claim_text",
    "completed_outcome",
    "evidence_sources",
    "failed_outcome",
    "item_evidence",
    "normalize_evidence",
    "parse_analysis",
    "payload_digest",
    "skipped_outcome",
)
