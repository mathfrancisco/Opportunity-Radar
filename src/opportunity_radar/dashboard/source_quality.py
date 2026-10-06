"""Pure source freshness, inventory, content, and human-recall metrics (F51-02)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

QUALITY_VERSION = "source-quality-v2"
COMPLETE_STATUSES = {"SUCCEEDED"}


def summarize_source_quality(
    sources: list[dict[str, Any]], runs: list[dict[str, Any]], *, captured_at: datetime
) -> dict[str, Any]:
    """Separate attempt cadence from freshness of last complete inventory."""
    runs_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        observed_at = run.get("finished_at") or run.get("started_at")
        if observed_at is not None and observed_at > captured_at:
            continue
        runs_by_source[str(run["source_definition_id"])].append(run)
    result: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source["id"])
        history = sorted(
            runs_by_source[source_id],
            key=lambda run: (
                run.get("finished_at")
                or run.get("started_at")
                or datetime.min.replace(tzinfo=captured_at.tzinfo)
            ),
            reverse=True,
        )
        latest = history[0] if history else None
        complete = next(
            (
                run
                for run in history
                if run.get("complete") is True and run.get("status") in COMPLETE_STATUSES
            ),
            None,
        )
        last_attempt = (latest.get("finished_at") or latest.get("started_at")) if latest else None
        last_inventory = (
            (complete.get("finished_at") or complete.get("started_at")) if complete else None
        )
        permanent_reason = source.get("permanent_block_reason")
        eligible = bool(source.get("enabled")) and not bool(permanent_reason)
        cooling_down = bool(source.get("cooldown_until") and source["cooldown_until"] > captured_at)
        budget_exhausted = bool(source.get("host_budget_exhausted"))
        temporarily_degraded = cooling_down or budget_exhausted
        complete_runs_7d = sum(
            run.get("complete") is True
            and run.get("status") in COMPLETE_STATUSES
            and run.get("finished_at") is not None
            and timedelta(0) <= captured_at - run["finished_at"] <= timedelta(days=7)
            for run in history
        )
        result.append(
            {
                "source_id": source_id,
                "enabled": bool(source.get("enabled")),
                "eligible": eligible,
                "eligibility_reason": (
                    "permanently_blocked:" + str(permanent_reason)
                    if permanent_reason
                    else "eligible"
                    if eligible
                    else "disabled_unclassified"
                ),
                "temporary_state": ("host_budget_degraded" if temporarily_degraded else "normal"),
                "cadence": {
                    "last_attempt_at": last_attempt,
                    "age_seconds": (captured_at - last_attempt).total_seconds()
                    if last_attempt
                    else None,
                    "last_status": latest.get("status") if latest else None,
                    "latest_attempt": (
                        {
                            "run_id": str(latest.get("id")) if latest.get("id") else None,
                            "status": latest.get("status"),
                            "complete": latest.get("complete"),
                            "items_announced": latest.get(
                                "items_announced", latest.get("items_seen")
                            ),
                            "items_persisted": latest.get("items_persisted"),
                            "items_invalid": latest.get("items_invalid"),
                            "error_code": latest.get("error_code"),
                        }
                        if latest
                        else None
                    ),
                    "denominator_included": eligible,
                    "degraded": temporarily_degraded,
                },
                "inventory_freshness": {
                    "last_complete_inventory_at": last_inventory,
                    "age_seconds": (captured_at - last_inventory).total_seconds()
                    if last_inventory
                    else None,
                    "complete_runs_7d": complete_runs_7d,
                    "denominator_included": eligible,
                    "degraded": temporarily_degraded,
                    "status": "measured" if complete else "not_measured",
                },
                "baseline_run_sufficiency": {
                    "complete_runs_7d": complete_runs_7d,
                    "status": "sufficient" if complete_runs_7d >= 3 else "insufficient",
                },
                "latest_run_content_counters": (
                    {
                        key: latest.get(key)
                        for key in (
                            "items_seen",
                            "items_persisted",
                            "items_invalid",
                            "items_target_area",
                            "items_off_target",
                        )
                    }
                    if latest
                    else None
                ),
            }
        )
    eligible_count = sum(row["eligible"] for row in result)
    fresh_count = sum(
        row["eligible"] and row["inventory_freshness"]["complete_runs_7d"] > 0 for row in result
    )
    return {
        "version": QUALITY_VERSION,
        "captured_at": captured_at,
        "window_days": 7,
        "sources": result,
        "freshness": {
            "numerator": fresh_count if eligible_count else None,
            "denominator": eligible_count if eligible_count else None,
            "status": "measured" if eligible_count else "unmeasurable_no_eligible_sources",
        },
        "baseline_run_sufficiency": {
            "eligible_sources": eligible_count,
            "sources_with_three_complete_runs": sum(
                row["eligible"] and row["baseline_run_sufficiency"]["status"] == "sufficient"
                for row in result
            ),
            "status": "insufficient_no_eligible_sources"
            if not eligible_count
            else (
                "sufficient"
                if all(
                    not row["eligible"] or row["baseline_run_sufficiency"]["status"] == "sufficient"
                    for row in result
                )
                else "insufficient"
            ),
        },
    }


def recall_from_human_sample(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate recall only from reviewed rows; parser rejections stay eligible."""
    if not rows:
        return {
            "numerator": None,
            "denominator": None,
            "excluded": 0,
            "sample_size": 0,
            "recall": None,
            "status": "unmeasurable_no_human_sample",
        }
    eligible: list[dict[str, Any]] = []
    excluded = 0
    for row in rows:
        label = row.get("human_label")
        reason = row.get("human_exclusion_reason")
        if label is None:
            raise ValueError("each recall sample row requires a human_label")
        if label == "eligible":
            eligible.append(row)
        elif label in {"outside_area", "out_of_scope", "inaccessible"} and reason:
            excluded += 1
        else:
            raise ValueError("recall exclusions require an allowed human label and reason")
    found = sum(bool(row.get("found")) for row in eligible)
    denominator = len(eligible)
    return {
        "numerator": found if denominator else None,
        "denominator": denominator if denominator else None,
        "excluded": excluded,
        "sample_size": len(rows),
        "recall": found / denominator if denominator else None,
        "status": "measured" if denominator else "unmeasurable_no_eligible_rows",
    }
