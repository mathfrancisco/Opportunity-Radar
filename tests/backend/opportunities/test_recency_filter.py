"""Card F20-61: default search shows only a posting from the last 14 days, except a
time-boxed entry program (estágio/trainee/early-careers/residência) or one with a
still-open application-window deadline (`valid_through`).

`recency_decision` is pure and takes `now` explicitly — every test below freezes it, so
both sides of the 14-day boundary are exact, never a flaky `datetime.now()` race.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from opportunity_radar.opportunities.domain import (
    ContractType,
    NormalizationInput,
    build_candidate,
    infer_recency_exempt_program,
    recency_decision,
)

NOW = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)


def _input(**changes: object) -> NormalizationInput:
    values: dict[str, object] = {
        "raw_item_id": uuid4(),
        "source_definition_id": uuid4(),
        "source_type": "manual",
        "external_id": "external-1",
        "title": "Senior C++ Engineer",
        "company_name": "Acme",
        "location_text": "Remote",
        "metadata": {},
    }
    values.update(changes)
    return NormalizationInput(**values)  # type: ignore[arg-type]


# --- Acceptance criterion 1: both sides of the 14-day boundary -----------------------


def test_opportunity_at_13_days_is_visible_by_default() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=13),
        first_seen_at=None,
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is True
    assert decision.date_is_estimated is False


def test_opportunity_at_15_days_is_not_visible_by_default() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=15),
        first_seen_at=None,
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is False


def test_opportunity_at_exactly_14_days_is_still_visible() -> None:
    """The boundary itself is inclusive (`>=`), so a 14-day-old posting is not
    dropped by an off-by-one on the exact edge."""
    decision = recency_decision(
        published_at=NOW - timedelta(days=14),
        first_seen_at=None,
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is True


# --- Acceptance criterion 2: internship/trainee/early-careers exception never expires


def test_internship_at_60_days_still_visible() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=60),
        first_seen_at=None,
        valid_through=None,
        recency_exempt_program=True,
        now=NOW,
    )
    assert decision.visible is True


def test_non_program_at_60_days_not_visible() -> None:
    """Same age, but without the program signal — the control case proving the
    exception (not just old-age tolerance) is what kept the internship visible."""
    decision = recency_decision(
        published_at=NOW - timedelta(days=60),
        first_seen_at=None,
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is False


@pytest.mark.parametrize(
    ("title", "contract_type"),
    [
        ("Software Engineering Intern", ContractType.INTERNSHIP),
        ("Vaga de Estagiário de Dados", ContractType.INTERNSHIP),
        ("Programa Trainee 2027", ContractType.UNKNOWN),
        ("Residency Program — Backend", ContractType.UNKNOWN),
        ("Programa de Residência em Engenharia", ContractType.UNKNOWN),
        ("Early Career Software Engineer", ContractType.UNKNOWN),
        ("Início de Carreira — Analista", ContractType.UNKNOWN),
    ],
)
def test_infer_recency_exempt_program_covers_every_named_program_keyword(
    title: str, contract_type: ContractType
) -> None:
    assert infer_recency_exempt_program(title, {}, contract_type=contract_type) is True


def test_infer_recency_exempt_program_false_for_an_ordinary_role() -> None:
    assert not infer_recency_exempt_program(
        "Senior Backend Engineer", {}, contract_type=ContractType.FULL_TIME
    )


# --- Acceptance criterion 3: missing published_at falls back to first_seen_at, marked


def test_missing_published_at_falls_back_to_first_seen_at_marked_estimated() -> None:
    decision = recency_decision(
        published_at=None,
        first_seen_at=NOW - timedelta(days=5),
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is True
    assert decision.effective_date == NOW - timedelta(days=5)
    assert decision.date_is_estimated is True


def test_missing_published_at_fallback_still_respects_the_window() -> None:
    decision = recency_decision(
        published_at=None,
        first_seen_at=NOW - timedelta(days=20),
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is False
    assert decision.date_is_estimated is True


def test_real_published_at_is_never_marked_estimated() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=1),
        first_seen_at=NOW - timedelta(days=90),  # radar saw it long before the real date
        valid_through=None,
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.date_is_estimated is False
    assert decision.effective_date == NOW - timedelta(days=1)


# --- Acceptance criterion 4: an open application deadline is its own exception -------


def test_future_valid_through_visible_even_when_old_and_not_a_program() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=30),
        first_seen_at=None,
        valid_through=NOW + timedelta(days=5),
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is True


def test_past_valid_through_grants_no_exception() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=30),
        first_seen_at=None,
        valid_through=NOW - timedelta(days=1),
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is False


# --- Threading valid_through and the program signal through normalization -----------


def test_normalize_candidate_threads_valid_through_and_program_signal() -> None:
    candidate = build_candidate(
        _input(
            title="Programa Trainee 2027",
            valid_through=NOW + timedelta(days=10),
        )
    )
    assert candidate.valid_through == NOW + timedelta(days=10)
    assert candidate.recency_exempt_program is True


def test_normalize_candidate_defaults_valid_through_to_none_and_program_to_false() -> None:
    candidate = build_candidate(_input(title="Senior Backend Engineer"))
    assert candidate.valid_through is None
    assert candidate.recency_exempt_program is False
