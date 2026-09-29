"""Circuit breaker per model (SPEC 43, section 7.4).

Only `TRANSIENT` failures count. 429 is the Quota Guard's and the router's
`blocked_until` business (F20-10, F20-12), not the breaker's.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class _ModelState:
    state: BreakerState = BreakerState.CLOSED
    failures: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    """In-memory, per-model. Never persisted (state resets on restart, on purpose)."""

    def __init__(
        self,
        *,
        failures: int = 5,
        cooldown_seconds: float = 120,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failures
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._models: dict[str, _ModelState] = {}

    def _get(self, model: str) -> _ModelState:
        return self._models.setdefault(model, _ModelState())

    def allow(self, model: str) -> bool:
        entry = self._get(model)
        if entry.state is BreakerState.CLOSED:
            return True
        if entry.state is BreakerState.HALF_OPEN:
            # A probe is already in flight; do not let a second one through.
            return False
        # OPEN: past cooldown, let exactly one probe through and mark it half-open.
        if self._clock() - entry.opened_at >= self._cooldown_seconds:
            entry.state = BreakerState.HALF_OPEN
            return True
        return False

    def record_success(self, model: str) -> None:
        entry = self._get(model)
        entry.state = BreakerState.CLOSED
        entry.failures = 0

    def record_failure(self, model: str) -> None:
        entry = self._get(model)
        if entry.state is BreakerState.HALF_OPEN:
            self._open(entry)
            return
        entry.failures += 1
        if entry.failures >= self._failure_threshold:
            self._open(entry)

    def _open(self, entry: _ModelState) -> None:
        entry.state = BreakerState.OPEN
        entry.opened_at = self._clock()
        entry.failures = 0

    def state(self, model: str) -> BreakerState:
        return self._get(model).state

    def snapshot(self) -> dict[str, BreakerState]:
        return {model: entry.state for model, entry in self._models.items()}


__all__ = ["BreakerState", "CircuitBreaker"]
