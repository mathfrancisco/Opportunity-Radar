from datetime import UTC, datetime

from opportunity_radar.acquisition.models import SourceDefinitionModel
from scripts.enable_sources import ProbeResult, _homologation_audit, _probe_candidate


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
