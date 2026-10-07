"""Default collection cadence per company priority, and the Workday exception."""

from __future__ import annotations

import pytest

from opportunity_radar.acquisition.scheduling import (
    _cron_interval_seconds,
    default_schedule_for_priority,
)

_NEW = {"high": "0 */2 * * *", "normal": "0 */6 * * *", "low": "0 0 * * *"}
_OLD = {"high": "0 */6 * * *", "normal": "0 0 * * *", "low": "0 0 * * 0"}


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_new_default_cadence_per_priority(priority: str) -> None:
    assert default_schedule_for_priority(priority) == _NEW[priority]


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_source_with_six_hour_minimum_never_runs_more_often_than_allowed(
    priority: str,
) -> None:
    schedule = default_schedule_for_priority(priority, minimum_run_interval_seconds=21_600)

    assert schedule != "0 */2 * * *"
    assert _cron_interval_seconds(schedule) >= 21_600
    assert schedule == ("0 */6 * * *" if priority in ("high", "normal") else "0 0 * * *")


@pytest.mark.parametrize("priority", ["high", "normal", "low"])
def test_workday_keeps_the_old_cadence_and_other_types_get_the_new_one(
    priority: str,
) -> None:
    assert default_schedule_for_priority(priority, source_type="workday") == _OLD[priority]
    assert default_schedule_for_priority(priority, source_type="greenhouse") == _NEW[priority]
