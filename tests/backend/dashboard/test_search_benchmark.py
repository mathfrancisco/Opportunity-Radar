import pytest

from opportunity_radar.dashboard.search_benchmark import (
    FTS_INDEX_CONFIG,
    REQUIRED_QUERY_CATEGORIES,
    SEARCH_BENCHMARK_VERSION,
    _query_execution_contract,
    canonical_hash,
    compare_snapshots,
    ensure_live_corpus_matches,
    precision_recall_at_k,
    summarize_latencies,
    summarize_raw_latencies,
    validate_frozen_manifest,
)


def _manifest() -> dict:
    queries = [
        {"query": category, "category": category} for category in sorted(REQUIRED_QUERY_CATEGORIES)
    ]
    opportunity_id = "00000000-0000-0000-0000-000000000001"
    gold = []
    for index, query in enumerate(queries):
        label = "relevant" if index == 0 else "not_relevant"
        gold.append(
            {
                "query": query["query"],
                "opportunity_id": opportunity_id,
                "eligible": True,
                "human_label": label,
                "relevant": label == "relevant",
                "judgments": [
                    {"reviewer_id": reviewer, "label": label}
                    for reviewer in ("reviewer-a", "reviewer-b")
                ],
            }
        )
    manifest = {
        "version": SEARCH_BENCHMARK_VERSION,
        "frozen": True,
        "captured_at": "2026-10-05T12:00:00Z",
        "index_config": FTS_INDEX_CONFIG,
        "cohort": [opportunity_id],
        "corpus": [{"opportunity_id": opportunity_id, "payload_hash": "payload-v1"}],
        "queries": queries,
        "gold": gold,
        "reviewers": ["reviewer-a", "reviewer-b"],
        "query_execution": _query_execution_contract(),
        "collector_version": "benchmark-collector-v1",
        "snapshot_provenance": {"snapshot": "fixture"},
    }
    manifest["hashes"] = {
        key: canonical_hash(manifest[key])
        for key in ("cohort", "corpus", "gold", "index_config", "reviewers")
    }
    manifest["hashes"]["queries"] = canonical_hash(
        {"execution": manifest["query_execution"], "queries_and_filters": queries}
    )
    manifest["hashes"]["query_hash"] = manifest["hashes"]["queries"]
    return manifest


def test_frozen_manifest_checks_reviewers_and_hashes() -> None:
    manifest = _manifest()
    hashes = validate_frozen_manifest(manifest)
    assert hashes["corpus"] == manifest["hashes"]["corpus"]
    manifest["corpus"][0]["payload_hash"] = "changed"
    with pytest.raises(ValueError, match="hashes"):
        validate_frozen_manifest(manifest)


def test_manifest_rejects_conflicting_labels_and_unlisted_reviewers() -> None:
    manifest = _manifest()
    manifest["gold"][0]["relevant"] = False
    manifest["hashes"]["gold"] = canonical_hash(manifest["gold"])
    with pytest.raises(ValueError, match="conflicts"):
        validate_frozen_manifest(manifest)
    manifest = _manifest()
    manifest["gold"][0]["judgments"][1]["reviewer_id"] = "unlisted"
    manifest["hashes"]["gold"] = canonical_hash(manifest["gold"])
    with pytest.raises(ValueError, match="declared"):
        validate_frozen_manifest(manifest)


def test_manifest_requires_two_judgments_for_every_query_and_cohort_item() -> None:
    manifest = _manifest()
    manifest["gold"].pop()
    manifest["hashes"]["gold"] = canonical_hash(manifest["gold"])
    with pytest.raises(ValueError, match="incomplete"):
        validate_frozen_manifest(manifest)


def test_manifest_rejects_query_text_reused_with_different_filters() -> None:
    manifest = _manifest()
    duplicate = {**manifest["queries"][0], "filters": {"allowed_country": "BR"}}
    manifest["queries"].append(duplicate)
    with pytest.raises(ValueError, match="unique"):
        validate_frozen_manifest(manifest)


def test_manifest_rejects_eligibility_that_conflicts_with_human_label() -> None:
    manifest = _manifest()
    manifest["gold"][0]["eligible"] = False
    manifest["hashes"]["gold"] = canonical_hash(manifest["gold"])
    with pytest.raises(ValueError, match="eligibility"):
        validate_frozen_manifest(manifest)


