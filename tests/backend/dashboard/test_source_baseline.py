from datetime import datetime, timedelta, timezone

from opportunity_radar.dashboard.source_baseline import (
    baseline_query_hash,
    classify_description,
)
from opportunity_radar.dashboard.source_quality import (
    recall_from_human_sample,
    summarize_source_quality,
)


def test_description_rule_is_versioned_and_keeps_missing_distinct() -> None:
    assert classify_description(None, "Engineer")["reason"] == "null_description"
    assert classify_description("  ", "Engineer")["reason"] == "empty_description"
    assert classify_description("Engineer", "Engineer")["reason"] == "title_only"
    assert classify_description("<div>Engineer role</div>", "Engineer")["reason"] == "html_residue"
    assert classify_description("403 Forbidden", "Engineer")["state"] == "invalid"
    assert (
        classify_description("Build reliable services for our customers.", "Engineer")["state"]
        == "useful"
    )
    assert (
        classify_description("Build reliable services for our customers.", "Engineer")[
            "rule_version"
        ]
        == "useful-description-v1"
    )


def test_baseline_query_hash_tracks_implementation_and_filter_definition() -> None:
    definition = {"version": "baseline-v1", "window": {"days": 7}}
    original = baseline_query_hash(definition, "implementation-a")
    assert original != baseline_query_hash(definition, "implementation-b")
    changed_filters = {**definition, "window": {"days": 14}}
    assert original != baseline_query_hash(changed_filters, "implementation-a")


def test_partial_run_does_not_refresh_complete_inventory() -> None:
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    completed_at = now - timedelta(days=3)
    report = summarize_source_quality(
        [{"id": "enabled", "enabled": True}, {"id": "disabled", "enabled": False}],
        [
            {
                "source_definition_id": "enabled",
                "status": "SUCCEEDED",
                "complete": True,
                "finished_at": completed_at,
            },
            {
                "source_definition_id": "enabled",
                "id": "partial-run",
                "status": "PARTIAL",
                "complete": False,
                "items_seen": 7,
                "items_persisted": 5,
                "items_invalid": None,
                "error_code": "SOURCE_RATE_LIMITED",
                "finished_at": now - timedelta(minutes=5),
            },
            {
                "source_definition_id": "enabled",
                "status": "SUCCEEDED",
                "complete": True,
                "finished_at": now + timedelta(days=1),
            },
        ],
        captured_at=now,
    )
    enabled = report["sources"][0]
    assert enabled["cadence"]["age_seconds"] == 300
    assert enabled["cadence"]["latest_attempt"] == {
        "run_id": "partial-run",
        "status": "PARTIAL",
        "complete": False,
        "items_announced": 7,
        "items_persisted": 5,
        "items_invalid": None,
        "error_code": "SOURCE_RATE_LIMITED",
    }
    assert enabled["inventory_freshness"]["age_seconds"] == 3 * 86400
    assert enabled["inventory_freshness"]["complete_runs_7d"] == 1
    assert report["freshness"] == {"numerator": 1, "denominator": 1, "status": "measured"}
    assert report["sources"][1]["eligible"] is False


def test_temporary_host_budget_block_degrades_but_stays_in_denominator() -> None:
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    report = summarize_source_quality(
        [
            {"id": "cooldown", "enabled": True, "cooldown_until": now + timedelta(hours=1)},
            {"id": "budget", "enabled": True, "host_budget_exhausted": True},
            {"id": "disabled", "enabled": False},
        ],
        [],
        captured_at=now,
    )
    assert report["freshness"]["denominator"] == 2
    assert report["sources"][0]["eligible"] is True
    assert report["sources"][0]["temporary_state"] == "host_budget_degraded"
    assert report["sources"][1]["eligible"] is True
    assert report["sources"][1]["cadence"]["degraded"] is True
    assert report["sources"][2]["eligibility_reason"] == "disabled_unclassified"


def test_recall_keeps_parser_misses_and_requires_human_exclusion_reason() -> None:
    report = recall_from_human_sample(
        [
            {"human_label": "eligible", "found": False, "parser_rejected": True},
            {"human_label": "eligible", "found": True},
            {
                "human_label": "outside_area",
                "found": False,
                "human_exclusion_reason": "reviewed location mismatch",
            },
        ]
    )
    assert report == {
        "numerator": 1,
        "denominator": 2,
        "excluded": 1,
        "sample_size": 3,
        "recall": 0.5,
        "status": "measured",
    }


def test_recall_without_human_sample_is_unmeasurable() -> None:
    assert recall_from_human_sample([])["recall"] is None
