"""Collection is general by default (owner decision 2026-10-19, R55-B5 follow-up)."""

from __future__ import annotations

import pytest

from opportunity_radar.platform.config import Settings


def test_prefilter_and_off_target_retention_are_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLLECTION_PREFILTER_ENABLED", raising=False)
    monkeypatch.delenv("OPPORTUNITY_OFF_TARGET_RETENTION_DAYS", raising=False)
    settings = Settings(_env_file=None)
    assert settings.collection_prefilter_enabled is False
    assert settings.opportunity_off_target_retention_days == 0


def test_operator_can_still_turn_the_profile_prefilter_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLLECTION_PREFILTER_ENABLED", "true")
    monkeypatch.setenv("OPPORTUNITY_OFF_TARGET_RETENTION_DAYS", "2")
    settings = Settings(_env_file=None)
    assert settings.collection_prefilter_enabled is True
    assert settings.opportunity_off_target_retention_days == 2
