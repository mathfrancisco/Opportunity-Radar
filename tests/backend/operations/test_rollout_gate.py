from __future__ import annotations

from datetime import UTC, datetime

from opportunity_radar.operations.rollout_gate import evaluate_rollout_evidence


def _evidence() -> dict[str, object]:
    return {
        "manifest": {
            "version": "v1",
            "cohort_frozen": True,
            "cohort_hash": "fixture-cohort-hash",
            "collector_version": "fixture-collector",
            "parser_version": "fixture-parser",
            "source_ids": ["source-1"],
        },
        "window": {"start_utc": "2026-10-01T00:00:00Z", "end_utc": "2026-10-08T00:00:00Z"},
        "ci": {
            "sha": "abc",
            "url": "https://ci.example/run/1",
            "result": "passed",
            "image_digest": "sha256:123",
        },
        "runtime": {"sha": "abc", "image_digest": "sha256:123"},
        "sources": [
            {
                "source_id": "source-1",
                "inventories": [
                    {
                        "run_id": f"run-{i}",
                        "status": "SUCCEEDED",
                        "complete": True,
                        "trigger": "scheduled",
                        "finished_at_utc": f"2026-10-0{i + 2}T00:00:00Z",
                    }
                    for i in range(3)
                ]
                + [
                    {
                        "run_id": "backfill",
                        "status": "SUCCEEDED",
                        "complete": True,
                        "trigger": "backfill",
                        "finished_at_utc": "2026-10-05T00:00:00Z",
                    }
                ],
                "useful_descriptions": {"numerator": 95, "denominator": 100},
                "human_recall": {"numerator": 95, "denominator": 100},
                "last_complete_inventory_utc": "2026-10-06T00:00:00Z",
            }
        ],
        "ai_terminal": {"numerator": 100, "denominator": 100},
        "restore_validation": {
            "environment": "isolated_test",
            "status": "passed",
            "operational_target": False,
            "before_hash": "abc",
            "after_hash": "abc",
        },
        "rollback_validation": {
            "environment": "isolated_test",
            "status": "passed",
            "operational_target": False,
            "before_hash": "abc",
            "after_hash": "abc",
        },
        "operational_approval": {
            "status": "approved",
            "owner": "test-owner",
            "signed_decision_hash": "fixture-signature-hash",
        },
        "expansions": {"F51-14": "deferred", "F51-15": "deferred", "F51-16": "deferred"},
    }


def test_rollout_gate_requires_complete_core_evidence_and_ignores_deferred_expansions() -> None:
    report = evaluate_rollout_evidence(_evidence(), now=datetime(2026, 10, 8, tzinfo=UTC))
    assert report["decision"] == "go"
    assert report["gates"]["sources"]["source-1"]["complete_distinct_inventories"]["value"] == 3
    assert report["evidence_authenticated"] is False


def test_rollout_gate_treats_missing_denominators_and_sha_drift_as_no_go() -> None:
    evidence = _evidence()
    evidence["ci"] = {"sha": "old", "url": "https://ci.example/run/1", "result": "passed"}
    evidence["sources"] = []
    evidence["ai_terminal"] = {"numerator": 0, "denominator": 0}
    report = evaluate_rollout_evidence(evidence, now=datetime(2026, 10, 8, tzinfo=UTC))
    assert report["decision"] == "no-go"
    assert report["gates"]["ci_runtime"]["value"] == "N/D"
    assert report["gates"]["ai_terminal"]["passes"] is False


def test_rollout_gate_rejects_backfill_as_inventory_and_freshness_outside_window() -> None:
    evidence = _evidence()
    source = evidence["sources"][0]  # type: ignore[index]
    source["inventories"] = [
        {
            "run_id": f"backfill-{i}",
            "status": "SUCCEEDED",
            "complete": True,
            "trigger": "backfill",
            "finished_at_utc": "2026-10-05T00:00:00Z",
        }
        for i in range(3)
    ]
    source["inventories"].extend(
        {
            "run_id": f"old-scheduled-{i}",
            "status": "SUCCEEDED",
            "complete": True,
            "trigger": "scheduled",
            "finished_at_utc": f"2026-09-2{i}T00:00:00Z",
        }
        for i in range(5, 8)
    )
    source["inventories"].append(
        {
            "run_id": "recent-backfill",
            "status": "SUCCEEDED",
            "complete": True,
            "trigger": "backfill",
            "finished_at_utc": "2026-10-07T00:00:00Z",
        }
    )
    source["last_complete_inventory_utc"] = "2026-09-01T00:00:00Z"
    report = evaluate_rollout_evidence(evidence, now=datetime(2026, 10, 8, tzinfo=UTC))
    checks = report["gates"]["sources"]["source-1"]
    assert checks["complete_distinct_inventories"]["passes"] is False
    assert checks["freshness_within_7_days"]["value"] == "N/D"


def test_rollout_gate_rejects_short_or_future_window_and_out_of_window_runs() -> None:
    evidence = _evidence()
    evidence["window"] = {"start_utc": "2026-10-02T00:00:00Z", "end_utc": "2026-10-08T00:00:00Z"}
    source = evidence["sources"][0]  # type: ignore[index]
    for run in source["inventories"][:3]:
        run["finished_at_utc"] = "2026-10-01T12:00:00Z"
    report = evaluate_rollout_evidence(evidence, now=datetime(2026, 10, 8, tzinfo=UTC))
    assert report["decision"] == "no-go"
    assert report["gates"]["window"]["passes"] is False
    assert report["gates"]["sources"]["source-1"]["complete_distinct_inventories"]["value"] == 0

    evidence["window"] = {"start_utc": "2026-10-01T00:00:00Z", "end_utc": "2026-10-09T00:00:00Z"}
    report = evaluate_rollout_evidence(evidence, now=datetime(2026, 10, 8, tzinfo=UTC))
    assert report["gates"]["window"]["passes"] is False


def test_rollout_gate_rejects_duplicate_and_malformed_sources_without_crashing() -> None:
    evidence = _evidence()
    evidence["sources"] = [evidence["sources"][0], evidence["sources"][0], None]  # type: ignore[index]
    report = evaluate_rollout_evidence(evidence, now=datetime(2026, 10, 8, tzinfo=UTC))
    assert report["decision"] == "no-go"
    assert report["gates"]["sources"]["cohort"]["value"] == "N/D"

    evidence["sources"] = []
    evidence["window"] = None
    report = evaluate_rollout_evidence(evidence, now=datetime(2026, 10, 8, tzinfo=UTC))
    assert report["decision"] == "no-go"
