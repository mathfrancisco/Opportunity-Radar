"""Ollama adapter for structured semantic analysis.

Infrastructure only. The domain never sees `/api/chat`: it depends on
`SemanticAnalysisPort` and receives an `AnalysisOutcome` that is already classified,
so an unavailable or misbehaving model degrades the assessment instead of failing it.
"""

from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx

from opportunity_radar.matching.analysis import (
    ANALYSIS_SCHEMA_VERSION,
    AnalysisError,
    AnalysisFailureCode,
    AnalysisOutcome,
    AnalysisPolicy,
    AnalysisRequest,
    SemanticAnalysis,
    analysis_cache_key,
    completed_outcome,
    failed_outcome,
    parse_analysis,
    skipped_outcome,
)
from opportunity_radar.matching.prompts import (
    DEFAULT_PROMPT_NAME,
    PROMPT_FAMILY,
    PromptArtifacts,
    load_prompt,
)

DEFAULT_PROMPT_VERSION = f"{PROMPT_FAMILY}/{DEFAULT_PROMPT_NAME}"
_CHAT_PATH = "/api/chat"


class _AnalysisCache:
    """Bounded in-memory cache. Section 40: the key already covers every relevant input."""

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
        policy: AnalysisPolicy | None = None,
        prompt: PromptArtifacts | None = None,
        cache_max_entries: int = 256,
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
        self._policy = policy or AnalysisPolicy()
        self._prompt = prompt or load_prompt()
        self._cache = _AnalysisCache(cache_max_entries)

    @property
    def model(self) -> str:
        return self._model

    @property
    def prompt_version(self) -> str:
        return self._prompt.version

    async def analyze(self, request: AnalysisRequest) -> AnalysisOutcome:
        """Never raises for an external failure: callers get a classified outcome."""
        if not self._policy.should_analyze(request):
            return skipped_outcome("policy skipped the semantic layer for this assessment")

        key = analysis_cache_key(
            request,
            model_id=self._model,
            prompt_version=self._prompt.version,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return completed_outcome(cached)

        try:
            analysis = await self._analyze_with_retries(request)
        except AnalysisError as error:
            return failed_outcome(error)
        self._cache.set(key, analysis)
        return completed_outcome(analysis)

    async def _analyze_with_retries(self, request: AnalysisRequest) -> SemanticAnalysis:
        last_error: AnalysisError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await self._analyze_once(request)
            except AnalysisError as error:
                last_error = error
                if not error.retryable or attempt == self._max_retries:
                    raise
                await self._sleeper(self._retry_after_seconds)
        assert last_error is not None
        raise last_error

    async def _analyze_once(self, request: AnalysisRequest) -> SemanticAnalysis:
        if self._client is not None:
            return await self._analyze_with_client(self._client, request)
        async with self._client_factory() as client:
            return await self._analyze_with_client(client, request)

    async def _analyze_with_client(
        self, client: httpx.AsyncClient, request: AnalysisRequest
    ) -> SemanticAnalysis:
        try:
            response = await client.post(
                f"{self._base_url}{_CHAT_PATH}",
                json=self._chat_payload(request),
            )
        except httpx.TimeoutException as error:
            raise AnalysisError(
                AnalysisFailureCode.TIMEOUT,
                "ollama analysis request timed out",
                retryable=True,
            ) from error
        except httpx.TransportError as error:
            raise AnalysisError(
                AnalysisFailureCode.TRANSPORT_ERROR,
                "could not connect to ollama",
                retryable=True,
            ) from error

        self._raise_for_status(response)
        return parse_analysis(
            self._content(response),
            model_id=self._model,
            prompt_version=self._prompt.version,
        )

    def _chat_payload(self, request: AnalysisRequest) -> dict[str, Any]:
        return {
            "model": self._model,
            "stream": False,
            "format": self._prompt.output_schema,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": self._prompt.system},
                {"role": "user", "content": self._user_content(request)},
            ],
        }

    def _user_content(self, request: AnalysisRequest) -> str:
        """Render the versioned template. Values arrive JSON-encoded, so the result parses."""
        deterministic_result = {
            "eligibility": request.eligibility.value,
            "verdict": request.verdict.value,
            "score": str(request.score),
            "rules_version": request.rules_version,
            "taxonomy_version": request.taxonomy_version,
            "authoritative": True,
        }
        return self._prompt.render_user(
            {
                "schema_version": _encode(ANALYSIS_SCHEMA_VERSION),
                "deterministic_result": _encode(deterministic_result),
                "opportunity": _encode(dict(request.opportunity_snapshot)),
                "profile": _encode(dict(request.profile_snapshot)),
            }
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
    def _content(response: httpx.Response) -> Any:
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


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


__all__ = ["DEFAULT_PROMPT_VERSION", "OllamaAnalysisAdapter"]
