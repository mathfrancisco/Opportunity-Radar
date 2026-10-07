"""Default collection cadence per company priority, and the per-source-type overrides."""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.scheduling import (
    _cron_interval_seconds,
    default_schedule_for_priority,
)

_DEFAULT = {"high": "0 * * * *", "normal": "0 * * * *", "low": "0 */6 * * *"}
_WORKDAY = {"high": "0 */6 * * *", "normal": "0 0 * * *", "low": "0 0 * * 0"}
_INHIRE = {"high": "0 * * * *", "normal": "0 * * * *", "low": "0 0 * * *"}


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_default_cadence_per_priority(priority: str) -> None:
    assert default_schedule_for_priority(priority) == _DEFAULT[priority]


@pytest.mark.parametrize("source_type", ["greenhouse", "ashby", "lever"])
def test_normal_priority_of_a_regular_source_resolves_to_hourly(source_type: str) -> None:
    assert default_schedule_for_priority("normal", source_type=source_type) == "0 * * * *"


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_source_with_six_hour_minimum_never_runs_more_often_than_allowed(
    priority: str,
) -> None:
    schedule = default_schedule_for_priority(priority, minimum_run_interval_seconds=21_600)

    assert _cron_interval_seconds(schedule) >= 21_600
    assert schedule == "0 */6 * * *"


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_workday_keeps_the_old_cadence(priority: str) -> None:
    assert default_schedule_for_priority(priority, source_type="workday") == _WORKDAY[priority]


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_inhire_runs_hourly_or_daily(priority: str) -> None:
    assert default_schedule_for_priority(priority, source_type="inhire") == _INHIRE[priority]


def test_an_override_source_also_steps_down_for_its_minimum_run_interval() -> None:
    schedule = default_schedule_for_priority(
        "high", minimum_run_interval_seconds=21_600, source_type="inhire"
    )

    assert schedule == "0 0 * * *"
