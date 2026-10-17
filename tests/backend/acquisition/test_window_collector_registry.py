"""R55-A5: the registry the finite window and the worker build serves every probeable type."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from opportunity_radar import worker
from opportunity_radar.acquisition.probing import PROBE_TYPES
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.pipeline import Deadline, StageContext, StopSignal
from scripts import run_pipeline_once


@pytest.mark.parametrize("source_type", PROBE_TYPES)
def test_registry_resolves_every_probeable_source_type(source_type: str) -> None:
    registry = build_collector_registry(greenhouse_base_url="https://example.invalid")
    assert registry.resolve(source_type).source_type == source_type


def test_registry_resolves_teamtailor_and_workable_explicitly() -> None:
    registry = build_collector_registry(greenhouse_base_url="https://example.invalid")
    assert registry.resolve("teamtailor").source_type == "teamtailor"
    assert registry.resolve("workable").source_type == "workable"


@pytest.mark.parametrize("source_type", PROBE_TYPES)
def test_service_the_window_builds_resolves_every_probeable_source_type(
    source_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `collect_enabled_sources` (worker and finite window alike) takes its service from here.
    monkeypatch.setattr(worker, "active_profile_target_role_families", lambda *_: ())
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db_test",
        worker_owner_sub="worker-owner-synthetic",
    )
    service = worker.collection_service_factory(settings)(MagicMock())
    assert service.registry.resolve(source_type).source_type == source_type


_WINDOW_TYPES = ("workable", "teamtailor", "workday", "inhire")


def test_default_acquisition_service_registry_cannot_drift_from_the_deployment_one() -> None:
    service = AcquisitionService(MagicMock())
    for source_type in PROBE_TYPES:
        assert service.registry.resolve(source_type).source_type == source_type


def test_finite_window_collect_stage_resolves_every_window_source_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the stage once ran with the default service and its 5-collector registry."""
    monkeypatch.setattr(worker, "active_profile_target_role_families", lambda *_: ())
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db_test",
        worker_owner_sub="worker-owner-synthetic",
    )
    captured: dict[str, object] = {}

    def fake_collect(*args: object, **kwargs: object) -> dict[str, int]:
        captured.update(kwargs)
        return {"input": 0, "completed": 0, "failed": 0, "skipped": 0, "stopped": 0}

    monkeypatch.setattr(run_pipeline_once, "collect_enabled_sources", fake_collect)
    stages = {
        stage.name: stage for stage in run_pipeline_once._stages(object(), settings, {})
    }
    stages["collect_enabled_sources"].run(
        StageContext("worker-owner-synthetic", Deadline(60.0), StopSignal())
    )

    factory = captured["service_factory"]
    service = factory(MagicMock())  # type: ignore[operator]
    for source_type in _WINDOW_TYPES:
        assert service.registry.resolve(source_type).source_type == source_type
