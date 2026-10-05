"""Cards F20-61 and F48-16: default search shows only a posting whose reference date
(`published_at ?? source_updated_at ?? first_seen_at`) is in the last 30 days (14 days is
the "Novas" lens), except a time-boxed entry program
(estágio/trainee/early-careers/residência) or one with a
still-open application-window deadline (`valid_through`).

`recency_decision` is pure and takes `now` explicitly — every test below freezes it, so
both sides of the window boundary are exact, never a flaky `datetime.now()` race.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from opportunity_radar.opportunities.domain import (
    DEFAULT_RECENCY_WINDOW_DAYS,
    NEW_RECENCY_WINDOW_DAYS,
    ContractType,
    NormalizationInput,
    RecencyBasis,
    build_candidate,
    infer_recency_exempt_program,
    recency_basis_of,
    recency_decision,
    recency_reference,
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


# --- Acceptance criterion 1: both sides of the window boundary ------------------------
# Default window is 30 days (F48-16, spec 48 decision 3); 14 days is the "Novas" lens and
# keeps the original F20-61 request one parameter away.


def _decide(*, days_old: int, window_days: int | None = None, **changes: object):
    kwargs: dict[str, object] = {
        "published_at": NOW - timedelta(days=days_old),
        "first_seen_at": None,
        "valid_through": None,
        "recency_exempt_program": False,
        "now": NOW,
    }
    kwargs.update(changes)
    if window_days is not None:
        kwargs["window_days"] = window_days
    return recency_decision(**kwargs)  # type: ignore[arg-type]


def test_default_window_is_30_days() -> None:
    assert DEFAULT_RECENCY_WINDOW_DAYS == 30
    assert NEW_RECENCY_WINDOW_DAYS == 14


def test_opportunity_at_29_days_is_visible_by_default() -> None:
    decision = _decide(days_old=29)
    assert decision.visible is True
    assert decision.date_is_estimated is False


def test_opportunity_at_31_days_is_not_visible_by_default() -> None:
    assert _decide(days_old=31).visible is False


def test_opportunity_at_exactly_30_days_is_still_visible() -> None:
    """The boundary itself is inclusive (`>=`), so a posting exactly at the window edge
    is not dropped by an off-by-one."""
    assert _decide(days_old=30).visible is True


def test_novas_lens_window_of_14_days_keeps_the_f20_61_boundary() -> None:
    assert _decide(days_old=13, window_days=NEW_RECENCY_WINDOW_DAYS).visible is True
    assert _decide(days_old=14, window_days=NEW_RECENCY_WINDOW_DAYS).visible is True
    assert _decide(days_old=15, window_days=NEW_RECENCY_WINDOW_DAYS).visible is False


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
        first_seen_at=NOW - timedelta(days=45),
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
        published_at=NOW - timedelta(days=45),
        first_seen_at=None,
        valid_through=NOW + timedelta(days=5),
        recency_exempt_program=False,
        now=NOW,
    )
    assert decision.visible is True


def test_past_valid_through_grants_no_exception() -> None:
    decision = recency_decision(
        published_at=NOW - timedelta(days=45),
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


# --- F48-16: explicit reference date and basis ---------------------------------------


def test_reference_prefers_published_then_updated_then_first_seen() -> None:
    published, updated, seen = (NOW - timedelta(days=d) for d in (40, 5, 1))
    assert recency_reference(
        published_at=published, source_updated_at=updated, first_seen_at=seen
    ) == (published, RecencyBasis.PUBLISHED)
    assert recency_reference(
        published_at=None, source_updated_at=updated, first_seen_at=seen
    ) == (updated, RecencyBasis.UPDATED)
    assert recency_reference(
        published_at=None, source_updated_at=None, first_seen_at=seen
    ) == (seen, RecencyBasis.FIRST_SEEN)


def test_recency_basis_of_ignores_first_seen() -> None:
    assert recency_basis_of(published_at=NOW, source_updated_at=None) is RecencyBasis.PUBLISHED
    assert recency_basis_of(published_at=None, source_updated_at=NOW) is RecencyBasis.UPDATED
    assert recency_basis_of(published_at=None, source_updated_at=None) is RecencyBasis.FIRST_SEEN


def test_updated_basis_is_estimated_and_sets_the_effective_date() -> None:
    decision = _decide(
        days_old=0,
        published_at=None,
        source_updated_at=NOW - timedelta(days=3),
        first_seen_at=NOW - timedelta(days=90),
    )
    assert decision.visible is True
    assert decision.basis is RecencyBasis.UPDATED
    assert decision.date_is_estimated is True
    assert decision.effective_date == NOW - timedelta(days=3)


def test_2026_10_13_cliff_does_not_hit_a_job_with_recent_source_updated_at() -> None:
    """Greenhouse gives no `published_at`. Seen on 2026-09-29, the job used to fall out of
    the default filter 14 days later; with `source_updated_at` as the reference it stays
    visible on 2026-10-13 (and later) while the source keeps updating it."""
    first_seen = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    cliff = datetime(2026, 10, 13, 12, 1, tzinfo=timezone.utc)
    recently_updated = cliff - timedelta(days=2)

    stale_basis = recency_decision(
        published_at=None,
        first_seen_at=first_seen,
        valid_through=None,
        recency_exempt_program=False,
        now=cliff,
        window_days=NEW_RECENCY_WINDOW_DAYS,
    )
    assert stale_basis.visible is False  # the old 14-day, first_seen-only behaviour

    with_update = recency_decision(
        published_at=None,
        source_updated_at=recently_updated,
        first_seen_at=first_seen,
        valid_through=None,
        recency_exempt_program=False,
        now=cliff,
    )
    assert with_update.visible is True
    assert with_update.basis is RecencyBasis.UPDATED


def test_program_deadline_exception_survives_the_new_window() -> None:
    assert _decide(days_old=200, recency_exempt_program=True).visible is True
    assert _decide(days_old=200, valid_through=NOW + timedelta(days=1)).visible is True
