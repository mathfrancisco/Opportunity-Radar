"""The soak window is a gate, so it has to fail when the window does not hold."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import pytest

from opportunity_radar.operations.soak import OUTAGE_STEPS, run_soak
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

#: Long enough to contain the scripted outage and its recovery, short enough for a test.
TEST_HOURS = max(OUTAGE_STEPS) + 4


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]  # the rest comes from the environment
        ollama_analysis_enabled=False,
    )


def test_the_window_holds_and_reports_what_it_proved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])

    with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
        result = run_soak(
            engine,
            _settings(),
            hours=TEST_HOURS,
            step_minutes=60,
            start=datetime.now(UTC),
        )

    failures = [check for check in result.checks if not check.passed]
    assert not failures, [check.detail for check in failures]
    assert {check.name for check in result.checks} == {
        "jobs",
        "collection",
        "alerting",
        "metrics",
        "retention",
    }
    assert result.steps == TEST_HOURS
    assert result.passed is True
    assert not any(
        "embed" in record.getMessage().casefold()
        for record in caplog.records
        if record.name == "opportunity_radar.worker"
    )


def test_a_window_too_short_to_recover_fails_the_gate() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])

    # Stopping inside the outage means the incident is open at the end. A gate that still
    # passed there would pass for a system that is down when the operator comes back.
    result = run_soak(
        engine,
        _settings(),
        hours=min(OUTAGE_STEPS) + 2,
        step_minutes=60,
        start=datetime.now(UTC),
    )

    assert result.passed is False
    assert any(
        check.name == "alerting" and not check.passed for check in result.checks
    )
