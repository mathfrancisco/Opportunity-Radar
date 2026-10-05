"""F48-06/07: the doctor renders the funnel, the north-star and the collection gap."""

from __future__ import annotations

from datetime import UTC, datetime

from opportunity_radar.dashboard.funnel import FunnelReport, FunnelStage, NorthStar, Ratio
from opportunity_radar.operations.collection_alarm import CollectionGapReport
from scripts.doctor import OK, WARN, describe_collection_gap, describe_funnel

NOW = datetime(2026, 9, 29, tzinfo=UTC)


def _report(*, forbidden: int = 0) -> FunnelReport:
    return FunnelReport(
        generated_at=NOW,
        stages=(FunnelStage("open", "Open", 10, 2), FunnelStage("raw_items", "Raw", 5)),
        north_star=NorthStar(("DATA",), True, 4, 1, 24, (("open", 10), ("area", 4))),
        guards={"seniority_unknown": Ratio(1, 4), "useful_verdict": Ratio(0, 0)},
        forbidden_hosts_touched=forbidden,
    )


def test_funnel_facts_list_stages_north_star_and_guards() -> None:
    check = describe_funnel(_report())

    assert check.status == OK
    assert check.facts["stage.open"] == "10 (lost 2)"
    assert check.facts["stage.raw_items"] == "5"
    assert check.facts["north_star.stock"] == 4
    assert check.facts["north_star.new_24h"] == 1
    assert "technical proxy" in check.facts["north_star.areas"]
    assert check.facts["guard.seniority_unknown"] == "1/4 (25.0%)"
    assert check.facts["guard.useful_verdict"] == "0/0 (n/a)"
    assert "false_closures" in check.facts["guard.not_measured"]


def test_a_forbidden_host_reference_warns() -> None:
    assert describe_funnel(_report(forbidden=2)).status == WARN


def test_collection_gap_ok_and_warn_rendering() -> None:
    quiet = CollectionGapReport(NOW, 2.0, 3, 21600.0, NOW, False, ())
    assert describe_collection_gap(quiet).status == OK

    broken = CollectionGapReport(NOW, 2.0, 3, 21600.0, NOW, True, ())
    check = describe_collection_gap(broken)
    assert check.status == WARN
    assert "no scheduled run anywhere" in check.detail
