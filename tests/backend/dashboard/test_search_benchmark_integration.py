"""F51-17 AC01, AC02, AC04, AC05 end to end: the benchmark script against a `_test` database.

The corpus is whatever the database holds, frozen into a manifest built here from the same
rows the script reads, so the real `evaluate` runs: manifest hashes, ranked queries, paired
A/B report, and the warm/cold groups (the restart is a fake callable: no Compose is touched).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard.search_benchmark import (
    FTS_INDEX_CONFIG,
    REQUIRED_QUERY_CATEGORIES,
    SEARCH_BENCHMARK_VERSION,
    _query_execution_contract,
    canonical_hash,
    paired_report,
)
from opportunity_radar.dashboard.source_baseline import opportunity_search_payload_hash
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from scripts.search_benchmark import evaluate

from .test_queries import _company, _opportunity

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)
_QUERIES: list[dict[str, Any]] = [
    {"query": "engenheiro", "category": "pt"},
    {"query": "backend", "category": "en"},
    {"query": "developer", "category": "synonym"},
    {"query": "manager", "category": "ambiguous"},
    {
        "query": "engineer",
        "category": "filter",
        "filters": {"role_families": ["SOFTWARE_ENGINEERING"]},
    },
    {"query": "zzzqqqxxx", "category": "zero"},
    {"query": "kubernetes", "category": "specific"},
]
_REVIEWERS = ["reviewer-a", "reviewer-b"]


def _freeze(session: Session, relevant: set[tuple[str, str]]) -> dict[str, Any]:
    """A manifest over every opportunity row, labelled `relevant` for the given pairs only."""
    rows = session.execute(
        select(
            OpportunityModel.id,
            OpportunityModel.canonical_title,
            OpportunityModel.company_name,
            OpportunityModel.search_skills,
            OpportunityModel.role_family,
            OpportunityModel.description,
            OpportunityModel.location_text,
            OpportunityModel.search_document,
        ).order_by(OpportunityModel.id)
    ).all()
    corpus = [
        {
            "opportunity_id": str(row.id),
            "payload_hash": opportunity_search_payload_hash(
                {
                    "canonical_title": row.canonical_title,
                    "company_name": row.company_name,
                    "search_skills": row.search_skills,
                    "role_family": row.role_family,
                    "description": row.description,
                    "location_text": row.location_text,
                    "search_document": str(row.search_document)
                    if row.search_document is not None
                    else None,
                }
            ),
        }
        for row in rows
    ]
    gold = []
    for entry in _QUERIES:
        for member in corpus:
            label = (
                "relevant"
                if (entry["query"], member["opportunity_id"]) in relevant
                else "not_relevant"
            )
            gold.append(
                {
                    "query": entry["query"],
                    "opportunity_id": member["opportunity_id"],
                    "eligible": True,
                    "human_label": label,
                    "relevant": label == "relevant",
                    "judgments": [{"reviewer_id": r, "label": label} for r in _REVIEWERS],
                }
            )
    manifest: dict[str, Any] = {
        "version": SEARCH_BENCHMARK_VERSION,
        "frozen": True,
        "captured_at": NOW.isoformat(),
        "index_config": FTS_INDEX_CONFIG,
        "cohort": [member["opportunity_id"] for member in corpus],
        "corpus": corpus,
        "queries": _QUERIES,
        "gold": gold,
        "reviewers": _REVIEWERS,
        "query_execution": _query_execution_contract(),
        "collector_version": "benchmark-collector-v1",
        "snapshot_provenance": {"snapshot": "fixture"},
    }
    manifest["hashes"] = {
        key: canonical_hash(manifest[key])
        for key in ("cohort", "corpus", "gold", "index_config", "reviewers")
    }
    manifest["hashes"]["queries"] = canonical_hash(
        {"execution": manifest["query_execution"], "queries_and_filters": _QUERIES}
    )
    manifest["hashes"]["query_hash"] = manifest["hashes"]["queries"]
    return manifest


@pytest.fixture
def seeded() -> Iterator[tuple[Session, OpportunityModel]]:
    """One opportunity in the database, removed after the test."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Backend Engineer",
            published_at=NOW,
            role_family="SOFTWARE_ENGINEERING",
        )
        session.commit()
        try:
            yield session, target
        finally:
            session.rollback()
            session.execute(delete(OpportunityModel).where(OpportunityModel.id == target.id))
            session.execute(delete(Company).where(Company.id == company.id))
            session.commit()
    engine.dispose()