@pytest.mark.parametrize("label", ["outside_area", "out_of_scope", "inaccessible"])
def test_manifest_accepts_two_reviewer_concurrence_on_exclusion(label: str) -> None:
    manifest = _manifest()
    row = manifest["gold"][0]
    row["human_label"] = label
    row["eligible"] = False
    row["relevant"] = False
    row["exclusion_reason"] = "Human reviewed exclusion reason"
    row["judgments"] = [
        {"reviewer_id": reviewer, "label": label}
        for reviewer in ("reviewer-a", "reviewer-b")
    ]
    # This case tests an allowed exclusion. Keep a distinct human-reviewed relevant
    # case because recall is undefined for a benchmark with no relevant gold at all.
    relevant = manifest["gold"][1]
    relevant["human_label"] = "relevant"
    relevant["eligible"] = True
    relevant["relevant"] = True
    relevant["judgments"] = [
        {"reviewer_id": reviewer, "label": "relevant"}
        for reviewer in ("reviewer-a", "reviewer-b")
    ]
    manifest["hashes"]["gold"] = canonical_hash(manifest["gold"])
    assert validate_frozen_manifest(manifest)["gold"] == manifest["hashes"]["gold"]


def test_manifest_rejects_disagreement_on_human_exclusion() -> None:
    manifest = _manifest()
    row = manifest["gold"][0]
    row["human_label"] = "outside_area"
    row["eligible"] = False
    row["relevant"] = False
    row["exclusion_reason"] = "Human reviewed exclusion reason"
    row["judgments"] = [
        {"reviewer_id": "reviewer-a", "label": "outside_area"},
        {"reviewer_id": "reviewer-b", "label": "relevant"},
    ]
    manifest["hashes"]["gold"] = canonical_hash(manifest["gold"])
    with pytest.raises(ValueError, match="disagree"):
        validate_frozen_manifest(manifest)


def test_manifest_needs_every_benchmark_category() -> None:
    manifest = _manifest()
    manifest["queries"] = manifest["queries"][:-1]
    manifest["hashes"]["queries"] = canonical_hash(manifest["queries"])
    with pytest.raises(ValueError, match="categories"):
        validate_frozen_manifest(manifest)


def test_precision_uses_k_slots_and_recall_uses_full_gold_denominator() -> None:
    ranked = [str(i) for i in range(8)] + ["x", "y", "8", "9", "10"]
    relevant = {str(i) for i in range(13)}
    at_10 = precision_recall_at_k(ranked, relevant, k=10)
    at_20 = precision_recall_at_k(ranked, relevant, k=20)
    assert at_10["precision_at_k"] == 0.8
    assert at_10["recall_at_k"] == 8 / 13
    assert at_20["precision_at_k"] == 11 / 20
    assert at_20["recall_at_k"] == 11 / 13
    assert precision_recall_at_k([], relevant, k=10)["precision_returned"] is None
    assert precision_recall_at_k([], relevant, k=10)["precision_at_k"] == 0


def test_sparse_results_keep_k_slots_and_report_returned_precision() -> None:
    metrics = precision_recall_at_k(["relevant"], {"relevant"}, k=10)
    assert metrics["precision_at_k"] == 0.1
    assert metrics["precision_returned"] == 1
    assert metrics["recall_at_k"] == 1


def test_live_corpus_must_match_frozen_payload_hashes() -> None:
    frozen = [{"opportunity_id": "job-1", "payload_hash": "a"}]
    ensure_live_corpus_matches(frozen, list(frozen))
    with pytest.raises(ValueError, match="differs"):
        ensure_live_corpus_matches(frozen, [{"opportunity_id": "job-1", "payload_hash": "b"}])


def test_latency_keeps_cold_and_warm_denominators_separate() -> None:
    report = summarize_latencies([10, 20, 30, 40, 50], list(range(10, 20)))
    assert report["cold"]["count"] == 5
    assert report["cold"]["status"] == "measured"
    assert report["warm"]["count"] == 10
    assert report["warm"]["status"] == "measured"
    assert summarize_latencies([1], [1])["warm"]["p95_ms"] is None


def test_cold_timing_is_not_reported_without_isolated_cache_reset_evidence() -> None:
    report = summarize_raw_latencies(list(range(10)), [1, 2, 3, 4, 5])
    assert report["warm"]["status"] == "measured"
    assert report["cold"]["status"] == "insufficient_need_5"
    assert report["raw_ms"]["cold"] == []

    evidence = [
        {
            "isolated_test_environment": True,
            "cache_state": "cold",
            "cache_reset_performed": True,
            "method": "isolated cache reset",
            "evidence_ref": f"run-{index}",
        }
        for index in range(5)
    ]
    measured = summarize_raw_latencies(
        list(range(10)), [1, 2, 3, 4, 5], cold_cache_evidence=evidence
    )
    assert measured["cold"]["status"] == "measured"


def test_content_delta_requires_fixed_cohort_queries_gold_and_filters() -> None:
    left = {
        "cohort_hash": "c",
        "query_hash": "q",
        "gold_hash": "g",
        "filter_hash": "f",
        "corpus_hash": "a",
    }
    right = {**left, "corpus_hash": "b"}
    assert compare_snapshots(left, right) == {
        "content_comparison": "comparable",
        "algorithm_comparison": "not_comparable",
        "payload_changed": True,
    }
    assert (
        compare_snapshots(left, {**right, "gold_hash": "changed"})["content_comparison"]
        == "not_comparable"
    )
