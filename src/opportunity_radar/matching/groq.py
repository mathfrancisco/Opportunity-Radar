"""Groq adapter for structured semantic analysis (SPEC 43; cards F20-16, F20-17).

Infrastructure only, like the retired local adapter: the domain never sees the
Groq wire format, it depends on `SemanticAnalysisPort` and gets back an `AnalysisOutcome`
that is already classified. Retry, fallback across the model chain, the circuit breaker
and the quota reservation all live in the shared `AIRouter` (cards F20-10 to F20-12);
this adapter owns the prompt, the payload, the token-budget fit (F20-13), the PII
sanitizer (F20-15) and the cache identity (F20-16).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from opportunity_radar.matching.analysis import (
    OUTPUT_SCHEMAS,
    AnalysisError,
    AnalysisFailureCode,
    AnalysisMetrics,
    AnalysisOutcome,
    AnalysisPolicy,
    AnalysisRequest,
    PreparedAnalysis,
    analysis_key,
    completed_outcome,
    evidence_sources,
    failed_outcome,
    parse_analysis,
    payload_digest,
    skipped_outcome,
)
from opportunity_radar.matching.prompts import PromptArtifacts
from opportunity_radar.matching.text import (
    CLEANER_VERSION,
    DEFAULT_TOKENS_PER_CHAR,
    clean_description_report,
    fit_description,
    prompt_budget,
    truncate_at_sentence,
)
from opportunity_radar.matching.text import estimate_tokens as _text_estimate_tokens
from opportunity_radar.platform.ai.budget import estimate_tokens as _budget_estimate_tokens
from opportunity_radar.platform.ai.budget import fits
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMResponse
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.sanitizer import sanitize_for_llm
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute

#: Rounds of re-fitting when JSON escaping made the rendered prompt longer than planned.
_FIT_ROUNDS = 3

#: Deterministic sampling seed (card F20-17's request example); no per-task tuning yet.
_SEED = 42


class GroqAnalysisAdapter:
    """Calls Groq through the shared `AIRouter` and returns validated structured analysis."""

    def __init__(
        self,
        *,
        router: AIRouter,
        prompt: PromptArtifacts,
        policy: AnalysisPolicy | None = None,
    ) -> None:
        self._router = router
        self._prompt = prompt
        self._policy = policy or AnalysisPolicy()

    @property
    def _route(self) -> ModelRoute:
        return self._router.route(AITask.JOB_MATCH)

    @property
    def model(self) -> str:
        return self._route.chain[0]

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    @property
    def requires(self) -> frozenset[str]:
        """Inputs beyond the stored snapshots this prompt reads (cards F16-07, F16-11)."""
        needed = set(self._prompt.variables) & {"posting", "similar_decisions"}
        if self._prompt.reads_profile_history:
            needed.add("profile_history")
        return frozenset(needed)

    def prepare(self, request: AnalysisRequest) -> PreparedAnalysis:
        """Build, sanitize, measure, fit and key the exact payload an analysis would send.

        Every snapshot is passed through `sanitize_for_llm` (card F20-15) before it is
        rendered into the prompt and before the payload hash is computed, so neither the
        model nor the cache key ever see contact data or a leaked credential. The fixed
        parts then go in whole; if they alone exceed the task's token budget
        (`platform.ai.budget.fits`, card F20-13), nothing is sent. The posting's
        description takes what is left, cleaned and cut at a sentence boundary, and the
        retrieved decisions give way before the description does.
        """
        route = self._route
        ratio, margin = self._ratio_and_margin(request, route)
        budget_ceiling = prompt_budget(
            route.budget.max_input_tokens, route.budget.max_output_tokens, margin
        )

        posting = (
            sanitize_for_llm(dict(request.posting or {}))
            if "posting" in self.requires
            else None
        )
        cleaned = clean_description_report(str((posting or {}).get("description") or ""))
        decisions = [sanitize_for_llm(dict(item)) for item in request.similar_decisions or ()]
        offered = len(decisions)
        description = cleaned.text
        truncated = False

        profile = sanitize_for_llm(dict(request.profile_snapshot))
        if self._prompt.reads_profile_history:
            profile.update(sanitize_for_llm(dict(request.profile_history or {})))
        opportunity = sanitize_for_llm(dict(request.opportunity_snapshot))

        def render(text: str, cut: bool, context: Sequence[Mapping[str, Any]]) -> str:
            return self._user_content(
                request, posting, profile, opportunity, text, cut, context
            )

        def estimate(content: str) -> int:
            return _text_estimate_tokens(len(self._prompt.system) + len(content), ratio)

        if posting is not None:
            if estimate(render("", False, [])) > budget_ceiling:
                pass  # nothing to trim towards; the fits() gate below will catch it
            else:
                while True:
                    available = budget_ceiling - estimate(render("", False, decisions))
                    fitted = fit_description(
                        cleaned.text, available_tokens=available, tokens_per_char=ratio
                    )
                    if fitted.truncated and decisions:
                        decisions.pop()
                        continue
                    description, truncated = fitted.text, fitted.truncated
                    break
                for _ in range(_FIT_ROUNDS):
                    excess = estimate(render(description, truncated, decisions)) - budget_ceiling
                    if excess <= 0:
                        break
                    shorter = max(0, len(description) - int(excess / ratio) - 1)
                    description, _ = truncate_at_sentence(description, shorter)
                    truncated = True

        user_content = render(description, truncated, decisions)
        payload: dict[str, Any] = json.loads(user_content)
        # Whether not even the fixed parts fit is decided by the Token Guard (card
        # F20-13), not by the local ratio used above only to choose what to cut.
        overflow = not fits(self._prompt.system, user_content, route.budget)
        prompt_tokens_estimate = _budget_estimate_tokens(self._prompt.system + user_content)
        size = AnalysisMetrics(
            prompt_chars=len(self._prompt.system) + len(user_content),
            prompt_tokens_estimate=prompt_tokens_estimate,
        )
        options: dict[str, Any] = {
            "provider": "groq",
            "chain": list(route.chain),
            "reasoning_effort": route.budget.reasoning_effort,
            "max_completion_tokens": route.budget.max_output_tokens,
            "temperature": self._prompt.sampling.get("temperature", 0),
            "seed": _SEED,
        }
        inference: dict[str, Any] = {
            "model": route.chain[0],
            "prompt_version": self._prompt.version,
            "prompt_digest": self._prompt.digest,
            "schema_version": self._prompt.schema_version,
            "options": options,
            "tokens_per_char": ratio,
            "calibration": (
                request.calibration.as_dict()
                if request.calibration is not None
                else {"state": "uncalibrated", "samples": 0, "ratio": ratio}
            ),
            "prompt_budget": budget_ceiling,
        }
        if posting is not None:
            inference["cut"] = {
                "cleaner_version": CLEANER_VERSION,
                "description_sha256": payload_digest(cleaned.text),
                "description_chars": len(cleaned.text),
                "description_sent_chars": len(description),
                "description_truncated": truncated,
                "removed_sections": list(cleaned.removed_sections),
                "kept_facts": cleaned.kept_facts,
            }
        if "similar_decisions" in self.requires:
            inference["context"] = {
                "offered": offered,
                "sent": len(decisions),
                "dropped": offered - len(decisions),
            }
        payload_hash = payload_digest(user_content)
        return PreparedAnalysis(
            cache_key=analysis_key(
                request,
                model_id=route.chain[0],
                prompt_version=self._prompt.version,
                schema_version=self._prompt.schema_version,
                prompt_digest=self._prompt.digest,
                payload_hash=payload_hash,
                options=options,
            ),
            payload_hash=payload_hash,
            payload=payload,
            inference=inference,
            size=size,
            system=self._prompt.system,
            user_content=user_content,
            prompt_budget=budget_ceiling,
            overflow=overflow,
            evidence_sources=evidence_sources(payload),
            # Only the decisions that survived the cut: what the model actually read.
            context_refs=tuple(
                dict(item["ref"]) for item in decisions if isinstance(item.get("ref"), Mapping)
            ),
            schema_version=self._prompt.schema_version,
        )

    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        prepared: PreparedAnalysis | None = None,
        use_cache: bool = True,
    ) -> AnalysisOutcome:
        """Never raises for an external failure: callers get a classified outcome.

        There is no in-memory cache here (card F20-16): reuse across restarts is the
        service's job, keyed by `PreparedAnalysis.cache_key` against the persisted table.
        `use_cache` is accepted for interface parity with `SemanticAnalysisPort` and
        currently unused by this adapter.
        """
        del use_cache
        if not self._policy.should_analyze(request):
            return skipped_outcome("policy skipped the semantic layer for this assessment")

        prepared = prepared or self.prepare(request)
        if prepared.overflow:
            overflow = AnalysisError(
                AnalysisFailureCode.CONTEXT_OVERFLOW,
                f"prompt needs about {prepared.size.prompt_tokens_estimate} tokens; "
                f"the budget is {prepared.prompt_budget}",
            )
            overflow.metrics = prepared.size
            return failed_outcome(overflow)

        try:
            result = await self._router.run(
                AITask.JOB_MATCH,
                system=prepared.system,
                user=prepared.user_content,
                schema_name=f"analysis_{prepared.schema_version.replace('-', '_')}",
                json_schema=OUTPUT_SCHEMAS[prepared.schema_version],
                temperature=self._prompt.sampling.get("temperature"),
                seed=_SEED,
                estimated_input_tokens=prepared.size.prompt_tokens_estimate or 0,
            )
        except ProviderError as error:
            failure = _classify(error)
            failure.metrics = _with_size(None, prepared.size)
            return failed_outcome(failure)

        response = result.response
        try:
            payload = json.loads(response.content)
        except (json.JSONDecodeError, TypeError, ValueError):
            invalid = AnalysisError(
                AnalysisFailureCode.INVALID_JSON,
                "groq analysis content is not valid JSON",
            )
            invalid.metrics = _with_size(_response_metrics(response), prepared.size)
            return failed_outcome(invalid)
        try:
            analysis = parse_analysis(
                payload,
                model_id=response.model or route_model(self._route),
                prompt_version=self._prompt.version,
                schema_version=prepared.schema_version,
                evidence_sources=prepared.evidence_sources,
            )
        except AnalysisError as error:
            error.metrics = _with_size(_response_metrics(response), prepared.size)
            return failed_outcome(error)

        metrics = _with_size(_response_metrics(response), prepared.size)
        return completed_outcome(analysis, metrics)

    async def warm_up(self, *, only_if_idle: bool = False) -> AnalysisMetrics | None:
        del only_if_idle
        return None  # nothing to warm up in the cloud

    async def describe(self) -> Mapping[str, Any]:
        return {"provider": "groq", "chain": list(self._route.chain)}

    def _ratio_and_margin(
        self, request: AnalysisRequest, route: ModelRoute
    ) -> tuple[float, int | None]:
        calibration = request.calibration
        if calibration is not None:
            return calibration.ratio, calibration.margin(
                route.budget.max_input_tokens, route.budget.max_output_tokens
            )
        return request.tokens_per_char or DEFAULT_TOKENS_PER_CHAR, None

    def _user_content(
        self,
        request: AnalysisRequest,
        posting: Mapping[str, Any] | None,
        profile: Mapping[str, Any],
        opportunity: Mapping[str, Any],
        description: str,
        truncated: bool,
        decisions: Sequence[Mapping[str, Any]],
    ) -> str:
        """Render the versioned template. Values arrive JSON-encoded, so the result parses.

        `posting`, `profile`, `opportunity` and `decisions` are already sanitized by the
        caller (card F20-15): nothing here needs to strip PII again.
        """
        deterministic_result = {
            "eligibility": request.eligibility.value,
            "verdict": request.verdict.value,
            "score": str(request.score),
            "rules_version": request.rules_version,
            "taxonomy_version": request.taxonomy_version,
            "authoritative": True,
        }
        values = {
            "schema_version": _encode(self._prompt.schema_version),
            "deterministic_result": _encode(deterministic_result),
            "opportunity": _encode(dict(opportunity)),
            "profile": _encode(dict(profile)),
            "posting": _encode(
                {
                    "title": (posting or {}).get("title"),
                    "company_name": (posting or {}).get("company_name"),
                    "location_text": (posting or {}).get("location_text"),
                    "description": description or None,
                    "description_truncated": truncated,
                }
            ),
            "similar_decisions": _encode(
                # The reference is for the row, not the model: ids mean nothing to it.
                [
                    {key: value for key, value in item.items() if key != "ref"}
                    for item in decisions
                ]
            ),
        }
        declared = set(self._prompt.variables)
        return self._prompt.render_user(
            {name: value for name, value in values.items() if name in declared}
        )


def route_model(route: ModelRoute) -> str:
    """`chain[0]` as a fallback model id, for the rare response with an empty `model`."""
    return route.chain[0]


def _classify(error: ProviderError) -> AnalysisError:
    """Map a router-level `ProviderError` to the failure code an assessment persists."""
    if error.kind is ErrorKind.QUOTA:
        return AnalysisError(AnalysisFailureCode.QUOTA_EXHAUSTED, error.summary)
    if error.kind is ErrorKind.INVALID_OUTPUT:
        return AnalysisError(AnalysisFailureCode.SCHEMA_MISMATCH, error.summary)
    if error.kind is ErrorKind.CONFIGURATION:
        return AnalysisError(AnalysisFailureCode.NOT_CONFIGURED, error.summary)
    if error.kind is ErrorKind.REQUEST:
        return AnalysisError(AnalysisFailureCode.SERVER_ERROR, f"request rejected: {error.summary}")
    # ErrorKind.TRANSIENT: the provider distinguishes timeout, connection and 5xx only
    # through `status` and the wording of `summary` (SPEC 43 section 5).
    if error.status is not None and 500 <= error.status < 600:
        return AnalysisError(AnalysisFailureCode.SERVER_ERROR, error.summary, retryable=True)
    if "timed out" in error.summary:
        return AnalysisError(AnalysisFailureCode.TIMEOUT, error.summary)
    if "could not connect" in error.summary:
        return AnalysisError(AnalysisFailureCode.TRANSPORT_ERROR, error.summary, retryable=True)
    return AnalysisError(AnalysisFailureCode.SERVER_ERROR, error.summary, retryable=True)


def _response_metrics(response: LLMResponse) -> AnalysisMetrics:
    return AnalysisMetrics(
        total_ms=response.latency_ms,
        prompt_tokens=response.usage.prompt_tokens,
        prompt_eval_ms=response.usage.prompt_ms,
        output_tokens=response.usage.completion_tokens,
        eval_ms=response.usage.completion_ms,
    )


def _with_size(metrics: AnalysisMetrics | None, size: AnalysisMetrics) -> AnalysisMetrics:
    return replace(
        metrics or AnalysisMetrics(),
        prompt_chars=size.prompt_chars,
        prompt_tokens_estimate=size.prompt_tokens_estimate,
    )


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = ["GroqAnalysisAdapter"]
