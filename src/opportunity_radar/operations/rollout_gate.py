"""Offline validator for F51-18 rollout evidence; it never observes or changes runtime state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _number(metric: Any) -> float | None:
    if not isinstance(metric, dict):
        return None
    numerator, denominator = metric.get("numerator"), metric.get("denominator")
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, (int, float))
        or not isinstance(denominator, (int, float))
        or denominator <= 0
        or numerator < 0
        or numerator > denominator
    ):
        return None
    return numerator / denominator


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def evaluate_rollout_evidence(evidence: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Return fail-closed metric gates from a caller-supplied, versioned evidence package.

    A missing, empty, malformed, or incompatible observation is N/D and blocks go. This
    function does not authenticate signatures or verify that evidence was actually observed.
    """
    gates: dict[str, dict[str, Any]] = {}
    window = evidence.get("window", {})
    start: datetime | None = None
    end: datetime | None = None
    try:
        start = datetime.fromisoformat(window["start_utc"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(window["end_utc"].replace("Z", "+00:00"))
        seven_day_window = (
            start.tzinfo is not None
            and end.tzinfo is not None
            and end - start >= timedelta(days=7)
            and end <= now
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        seven_day_window = False
    gates["window"] = {
        "value": "observed" if seven_day_window else "N/D",
        "passes": seven_day_window,
    }

    manifest = evidence.get("manifest", {})
    raw_source_ids = manifest.get("source_ids") if isinstance(manifest, dict) else None
    source_ids_valid = isinstance(raw_source_ids, list) and all(
        isinstance(item, str) and item for item in raw_source_ids
    )
    declared_source_ids: list[str] = (
        [item for item in raw_source_ids if isinstance(item, str)]
        if isinstance(raw_source_ids, list)
        else []
    )
    cohort_ok = bool(
        isinstance(manifest, dict)
        and manifest.get("version")
        and manifest.get("cohort_frozen") is True
        and manifest.get("cohort_hash")
        and manifest.get("collector_version")
        and manifest.get("parser_version")
        and source_ids_valid
        and bool(declared_source_ids)
        and len(declared_source_ids) == len(set(declared_source_ids))
    )
    gates["cohort_provenance"] = {
        "value": "declared" if cohort_ok else "N/D",
        "passes": cohort_ok,
    }

    ci = evidence.get("ci", {})
    runtime = evidence.get("runtime", {})
    compatible = bool(
        isinstance(ci, dict)
        and isinstance(runtime, dict)
        and ci.get("sha")
        and ci.get("sha") == runtime.get("sha")
        and ci.get("image_digest") == runtime.get("image_digest")
        and runtime.get("image_digest")
        and ci.get("url")
        and ci.get("result") == "passed"
    )
    gates["ci_runtime"] = {"value": "compatible" if compatible else "N/D", "passes": compatible}

    sources = evidence.get("sources")
    source_checks: dict[str, Any] = {}
    source_ids: list[str] = []
    source_entries = sources if isinstance(sources, list) else []
    valid_sources = isinstance(sources, list) and bool(source_entries)
    if valid_sources:
        for source in source_entries:
            if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
                valid_sources = False
                continue
            source_ids.append(source["source_id"])
    valid_sources = valid_sources and len(source_ids) == len(set(source_ids))
    source_cohort_ok = bool(
        valid_sources and cohort_ok and set(source_ids) == set(declared_source_ids)
    )
    source_checks["cohort"] = {
        "value": "matched" if source_cohort_ok else "N/D",
        "passes": source_cohort_ok,
    }
    if valid_sources:
        for source in source_entries:
            name = source["source_id"]
            runs = source.get("inventories", [])
            inventory_times: dict[str, datetime] = {}
            conflicting_run_ids: set[str] = set()
            if isinstance(runs, list):
                for run in runs:
                    if not isinstance(run, dict):
                        continue
                    finished = _timestamp(run.get("finished_at_utc"))
                    if (
                        run.get("status") == "SUCCEEDED"
                        and run.get("complete") is True
                        and run.get("trigger") != "backfill"
                        and isinstance(run.get("run_id"), str)
                        and run.get("run_id")
                        and finished is not None
                        and start is not None
                        and end is not None
                        and finished <= now
                        and start <= finished <= end
                    ):
                        run_id = run["run_id"]
                        if run_id in inventory_times and inventory_times[run_id] != finished:
                            conflicting_run_ids.add(run_id)
                        inventory_times[run_id] = finished
            for duplicate_id in conflicting_run_ids:
                inventory_times.pop(duplicate_id, None)
            count_ok = len(inventory_times) >= 3
            useful = _number(source.get("useful_descriptions"))
            latest_complete = max(inventory_times.values(), default=None)
            freshness_ok = bool(
                latest_complete is not None
                and timedelta(0) <= now - latest_complete <= timedelta(days=7)
            )
            recall = _number(source.get("human_recall"))
            source_checks[name] = {
                "complete_distinct_inventories": {
                    "value": len(inventory_times),
                    "passes": count_ok,
                },
                "useful_description_rate": {
                    "value": useful,
                    "passes": useful is not None and useful >= 0.95,
                },
                "human_recall": {"value": recall, "passes": recall is not None and recall >= 0.95},
                "freshness_within_7_days": {
                    "value": (
                        latest_complete.isoformat()
                        if freshness_ok and latest_complete is not None
                        else "N/D"
                    ),
                    "passes": freshness_ok,
                },
            }
    gates["sources"] = source_checks

    ai = evidence.get("ai_terminal")
    ai_rate = _number(ai)
    gates["ai_terminal"] = {
        "value": ai_rate,
        "passes": ai_rate == 1.0,
    }
    restore = evidence.get("restore_validation", {})
    restore_ok = bool(
        isinstance(restore, dict)
        and restore.get("environment") == "isolated_test"
        and restore.get("status") == "passed"
        and restore.get("operational_target") is False
        and restore.get("before_hash")
        and restore.get("before_hash") == restore.get("after_hash")
    )
    gates["restore_validation"] = {
        "value": "declared_isolated_pass" if restore_ok else "N/D",
        "passes": restore_ok,
    }
    rollback = evidence.get("rollback_validation", {})
    rollback_ok = bool(
        isinstance(rollback, dict)
        and rollback.get("environment") == "isolated_test"
        and rollback.get("status") == "passed"
        and rollback.get("operational_target") is False
        and rollback.get("before_hash")
        and rollback.get("before_hash") == rollback.get("after_hash")
    )
    gates["rollback_validation"] = {
        "value": "declared_isolated_pass" if rollback_ok else "N/D",
        "passes": rollback_ok,
    }
    approval = evidence.get("operational_approval", {})
    approval_present = bool(
        isinstance(approval, dict)
        and approval.get("status") == "approved"
        and approval.get("owner")
        and approval.get("signed_decision_hash")
    )
    gates["operational_approval"] = {
        "value": "declared" if approval_present else "N/D",
        "passes": approval_present,
    }
    # F14-F16 are optional expansion work and do not affect the core decision.
    core_checks = [
        gates["window"],
        gates["cohort_provenance"],
        gates["ci_runtime"],
        gates["ai_terminal"],
        gates["restore_validation"],
        gates["rollback_validation"],
        gates["operational_approval"],
        source_checks["cohort"],
    ]
    for source_result in source_checks.values():
        if isinstance(source_result, dict) and source_result is not source_checks["cohort"]:
            core_checks.extend(source_result.values())
    go = bool(core_checks) and all(check.get("passes") is True for check in core_checks)
    return {
        "decision": "go" if go else "no-go",
        "gates": gates,
        "expansions": evidence.get(
            "expansions", {"F51-14": "deferred", "F51-15": "deferred", "F51-16": "deferred"}
        ),
        "evidence_authenticated": False,
        "rollout_authorized": False,
        "limitations": [
            "Offline validation only; declarations are not authenticated observations, signatures, "
            "A declared go is not rollout authorization."
        ],
    }