def test_search_benchmark_uses_frozen_manifest(
    seeded: tuple[Session, OpportunityModel],
) -> None:
    session, target = seeded
    manifest = _freeze(session, {("backend", str(target.id))})

    report = evaluate(session, manifest)

    for key in ("cohort", "corpus", "gold", "queries", "index_config", "reviewers"):
        assert report["hashes"][key] == manifest["hashes"][key]
    assert report["reviewers"] == _REVIEWERS
    tampered = {**manifest, "corpus": [*manifest["corpus"]]}
    tampered["corpus"][0] = {**tampered["corpus"][0], "payload_hash": "changed"}
    with pytest.raises(ValueError, match="hashes"):
        evaluate(session, tampered)


def test_benchmark_covers_language_ambiguity_filters_and_zero(
    seeded: tuple[Session, OpportunityModel],
) -> None:
    session, target = seeded
    assert {entry["category"] for entry in _QUERIES} == REQUIRED_QUERY_CATEGORIES

    report = evaluate(session, _freeze(session, {("backend", str(target.id))}))

    assert set(report["category_counts"]) == REQUIRED_QUERY_CATEGORIES
    by_query = {row["query"]: row for row in report["per_query"]}
    assert set(by_query) == {entry["query"] for entry in _QUERIES}
    zero = by_query["zzzqqqxxx"]
    assert zero["returned"] == 0  # reported, not omitted
    assert zero["metrics"]["at_10"]["precision_at_k"] == 0
    assert zero["metrics"]["at_10"]["precision_returned"] is None
    assert zero["metrics"]["at_10"]["recall_at_k"] is None  # no relevant item: N/D
    assert by_query["backend"]["gold_relevant"] == 1
    assert by_query["backend"]["metrics"]["at_10"]["recall_at_k"] == 1


def test_search_benchmark_report_carries_warm_and_cold_groups(
    seeded: tuple[Session, OpportunityModel],
) -> None:
    session, target = seeded
    restarts: list[int] = []
    cold_runs: list[str] = []

    report = evaluate(
        session,
        _freeze(session, {("backend", str(target.id))}),
        warm_repetitions=10,
        cold_restarts=5,
        restart=lambda: restarts.append(len(cold_runs)),
        restart_method="fake restart",
        run_cold=cold_runs.append,
    )

    queries = [entry["query"] for entry in _QUERIES]
    groups = report["latency_groups"]
    assert restarts == [index * len(queries) for index in range(5)]
    assert cold_runs == queries * 5  # each restart is followed by every query once
    for row in report["per_query"]:
        assert len(row["warm_latency_ms"]) == 10
        assert len(row["cold_latency_ms"]) == 5
    assert groups["warm"]["all_queries"]["status"] == "measured"
    assert groups["cold"]["all_queries"]["status"] == "measured"
    assert groups["cold"]["restarts"] == 5
    assert report["latency"]["cold"]["count"] == 5 * len(queries)
    assert "server_version" in groups["environment"]


def test_search_benchmark_report_pairs_a_content_delta_on_a_fixed_cohort(
    seeded: tuple[Session, OpportunityModel],
) -> None:
    session, target = seeded
    relevant = {("kubernetes", str(target.id))}  # a human label, fixed before B
    report_a = evaluate(session, _freeze(session, relevant), parser_version="v-before")
    target.description = "Runs production Kubernetes clusters."  # the enrichment
    session.commit()
    report_b = evaluate(session, _freeze(session, relevant), parser_version="v-after")

    paired = paired_report(report_a, report_b)

    assert paired["comparison"] == "comparable"
    assert paired["payload_changed"] is True
    assert paired["delta_attributed_to"] == "content"
    assert paired["parser_versions"] == {"a": "v-before", "b": "v-after"}
    assert paired["hashes"]["a"]["corpus_hash"] != paired["hashes"]["b"]["corpus_hash"]
    row = next(row for row in paired["per_query"] if row["query"] == "kubernetes")
    assert row["at_10"]["recall_at_k"] == {"a": 0.0, "b": 1.0, "delta": 1.0}
