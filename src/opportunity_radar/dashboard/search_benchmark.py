"""Frozen-manifest helpers for the FTS relevance benchmark (F51-17)."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
from collections import Counter
from typing import Any
from uuid import UUID

SEARCH_BENCHMARK_VERSION = "search-benchmark-v1"
QUERY_EXECUTION_VERSION = "opportunity-inbox-query-v1"
REQUIRED_QUERY_CATEGORIES = {"pt", "en", "synonym", "ambiguous", "filter", "zero", "specific"}
FTS_INDEX_CONFIG = {
    "search_document_migration": "20260925_0028",
    "search_document_languages": ["portuguese", "english"],
    "search_document_weights": {
        "title_company": "A",
        "skills_role": "B",
        "description": "C",
        "location": "D",
    },
    "query": "websearch_to_tsquery_bilingual_or",
    "rank": "ts_rank_cd",
    "synonyms_version": "synonyms-v1",
}


def _query_execution_contract() -> dict[str, str]:
    from opportunity_radar.dashboard import queries, search_synonyms

    return {
        "version": QUERY_EXECUTION_VERSION,
        "implementation_sha256": hashlib.sha256(
            (inspect.getsource(queries) + inspect.getsource(search_synonyms)).encode("utf-8")
        ).hexdigest(),
    }


def canonical_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def ensure_live_corpus_matches(
    frozen_corpus: list[dict[str, Any]], live_corpus: list[dict[str, Any]]
) -> None:
    if canonical_hash(live_corpus) != canonical_hash(frozen_corpus):
        raise ValueError("current database corpus differs from frozen manifest; benchmark refused")


def validate_frozen_manifest(manifest: dict[str, Any]) -> dict[str, str]:
    """Require frozen data hashes and two reviewers before running ranked queries."""
    if manifest.get("version") != SEARCH_BENCHMARK_VERSION or manifest.get("frozen") is not True:
        raise ValueError("manifest must be frozen and use search-benchmark-v1")
    for key in (
        "captured_at",
        "index_config",
        "cohort",
        "corpus",
        "queries",
        "gold",
        "query_execution",
        "collector_version",
        "snapshot_provenance",
    ):
        if key not in manifest:
            raise ValueError(f"manifest missing {key}")
    reviewers = manifest.get("reviewers")
    if not isinstance(reviewers, list) or len(set(reviewers)) < 2:
        raise ValueError("gold requires at least two independent reviewer IDs")
    if not isinstance(manifest["queries"], list) or not manifest["queries"]:
        raise ValueError("manifest queries must be a non-empty frozen list")
    if manifest["index_config"] != FTS_INDEX_CONFIG:
        raise ValueError("manifest index_config does not match the implemented FTS baseline")
    if manifest["query_execution"] != _query_execution_contract():
        raise ValueError("manifest query execution contract differs from current query code")
    categories = {query.get("category") for query in manifest["queries"]}
    missing = REQUIRED_QUERY_CATEGORIES - categories
    if missing:
        raise ValueError(f"manifest is missing query categories: {', '.join(sorted(missing))}")
    queries = manifest["queries"]
    query_texts = [item.get("query") for item in queries]
    if len(query_texts) != len(set(query_texts)):
        raise ValueError("query text must be unique; gold is keyed by query text")
    query_hash = canonical_hash(
        {"execution": manifest["query_execution"], "queries_and_filters": queries}
    )
    hashes = {key: canonical_hash(manifest[key]) for key in ("cohort", "corpus", "gold")}
    hashes["queries"] = query_hash
    hashes["query_hash"] = query_hash
    hashes["index_config"] = canonical_hash(manifest["index_config"])
    hashes["reviewers"] = canonical_hash(reviewers)
    declared = manifest.get("hashes")
    if not isinstance(declared, dict) or any(
        declared.get(key) != digest for key, digest in hashes.items()
    ):
        raise ValueError("manifest hashes do not match frozen cohort/corpus/queries/gold")
    query_texts_set = set(query_texts)
    if any(
        not item.get("query") or item["query"] not in query_texts_set for item in manifest["gold"]
    ):
        raise ValueError("gold rows must name a frozen query")
    corpus_ids = {
        str(item.get("opportunity_id")) if isinstance(item, dict) else str(item)
        for item in manifest["corpus"]
    }
    if {str(item) for item in manifest["cohort"]} != corpus_ids:
        raise ValueError("frozen cohort must exactly match frozen corpus membership")
    seen_labels: dict[tuple[str, str], str] = {}
    judgments: dict[tuple[str, str], set[str]] = {}
    reviewer_ids = set(reviewers)
    for item in manifest["gold"]:
        row_judgments = item.get("judgments")
        if not isinstance(row_judgments, list):
            raise ValueError("each query/cohort gold row requires two human judgments")
        row_reviewers = {judgment.get("reviewer_id") for judgment in row_judgments}
        if len(row_reviewers) < 2 or not row_reviewers <= reviewer_ids:
            raise ValueError("each gold row requires two declared independent reviewers")
        for judgment in row_judgments:
            if judgment.get("label") not in {
                "relevant",
                "not_relevant",
                "outside_area",
                "out_of_scope",
                "inaccessible",
            }:
                raise ValueError("each reviewer must provide a supported human judgment")
        if len({judgment["label"] for judgment in row_judgments}) != 1:
            raise ValueError("reviewer judgments disagree; adjudication is required")
        if item.get("human_label") not in {
            "relevant",
            "not_relevant",
            "outside_area",
            "out_of_scope",
            "inaccessible",
        }:
            raise ValueError("gold row has an unsupported human label")
        if item.get("eligible") is not (item["human_label"] in {"relevant", "not_relevant"}):
            raise ValueError("gold eligibility conflicts with its human label")
        if item["human_label"] != row_judgments[0]["label"]:
            raise ValueError("adjudicated human label conflicts with reviewer judgments")
        expected_relevant = item["human_label"] == "relevant"
        if "relevant" in item and item["relevant"] is not expected_relevant:
            raise ValueError("gold relevant flag conflicts with human_label")
        if item.get("human_label") in {
            "outside_area",
            "out_of_scope",
            "inaccessible",
        } and not item.get("exclusion_reason"):
            raise ValueError("human gold exclusions require a reason")
        try:
            opportunity_id = str(UUID(item["opportunity_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("gold rows require a valid opportunity_id") from exc
        if opportunity_id not in corpus_ids:
            raise ValueError("gold opportunity IDs must belong to the frozen corpus")
        label_key = (item["query"], opportunity_id)
        if label_key in seen_labels:
            raise ValueError("duplicate or contradictory query/opportunity gold row")
        seen_labels[label_key] = item["human_label"]
        judgments[label_key] = row_reviewers
    expected = {
        (str(query["query"]), str(opportunity_id))
        for query in queries
        for opportunity_id in corpus_ids
    }
    if set(seen_labels) != expected:
        raise ValueError("gold is incomplete: every query/cohort pair needs two human judgments")
    if not any(label == "relevant" for label in seen_labels.values()):
        raise ValueError("frozen gold must contain human-labeled relevant items")
    return hashes


def validate_cold_cache_evidence(evidence: Any) -> tuple[bool, str | None]:
    """Cold timing needs five distinct documented isolated cache-reset observations."""
    if not isinstance(evidence, list) or len(evidence) < 5:
        return False, None
    valid: list[dict[str, Any]] = []
    for item in evidence:
        if (
            not isinstance(item, dict)
            or item.get("isolated_test_environment") is not True
            or item.get("cache_state") != "cold"
            or item.get("cache_reset_performed") is not True
            or not isinstance(item.get("method"), str)
            or not item["method"].strip()
            or item["method"].strip().casefold() in {"new connection", "new_connection"}
            or not isinstance(item.get("evidence_ref"), str)
            or not item["evidence_ref"].strip()
        ):
            return False, None
        valid.append(item)
    refs = [item["evidence_ref"] for item in valid]
    if len(set(refs)) < 5:
        return False, None
    methods = {item["method"] for item in valid}
    return True, "; ".join(sorted(methods))


def summarize_raw_latencies(
    warm_ms: list[float],
    cold_ms: list[float] | None = None,
    *,
    cold_cache_evidence: Any = None,
) -> dict[str, Any]:
    evidence_ok, method = validate_cold_cache_evidence(cold_cache_evidence)
    cold = (cold_ms or []) if evidence_ok else []
    return {
        **summarize_latencies(cold, warm_ms),
        "raw_ms": {"cold": cold, "warm": warm_ms},
        "cold_condition": (
            method
            if evidence_ok
            else "N/D: five independently documented isolated cache resets are required"
        ),
        "cold_evidence_refs": [row["evidence_ref"] for row in cold_cache_evidence]
        if evidence_ok
        else [],
    }


def precision_recall_at_k(
    ranked_ids: list[str], relevant_ids: set[str], *, k: int
) -> dict[str, Any]:
    if k <= 0:
        raise ValueError("k must be positive")
    hits = len(set(ranked_ids[:k]) & relevant_ids)
    returned = min(k, len(ranked_ids))
    return {
        "k": k,
        "relevant_returned": hits,
        "returned": returned,
        "relevant_in_gold": len(relevant_ids),
        "precision_at_k": hits / k,
        "precision_returned": hits / returned if returned else None,
        "recall_at_k": hits / len(relevant_ids) if relevant_ids else None,
    }


def summarize_latencies(cold_ms: list[float], warm_ms: list[float]) -> dict[str, Any]:
    def summary(values: list[float], minimum: int) -> dict[str, Any]:
        if len(values) < minimum:
            return {
                "count": len(values),
                "p50_ms": None,
                "p95_ms": None,
                "status": f"insufficient_need_{minimum}",
            }
        ordered = sorted(values)

        def percentile(p: float) -> float:
            index = (len(ordered) - 1) * p
            lower = math.floor(index)
            upper = math.ceil(index)
            return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

        return {
            "count": len(values),
            "p50_ms": percentile(0.5),
            "p95_ms": percentile(0.95),
            "status": "measured",
        }

    return {"cold": summary(cold_ms, 5), "warm": summary(warm_ms, 10)}


def query_category_counts(queries: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(query["category"]) for query in queries))


def compare_snapshots(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Content deltas need a fixed cohort/gold; algorithm deltas need equal corpus."""
    stable = all(
        left.get(key) == right.get(key)
        for key in ("cohort_hash", "query_hash", "gold_hash", "filter_hash")
    )
    same_corpus = left.get("corpus_hash") == right.get("corpus_hash")
    same_algorithm = left.get("index_config_hash") == right.get("index_config_hash")
    return {
        "content_comparison": "comparable" if stable else "not_comparable",
        "algorithm_comparison": (
            "comparable" if stable and same_corpus and same_algorithm else "not_comparable"
        ),
        "payload_changed": stable and not same_corpus,
    }
