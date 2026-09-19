"""The transition table is policy, so it is tested as policy rather than as plumbing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from opportunity_radar.pipeline.domain import (
    ALLOWED_TRANSITIONS,
    START_STAGES,
    TERMINAL_STAGES,
    ApplicationStage,
    ApplicationStatus,
    InvalidStageTransitionError,
    InvalidStartStageError,
    NextAction,
    can_transition,
    is_terminal,
    normalized_text,
    status_for,
    validate_start,
    validate_transition,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def test_every_stage_has_an_entry_in_the_table() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(ApplicationStage)


def test_terminal_stages_have_no_way_out() -> None:
    for stage in TERMINAL_STAGES:
        assert ALLOWED_TRANSITIONS[stage] == frozenset()
        assert is_terminal(stage) is True
        assert status_for(stage) is ApplicationStatus.CLOSED


def test_active_stages_can_always_be_abandoned() -> None:
    """Any live application can be rejected, withdrawn or closed from where it is."""
    for stage in ApplicationStage:
        if stage in TERMINAL_STAGES:
            continue
        assert status_for(stage) is ApplicationStatus.ACTIVE
        for exit_stage in TERMINAL_STAGES:
            assert can_transition(stage, exit_stage) is True


def test_a_stage_never_transitions_to_itself() -> None:
    for stage, targets in ALLOWED_TRANSITIONS.items():
        assert stage not in targets


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (ApplicationStage.INTERESTED, ApplicationStage.APPLIED),
        (ApplicationStage.APPLIED, ApplicationStage.SCREENING),
        (ApplicationStage.SCREENING, ApplicationStage.INTERVIEW),
        (ApplicationStage.INTERVIEW, ApplicationStage.TECHNICAL),
        (ApplicationStage.TECHNICAL, ApplicationStage.INTERVIEW),
        (ApplicationStage.TECHNICAL, ApplicationStage.FINAL),
        (ApplicationStage.FINAL, ApplicationStage.OFFER),
        (ApplicationStage.OFFER, ApplicationStage.CLOSED),
    ],
)
def test_expected_moves_are_allowed(
    source: ApplicationStage, target: ApplicationStage
) -> None:
    validate_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (ApplicationStage.INTERESTED, ApplicationStage.OFFER),
        (ApplicationStage.APPLIED, ApplicationStage.FINAL),
        (ApplicationStage.SCREENING, ApplicationStage.OFFER),
        (ApplicationStage.OFFER, ApplicationStage.INTERVIEW),
        (ApplicationStage.REJECTED, ApplicationStage.APPLIED),
        (ApplicationStage.CLOSED, ApplicationStage.INTERESTED),
    ],
)
def test_skipping_or_reopening_is_refused(
    source: ApplicationStage, target: ApplicationStage
) -> None:
    with pytest.raises(InvalidStageTransitionError):
        validate_transition(source, target)


def test_an_application_only_starts_where_the_candidate_can_honestly_be() -> None:
    assert START_STAGES == {ApplicationStage.INTERESTED, ApplicationStage.APPLIED}
    validate_start(ApplicationStage.INTERESTED)
    validate_start(ApplicationStage.APPLIED)
    with pytest.raises(InvalidStartStageError):
        validate_start(ApplicationStage.OFFER)


def test_next_action_without_a_date_is_never_due() -> None:
    assert NextAction(description="Enviar follow-up").is_due(NOW) is False


def test_next_action_is_due_when_the_date_passed_or_falls_in_the_window() -> None:
    overdue = NextAction(description="Cobrar retorno", due_at=NOW - timedelta(days=1))
    soon = NextAction(description="Preparar entrevista", due_at=NOW + timedelta(days=3))

    assert overdue.is_due(NOW) is True
    assert soon.is_due(NOW) is False
    assert soon.is_due(NOW, within_days=7) is True


def test_blank_text_collapses_to_absence() -> None:
    assert normalized_text("   ", 100) is None
    assert normalized_text(None, 100) is None
    assert normalized_text("  nota  ", 100) == "nota"
    assert normalized_text("x" * 200, 100) == "x" * 100
