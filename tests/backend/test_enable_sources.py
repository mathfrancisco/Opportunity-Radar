from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from opportunity_radar.acquisition.models import SourceDefinitionModel
from scripts import enable_sources
from scripts.enable_sources import ProbeResult, _homologation_audit, _probe_all, _probe_candidate


def test_probe_candidate_accepts_a_configured_disabled_ats_source() -> None:
    source = SourceDefinitionModel(
        source_type="ashby",
        name="Proposed board",
        enabled=False,
        configuration={"board_identifier": "example"},
    )

    assert _probe_candidate(source, include_remotive=True) is True


def test_probe_candidate_keeps_enabled_or_unconfigured_sources_out() -> None:
    enabled = SourceDefinitionModel(
        source_type="lever",
        name="Enabled source",
        enabled=True,
        configuration={"site_identifier": "example"},
    )
    incomplete = SourceDefinitionModel(
        source_type="greenhouse",
        name="Incomplete proposal",
        enabled=False,
        configuration={},
    )

    assert _probe_candidate(enabled, include_remotive=True) is False
    assert _probe_candidate(incomplete, include_remotive=True) is False


def test_homologation_audit_keeps_terms_gate_and_probe_evidence() -> None:
    reviewed_at = datetime(2026, 9, 22, 12, 30, tzinfo=UTC)

    audit = _homologation_audit(
        ProbeResult(
            source_id="source-id",
            source_name="Verified board",
            source_type="greenhouse",
            ok=True,
            detail="parsed",
            items_seen=1,
            http_requests=1,
        ),
        reviewed_at,
    )

    assert audit == {
        "public_endpoint_reference": "https://docs.greenhouse.io/job-board.html",
        "terms_review": "operator-confirmed via --accept-terms",
        "reviewed_at": "2026-09-22T12:30:00+00:00",
        "collector_local_test": {
            "status": "passed",
            "items_seen": 1,
            "http_requests": 1,
        },
    }


def _fake_result(source: SourceDefinitionModel) -> ProbeResult:
    return ProbeResult(
        source_id=str(source.id),
        source_name=source.name,
        source_type=source.source_type,
        ok=True,
        detail="ok",
    )


def test_probe_all_preserves_source_order_regardless_of_completion_order(monkeypatch) -> None:
    sources = [
        SourceDefinitionModel(
            source_type="ashby", name="A", enabled=False, configuration={"board_identifier": "a"}
        ),
        SourceDefinitionModel(
            source_type="lever", name="B", enabled=False, configuration={"site_identifier": "b"}
        ),
        SourceDefinitionModel(
            source_type="greenhouse",
            name="C",
            enabled=False,
            configuration={"board_token": "c"},
        ),
    ]
    # Each fake probe resolves in the opposite order of `sources`: if `_probe_all`
    # returned completion order instead of `sources`' own order, this would catch it.
    delays = {"A": 0.03, "B": 0.02, "C": 0.01}

    async def fake_probe(source: SourceDefinitionModel, registry, *, max_items: int) -> ProbeResult:
        await asyncio.sleep(delays[source.name])
        return _fake_result(source)

    monkeypatch.setattr(enable_sources, "_probe", fake_probe)

    results = asyncio.run(_probe_all(sources, registry=object(), max_items=1, concurrency=8))

    assert [result.source_name for result in results] == ["A", "B", "C"]


def test_probe_all_serializes_two_sources_on_the_same_provider_host(monkeypatch) -> None:
    sources = [
        SourceDefinitionModel(
            source_type="ashby",
            name="A1",
            enabled=False,
            configuration={"board_identifier": "a1"},
        ),
        SourceDefinitionModel(
            source_type="ashby",
            name="A2",
            enabled=False,
            configuration={"board_identifier": "a2"},
        ),
    ]
    active = 0
    max_active = 0

    async def fake_probe(source: SourceDefinitionModel, registry, *, max_items: int) -> ProbeResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return _fake_result(source)

    monkeypatch.setattr(enable_sources, "_probe", fake_probe)

    asyncio.run(_probe_all(sources, registry=object(), max_items=1, concurrency=8))

    assert max_active == 1  # same provider host: never more than one in flight


def test_probe_all_runs_different_provider_hosts_concurrently(monkeypatch) -> None:
    sources = [
        SourceDefinitionModel(
            source_type="ashby", name="A", enabled=False, configuration={"board_identifier": "a"}
        ),
        SourceDefinitionModel(
            source_type="lever", name="B", enabled=False, configuration={"site_identifier": "b"}
        ),
    ]
    active = 0
    max_active = 0

    async def fake_probe(source: SourceDefinitionModel, registry, *, max_items: int) -> ProbeResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return _fake_result(source)

    monkeypatch.setattr(enable_sources, "_probe", fake_probe)

    asyncio.run(_probe_all(sources, registry=object(), max_items=1, concurrency=8))

    assert max_active == 2  # different provider hosts: both in flight at once
