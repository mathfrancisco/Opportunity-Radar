"""`scripts/resolve_review_queue.py`: which parked rows count as distinct postings."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "resolve_review_queue",
    Path(__file__).parents[2] / "scripts" / "resolve_review_queue.py",
)
assert _SPEC is not None and _SPEC.loader is not None
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


def _row(**fields: Any) -> dict[str, Any]:
    return {
        "external_id": "job-1",
        "normalized_location": "sao paulo",
        "work_mode": "HYBRID",
        **fields,
    }


def _candidate(**fields: Any) -> dict[str, Any]:
    return {
        "external_ids": ["job-2"],
        "normalized_location": "recife",
        "work_mode": "HYBRID",
        **fields,
    }


def test_same_source_other_external_id_and_other_location_is_a_distinct_posting() -> None:
    assert script.is_distinct_posting(_row(), [_candidate()])


def test_same_location_and_other_work_mode_is_a_distinct_posting() -> None:
    candidate = _candidate(normalized_location="sao paulo", work_mode="REMOTE")

    assert script.is_distinct_posting(_row(), [candidate])


@pytest.mark.parametrize(
    "candidate",
    [
        _candidate(external_ids=None),  # the candidate is not in this source
        _candidate(external_ids=["job-1"]),  # same external id: not another posting
        _candidate(normalized_location="sao paulo"),  # same place and same mode
        _candidate(normalized_location=None),  # unknown location is not a difference
        _candidate(normalized_location="sao paulo", work_mode="UNKNOWN"),
        None,  # the candidate opportunity no longer exists
    ],
)
def test_anything_else_stays_in_the_queue(candidate: dict[str, Any] | None) -> None:
    assert not script.is_distinct_posting(_row(), [candidate])


def test_every_candidate_has_to_fit() -> None:
    same_place = _candidate(normalized_location="sao paulo")

    assert not script.is_distinct_posting(_row(), [_candidate(), same_place])
    assert not script.is_distinct_posting(_row(), [])


def test_a_row_is_grouped_under_its_first_reason_that_parks_it() -> None:
    reasons = [
        {"code": "SENIORITY_CLASSIFICATION"},
        {"code": "EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED"},
    ]

    assert script.review_reason(reasons) == "EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED"
    assert script.review_reason([{"code": "SENIORITY_CLASSIFICATION"}]) == "NO_REVIEW_REASON"


def test_sample_takes_at_most_the_size_of_each_reason_and_is_repeatable() -> None:
    rows = [
        {
            "id": index,
            "reason": "A" if index < 8 else "B",
            "source_type": "lever",
            "opportunity_id": index,
            "canonical_title": "t",
            "company_name": "c",
            "normalized_location": None,
            "work_mode": "UNKNOWN",
            "external_id": str(index),
            "candidates": [],
            "distinct_posting": False,
        }
        for index in range(10)
    ]

    first = script.sample(rows, 5, seed=1)

    assert [entry["reason"] for entry in first] == ["A"] * 5 + ["B"] * 2
    assert first == script.sample(rows, 5, seed=1)
