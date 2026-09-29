"""Errors a `LLMProvider` raises, classified so a router (F20-10) can react without
inspecting HTTP status codes or exception types itself.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opportunity_radar.platform.ai.router import Attempt


class ErrorKind(StrEnum):
    """How a call failed, not why. The router decides retry/fallback from this alone."""

    TRANSIENT = "transient"  # timeout, connection error, 5xx
    QUOTA = "quota"  # 429
    INVALID_OUTPUT = "invalid_output"  # body without valid JSON, or outside the schema
    CONFIGURATION = "configuration"  # 401, 403, 404
    REQUEST = "request"  # 400, 413, 422


class ProviderError(Exception):
    """Raised by a `LLMProvider` for every non-success call.

    `summary` never carries the API key (SPEC 43, section 5): callers must not build it
    from an unredacted response body.
    """

    def __init__(
        self,
        kind: ErrorKind,
        summary: str,
        *,
        status: int | None = None,
        retry_after_seconds: float | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(summary)
        self.kind = kind
        self.summary = summary
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        self.model = model
        # Filled by `AIRouter.run` (card F20-19) right before it re-raises, so a caller
        # can record per-call telemetry even for a call that never returned a response.
        self.attempts: tuple["Attempt", ...] = ()
