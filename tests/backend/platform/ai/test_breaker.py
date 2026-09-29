from opportunity_radar.platform.ai.breaker import BreakerState, CircuitBreaker


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


def test_closed_by_default() -> None:
    breaker = CircuitBreaker()

    assert breaker.allow("m") is True
    assert breaker.state("m") is BreakerState.CLOSED


def test_opens_after_n_failures() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(failures=5, cooldown_seconds=120, clock=clock)

    for _ in range(4):
        breaker.record_failure("m")
    assert breaker.state("m") is BreakerState.CLOSED
    assert breaker.allow("m") is True

    breaker.record_failure("m")

    assert breaker.state("m") is BreakerState.OPEN
    assert breaker.allow("m") is False


def test_half_open_after_cooldown() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(failures=1, cooldown_seconds=120, clock=clock)
    breaker.record_failure("m")
    assert breaker.allow("m") is False

    clock.now = 119.9
    assert breaker.allow("m") is False

    clock.now = 120.0
    assert breaker.allow("m") is True
    assert breaker.state("m") is BreakerState.HALF_OPEN
    # A second probe must not slip through while the first is in flight.
    assert breaker.allow("m") is False


def test_success_closes() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(failures=1, cooldown_seconds=120, clock=clock)
    breaker.record_failure("m")
    clock.now = 200.0
    assert breaker.allow("m") is True

    breaker.record_success("m")

    assert breaker.state("m") is BreakerState.CLOSED
    assert breaker.allow("m") is True


def test_failure_in_half_open_reopens() -> None:
    clock = _FakeClock()
    breaker = CircuitBreaker(failures=1, cooldown_seconds=120, clock=clock)
    breaker.record_failure("m")
    clock.now = 200.0
    assert breaker.allow("m") is True

    breaker.record_failure("m")

    assert breaker.state("m") is BreakerState.OPEN
    clock.now = 200.0 + 119.0
    assert breaker.allow("m") is False
    clock.now = 200.0 + 120.0
    assert breaker.allow("m") is True


def test_quota_does_not_count() -> None:
    # The breaker only has `record_failure`/`record_success`: a caller that never calls
    # `record_failure` for a QUOTA/CONFIGURATION/REQUEST/INVALID_OUTPUT error (the
    # router's job, F20-10/F20-11) never trips the breaker on those.
    breaker = CircuitBreaker(failures=1)

    breaker.record_success("m")  # no-op if never failed

    assert breaker.state("m") is BreakerState.CLOSED
    assert breaker.allow("m") is True


def test_snapshot_reports_every_seen_model() -> None:
    breaker = CircuitBreaker(failures=1)
    breaker.record_failure("a")
    breaker.record_success("b")

    assert breaker.snapshot() == {"a": BreakerState.OPEN, "b": BreakerState.CLOSED}
