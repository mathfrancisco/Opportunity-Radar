"""R55-A5: the registry the finite window and the worker build serves every probeable type."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from opportunity_radar import worker
from opportunity_radar.acquisition.probing import PROBE_TYPES
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.platform.config import Settings


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
