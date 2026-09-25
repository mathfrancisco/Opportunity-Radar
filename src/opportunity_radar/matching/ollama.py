"""Ollama adapter for structured semantic analysis.

Infrastructure only. The domain never sees `/api/chat`: it depends on
`SemanticAnalysisPort` and receives an `AnalysisOutcome` that is already classified,
so an unavailable or misbehaving model degrades the assessment instead of failing it.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from typing import Any

import httpx

from opportunity_radar.matching.analysis import (
    AnalysisError,
    AnalysisFailureCode,
    AnalysisMetrics,
    AnalysisOutcome,
    AnalysisPolicy,
    AnalysisRequest,
    PreparedAnalysis,
    SemanticAnalysis,
    analysis_key,
    completed_outcome,
    evidence_sources,
    failed_outcome,
    parse_analysis,
    payload_digest,
    skipped_outcome,
)
from opportunity_radar.matching.prompts import (
    DEFAULT_PROMPT_NAME,
    PROMPT_FAMILY,
    PromptArtifacts,
    load_prompt,
)
from opportunity_radar.matching.text import (
    CLEANER_VERSION,
    DEFAULT_TOKENS_PER_CHAR,
    clean_description_report,
    estimate_tokens,
    fit_description,
    prompt_budget,
    truncate_at_sentence,
)

DEFAULT_PROMPT_VERSION = f"{PROMPT_FAMILY}/{DEFAULT_PROMPT_NAME}"
_CHAT_PATH = "/api/chat"
_GENERATE_PATH = "/api/generate"
_VERSION_PATH = "/api/version"
_TAGS_PATH = "/api/tags"
_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")
_DURATION_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
#: Rounds of re-fitting when JSON escaping made the rendered prompt longer than planned.
_FIT_ROUNDS = 3


class _AnalysisCache:
    """Bounded in-memory cache, keyed by the same `analysis-key-v2` as the table."""

    def __init__(self, max_entries: int) -> None:
        self._max_entries = max(0, max_entries)
        self._entries: OrderedDict[str, SemanticAnalysis] = OrderedDict()

    def get(self, key: str) -> SemanticAnalysis | None:
        if self._max_entries == 0:
            return None
        analysis = self._entries.get(key)
        if analysis is not None:
            self._entries.move_to_end(key)
        return analysis

    def set(self, key: str, analysis: SemanticAnalysis) -> None:
        if self._max_entries == 0:
            return
        self._entries[key] = analysis
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def __len__(self) -> int:
        return len(self._entries)


class OllamaAnalysisAdapter:
    """Calls a local Ollama model and returns validated structured analysis."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        client_factory: (
            Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None
        ) = None,
        timeout_seconds: float = 30.0,
        connect_timeout_seconds: float = 5.0,
        max_retries: int = 1,
        retry_after_seconds: float = 0.5,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
        clock: Callable[[], float] = time.monotonic,
        policy: AnalysisPolicy | None = None,
        prompt: PromptArtifacts | None = None,
        cache_max_entries: int = 256,
        num_ctx: int | None = None,
        num_predict: int | None = None,
        seed: int | None = None,
        keep_alive: str | None = None,
        think: bool | None = None,
    ) -> None:
        if client is not None and client_factory is not None:
            raise ValueError("provide either client or client_factory, not both")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_after_seconds < 0:
            raise ValueError("retry_after_seconds cannot be negative")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = client
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=connect_timeout_seconds,
                    read=timeout_seconds,
                    write=timeout_seconds,
                    pool=connect_timeout_seconds,
                )
            )
        )
        self._max_retries = max_retries
        self._retry_after_seconds = retry_after_seconds
        self._sleeper = sleeper
        self._jitter = jitter
        self._clock = clock
        self._last_call_at: float | None = None
        self._policy = policy or AnalysisPolicy()
        self._prompt = prompt or load_prompt()
        self._cache = _AnalysisCache(cache_max_entries)
        self._num_ctx = num_ctx
        self._num_predict = num_predict
        self._seed = seed
        self._keep_alive = keep_alive
        self._residency_seconds = _keep_alive_seconds(keep_alive)
        self._think = think
        # What `describe` found about the server; recorded with every later analysis.
        self._server: dict[str, Any] = {}

    @property
    def model(self) -> str:
        return self._model

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
        """Build, measure, fit and key the exact payload an analysis would send.

        The fixed parts — instructions, deterministic result, snapshots, profile — go in
        whole; if they alone exceed the budget, nothing is sent. The posting's description
        takes what is left, cleaned and cut at a sentence boundary, and the retrieved
        decisions give way before the description does. Every cut is recorded.
        """
        ratio, margin = self._ratio_and_margin(request)
        budget = (
            prompt_budget(self._num_ctx, self._num_predict or 0, margin)
            if self._num_ctx is not None
            else None
        )
        posting = dict(request.posting or {}) if "posting" in self.requires else None
        cleaned = clean_description_report(str((posting or {}).get("description") or ""))
        decisions = [dict(item) for item in request.similar_decisions or ()]
        offered = len(decisions)
        description = cleaned.text
        truncated = False

        def render(text: str, cut: bool, context: Sequence[Mapping[str, Any]]) -> str:
            return self._user_content(request, posting, text, cut, context)

        def estimate(content: str) -> int:
            return estimate_tokens(len(self._prompt.system) + len(content), ratio)

        overflow = False
        if budget is not None:
            if estimate(render("", False, [])) > budget:
                overflow = True
            elif posting is not None:
                # Retrieved context is cut before the description is (card F16-11).
                while True:
                    available = budget - estimate(render("", False, decisions))
                    fitted = fit_description(
                        cleaned.text, available_tokens=available, tokens_per_char=ratio
                    )
                    if fitted.truncated and decisions:
                        decisions.pop()
                        continue
                    description, truncated = fitted.text, fitted.truncated
                    break
                # JSON escaping can make the rendered text longer than the plain one.
                for _ in range(_FIT_ROUNDS):
                    excess = estimate(render(description, truncated, decisions)) - budget
                    if excess <= 0:
                        break
                    shorter = max(0, len(description) - int(excess / ratio) - 1)
                    description, _ = truncate_at_sentence(description, shorter)
                    truncated = True

        user_content = render(description, truncated, decisions)
        payload: dict[str, Any] = json.loads(user_content)
        size = AnalysisMetrics(
            prompt_chars=len(self._prompt.system) + len(user_content),
            prompt_tokens_estimate=estimate(user_content),
        )
        options = self._options()
        inference: dict[str, Any] = {
            "model": self._model,
            "prompt_version": self._prompt.version,
            "prompt_digest": self._prompt.digest,
            "schema_version": self._prompt.schema_version,
            "options": options,
            "keep_alive": self._keep_alive,
            "tokens_per_char": ratio,
            "calibration": (
                request.calibration.as_dict()
                if request.calibration is not None
                else {"state": "uncalibrated", "samples": 0, "ratio": ratio}
            ),
            "prompt_budget": budget,
            **self._server,
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
                model_id=self._model,
                prompt_version=self._prompt.version,
                schema_version=self._prompt.schema_version,
                prompt_digest=self._prompt.digest,
                payload_hash=payload_hash,
                options={**options, "think": self._think},
            ),
            payload_hash=payload_hash,
            payload=payload,
            inference=inference,
            size=size,
            system=self._prompt.system,
            user_content=user_content,
            prompt_budget=budget,
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

        `use_cache=False` is the refresh and the evaluation: they must reach the model
        even when an identical answer is in memory.
        """
        if not self._policy.should_analyze(request):
            return skipped_outcome("policy skipped the semantic layer for this assessment")

        prepared = prepared or self.prepare(request)
        if use_cache:
            cached = self._cache.get(prepared.cache_key)
            if cached is not None:
                return completed_outcome(cached)

        if prepared.overflow:
            # Sending it would let the server cut the instructions off the front.
            overflow = AnalysisError(
                AnalysisFailureCode.CONTEXT_OVERFLOW,
                f"prompt needs about {prepared.size.prompt_tokens_estimate} tokens; "
                f"the budget is {prepared.prompt_budget}",
            )
            overflow.metrics = prepared.size
            return failed_outcome(overflow)
        try:
            analysis, metrics = await self._analyze_with_retries(prepared)
        except AnalysisError as error:
            error.metrics = _with_size(error.metrics, prepared.size)
            return failed_outcome(error)
        self._cache.set(prepared.cache_key, analysis)
        return completed_outcome(analysis, _with_size(metrics, prepared.size))

    def _ratio_and_margin(self, request: AnalysisRequest) -> tuple[float, int | None]:
        calibration = request.calibration
        if calibration is not None and self._num_ctx is not None:
            return calibration.ratio, calibration.margin(self._num_ctx, self._num_predict or 0)
        return request.tokens_per_char or DEFAULT_TOKENS_PER_CHAR, None

    def _options(self) -> dict[str, Any]:
        options: dict[str, Any] = dict(self._prompt.sampling)
        if self._num_ctx is not None:
            options["num_ctx"] = self._num_ctx
        if self._num_predict is not None:
            options["num_predict"] = self._num_predict
        if self._seed is not None:
            options["seed"] = self._seed
        return options

    async def warm_up(self, *, only_if_idle: bool = False) -> AnalysisMetrics | None:
        """Load the model before the queue needs it, and report what the load cost.

        An empty generate request loads the model into memory and keeps it there for
        `keep_alive`, so the first real analysis does not pay for loading five gigabytes.
        With `only_if_idle`, the request is sent only when the last call is older than
        `keep_alive`, which is when the server has unloaded the model. Returns `None` when
        nothing was loaded. Never raises: a server that is down is the queue's problem to
        degrade, not the worker's startup's.
        """
        if only_if_idle and not self._idle():
            return None
        payload: dict[str, Any] = {"model": self._model, "prompt": ""}
        if self._keep_alive is not None:
            payload["keep_alive"] = self._keep_alive
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self._base_url}{_GENERATE_PATH}", json=payload
                )
            else:
                async with self._client_factory() as client:
                    response = await client.post(
                        f"{self._base_url}{_GENERATE_PATH}", json=payload
                    )
        except httpx.HTTPError:
            return None
        if not 200 <= response.status_code < 300:
            return None
        self._last_call_at = self._clock()
        try:
            envelope = response.json()
        except ValueError:
            return None
        return _metrics(envelope) if isinstance(envelope, dict) else None

    async def describe(self) -> Mapping[str, Any]:
        """Server version and the digest the tag resolves to; whatever cannot be read is
        left out. Remembered, so every later analysis records the same identity."""
        found: dict[str, Any] = {}
        try:
            if self._client is not None:
                found = await self._describe_with(self._client)
            else:
                async with self._client_factory() as client:
                    found = await self._describe_with(client)
        except httpx.HTTPError:
            return dict(self._server)
        self._server.update(found)
        return dict(self._server)

    async def _describe_with(self, client: httpx.AsyncClient) -> dict[str, Any]:
        found: dict[str, Any] = {}
        version = await client.get(f"{self._base_url}{_VERSION_PATH}")
        if version.status_code == 200:
            body = _json_object(version)
            if isinstance(body.get("version"), str):
                found["server_version"] = body["version"]
        tags = await client.get(f"{self._base_url}{_TAGS_PATH}")
        if tags.status_code == 200:
            models = _json_object(tags).get("models")
            for item in models if isinstance(models, list) else []:
                if isinstance(item, dict) and self._model in (item.get("name"), item.get("model")):
                    if isinstance(item.get("digest"), str):
                        found["model_digest"] = item["digest"]
        return found

    async def _analyze_with_retries(
        self, prepared: PreparedAnalysis
    ) -> tuple[SemanticAnalysis, AnalysisMetrics | None]:
        last_error: AnalysisError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._analyze_once(prepared)
            except AnalysisError as error:
                last_error = error
                if not error.retryable or attempt == self._max_retries:
                    raise
                # Exponential with jitter, so a restarting server is not hit in lockstep.
                delay = self._retry_after_seconds * 2**attempt
                await self._sleeper(delay * (1 + self._jitter() / 4))
        assert last_error is not None
        raise last_error

    async def _analyze_once(
        self, prepared: PreparedAnalysis
    ) -> tuple[SemanticAnalysis, AnalysisMetrics | None]:
        if self._client is not None:
            return await self._analyze_with_client(self._client, prepared)
        async with self._client_factory() as client:
            return await self._analyze_with_client(client, prepared)

    async def _analyze_with_client(
        self, client: httpx.AsyncClient, prepared: PreparedAnalysis
    ) -> tuple[SemanticAnalysis, AnalysisMetrics | None]:
        try:
            response = await client.post(
                f"{self._base_url}{_CHAT_PATH}",
                json=self._chat_payload(prepared),
            )
        except httpx.TimeoutException as error:
            # Not retried here: the same input would time out again at once. The queue's
            # cooldown is the retry for a timeout.
            raise AnalysisError(
                AnalysisFailureCode.TIMEOUT,
                "ollama analysis request timed out",
            ) from error
        except httpx.TransportError as error:
            raise AnalysisError(
                AnalysisFailureCode.TRANSPORT_ERROR,
                "could not connect to ollama",
                retryable=True,
            ) from error

        self._last_call_at = self._clock()
        self._raise_for_status(response)
        envelope = self._envelope(response)
        metrics = _metrics(envelope)
        try:
            analysis = parse_analysis(
                self._content(envelope),
                model_id=self._model,
                prompt_version=self._prompt.version,
                schema_version=self._prompt.schema_version,
                evidence_sources=prepared.evidence_sources,
            )
        except AnalysisError as error:
            error.metrics = metrics
            raise
        return analysis, metrics

    def _idle(self) -> bool:
        if self._last_call_at is None:
            return True
        if self._residency_seconds is None:
            return False
        return self._clock() - self._last_call_at >= self._residency_seconds

    def _chat_payload(self, prepared: PreparedAnalysis) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "format": self._prompt.output_schema,
            "options": self._options(),
            "messages": [
                {"role": "system", "content": prepared.system},
                {"role": "user", "content": prepared.user_content},
            ],
        }
        if self._keep_alive is not None:
            payload["keep_alive"] = self._keep_alive
        if self._think is not None:
            payload["think"] = self._think
        return payload

    def _user_content(
        self,
        request: AnalysisRequest,
        posting: Mapping[str, Any] | None,
        description: str,
        truncated: bool,
        decisions: Sequence[Mapping[str, Any]],
    ) -> str:
        """Render the versioned template. Values arrive JSON-encoded, so the result parses.

        Only the variables the template declares are rendered, so `v1` keeps sending
        exactly the snapshots it always did.
        """
        deterministic_result = {
            "eligibility": request.eligibility.value,
            "verdict": request.verdict.value,
            "score": str(request.score),
            "rules_version": request.rules_version,
            "taxonomy_version": request.taxonomy_version,
            "authoritative": True,
        }
        profile = dict(request.profile_snapshot)
        if self._prompt.reads_profile_history:
            profile.update(dict(request.profile_history or {}))
        values = {
            "schema_version": _encode(self._prompt.schema_version),
            "deterministic_result": _encode(deterministic_result),
            "opportunity": _encode(dict(request.opportunity_snapshot)),
            "profile": _encode(profile),
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

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 404:
            raise AnalysisError(
                AnalysisFailureCode.MODEL_UNAVAILABLE,
                "ollama does not have the analysis model installed",
            )
        if status == 429:
            raise AnalysisError(
                AnalysisFailureCode.RATE_LIMITED,
                "ollama rate limited the analysis request",
                retryable=True,
            )
        if 500 <= status < 600:
            raise AnalysisError(
                AnalysisFailureCode.SERVER_ERROR,
                f"ollama returned HTTP {status}",
                retryable=True,
            )
        raise AnalysisError(
            AnalysisFailureCode.SERVER_ERROR,
            f"ollama returned HTTP {status}",
        )

    @staticmethod
    def _envelope(response: httpx.Response) -> dict[str, Any]:
        try:
            envelope = response.json()
        except ValueError as error:
            raise AnalysisError(
                AnalysisFailureCode.INVALID_JSON,
                "ollama returned a non-JSON envelope",
                retryable=True,
            ) from error
        if not isinstance(envelope, dict):
            raise AnalysisError(
                AnalysisFailureCode.INVALID_JSON,
                "ollama envelope must be an object",
                retryable=True,
            )
        return envelope

    @staticmethod
    def _content(envelope: dict[str, Any]) -> Any:
        message = envelope.get("message")
        if not isinstance(message, dict):
            raise AnalysisError(
                AnalysisFailureCode.INVALID_JSON,
                "ollama envelope is missing the message object",
                retryable=True,
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AnalysisError(
                AnalysisFailureCode.EMPTY_RESPONSE,
                "ollama returned an empty analysis content",
                retryable=True,
            )
        try:
            return json.loads(content)
        except ValueError as error:
            raise AnalysisError(
                AnalysisFailureCode.INVALID_JSON,
                "ollama analysis content is not valid JSON",
                retryable=True,
            ) from error


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _metrics(envelope: dict[str, Any]) -> AnalysisMetrics:
    """Durations arrive in nanoseconds; anything missing or malformed stays absent."""

    def milliseconds(key: str) -> int | None:
        value = envelope.get(key)
        return value // 1_000_000 if isinstance(value, int) and value >= 0 else None

    def count(key: str) -> int | None:
        value = envelope.get(key)
        return value if isinstance(value, int) and value >= 0 else None

    return AnalysisMetrics(
        total_ms=milliseconds("total_duration"),
        load_ms=milliseconds("load_duration"),
        prompt_tokens=count("prompt_eval_count"),
        prompt_eval_ms=milliseconds("prompt_eval_duration"),
        output_tokens=count("eval_count"),
        eval_ms=milliseconds("eval_duration"),
    )


def _keep_alive_seconds(keep_alive: str | None) -> float | None:
    """How long the server keeps the model loaded; `None` when it never unloads it.

    Ollama takes a Go duration (`30m`, `1h30m`) or a bare number of seconds, and a
    negative value keeps the model resident. An unset or unreadable value falls back to
    the server default of five minutes, which errs towards warming up.
    """
    value = (keep_alive or "").strip()
    if not value:
        return 300.0
    try:
        seconds = float(value)
    except ValueError:
        parts = _DURATION_PART.findall(value.lstrip("-"))
        if not parts or "".join(n + u for n, u in parts) != value.lstrip("-"):
            return 300.0
        seconds = sum(float(n) * _DURATION_SECONDS[u] for n, u in parts)
        if value.startswith("-"):
            seconds = -seconds
    return None if seconds < 0 else seconds


def _with_size(metrics: AnalysisMetrics | None, size: AnalysisMetrics) -> AnalysisMetrics:
    return replace(
        metrics or AnalysisMetrics(),
        prompt_chars=size.prompt_chars,
        prompt_tokens_estimate=size.prompt_tokens_estimate,
    )


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = ["DEFAULT_PROMPT_VERSION", "OllamaAnalysisAdapter"]
