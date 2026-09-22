from opportunity_radar.acquisition.models import SourceDefinitionModel
from scripts.enable_sources import _probe_candidate


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
