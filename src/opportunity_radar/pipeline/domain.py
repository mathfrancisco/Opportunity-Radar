"""Application pipeline: stages, legal transitions and the rules around them.

Pure module. It knows nothing about SQLAlchemy or HTTP, so the transition table can be
read and tested as the statement of policy it is.

An opportunity and an application stay separate concepts: the opportunity is what the
market published, the application is what the candidate did about it. Closing one never
closes the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

MAX_NOTE_LENGTH = 2000
MAX_NEXT_ACTION_LENGTH = 500


class ApplicationStage(StrEnum):
    """Section 59 of docs/29-roadmap-mvp.md."""

    INTERESTED = "INTERESTED"
    APPLIED = "APPLIED"
    SCREENING = "SCREENING"
    INTERVIEW = "INTERVIEW"
    TECHNICAL = "TECHNICAL"
    FINAL = "FINAL"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


class ApplicationStatus(StrEnum):
    """Derived from the stage, never set by hand."""

    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


#: Reaching one of these ends the application. They have no outgoing transition, so a
#: mistake is corrected by starting a new application, not by reopening history.
TERMINAL_STAGES: frozenset[ApplicationStage] = frozenset(
    {ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN, ApplicationStage.CLOSED}
)

_EXITS: frozenset[ApplicationStage] = frozenset(
    {ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN, ApplicationStage.CLOSED}
)

# Interviews and technical rounds can repeat in either order in practice, so the table
# allows both directions between them rather than forcing a single funnel.
ALLOWED_TRANSITIONS: Mapping[ApplicationStage, frozenset[ApplicationStage]] = (
    MappingProxyType(
        {
            ApplicationStage.INTERESTED: frozenset({ApplicationStage.APPLIED}) | _EXITS,
            ApplicationStage.APPLIED: frozenset(
                {
                    ApplicationStage.SCREENING,
                    ApplicationStage.INTERVIEW,
                    ApplicationStage.TECHNICAL,
                }
            )
            | _EXITS,
            ApplicationStage.SCREENING: frozenset(
                {ApplicationStage.INTERVIEW, ApplicationStage.TECHNICAL}
            )
            | _EXITS,
            ApplicationStage.INTERVIEW: frozenset(
                {
                    ApplicationStage.TECHNICAL,
                    ApplicationStage.FINAL,
                    ApplicationStage.OFFER,
                }
            )
            | _EXITS,
            ApplicationStage.TECHNICAL: frozenset(
                {
                    ApplicationStage.INTERVIEW,
                    ApplicationStage.FINAL,
                    ApplicationStage.OFFER,
                }
            )
            | _EXITS,
            ApplicationStage.FINAL: frozenset({ApplicationStage.OFFER}) | _EXITS,
            ApplicationStage.OFFER: frozenset(_EXITS),
            ApplicationStage.REJECTED: frozenset(),
            ApplicationStage.WITHDRAWN: frozenset(),
            ApplicationStage.CLOSED: frozenset(),
        }
    )
)

#: Where an application may start. Everything else has to be reached by a transition, so
#: the history always explains how the current stage was arrived at.
START_STAGES: frozenset[ApplicationStage] = frozenset(
    {ApplicationStage.INTERESTED, ApplicationStage.APPLIED}
)


class PipelineError(Exception):
    """Base for everything this context refuses to do."""


class InvalidStageTransitionError(PipelineError):
    def __init__(self, source: ApplicationStage, target: ApplicationStage) -> None:
        super().__init__(f"cannot move an application from {source} to {target}")
        self.source = source
        self.target = target


class InvalidStartStageError(PipelineError):
    def __init__(self, stage: ApplicationStage) -> None:
        super().__init__(f"an application cannot start at {stage}")
        self.stage = stage


class DuplicateActiveApplicationError(PipelineError):
    """One active application per opportunity and profile version."""


class ApplicationNotFoundError(PipelineError):
    pass


class ApplicationVersionConflictError(PipelineError):
    pass


def is_terminal(stage: ApplicationStage) -> bool:
    return stage in TERMINAL_STAGES


def status_for(stage: ApplicationStage) -> ApplicationStatus:
    return ApplicationStatus.CLOSED if is_terminal(stage) else ApplicationStatus.ACTIVE


def can_transition(source: ApplicationStage, target: ApplicationStage) -> bool:
    return target in ALLOWED_TRANSITIONS[source]


def validate_transition(source: ApplicationStage, target: ApplicationStage) -> None:
    """Raise unless the move is in the table. A no-op move is also refused: recording the
    same stage twice would add history without adding information."""
    if not can_transition(source, target):
        raise InvalidStageTransitionError(source, target)


def validate_start(stage: ApplicationStage) -> None:
    if stage not in START_STAGES:
        raise InvalidStartStageError(stage)


@dataclass(frozen=True, slots=True)
class NextAction:
    """What the candidate owes this application, and when."""

    description: str | None = None
    due_at: datetime | None = None

    def is_due(self, reference: datetime, *, within_days: int = 0) -> bool:
        if self.due_at is None:
            return False
        if within_days == 0:
            return self.due_at <= reference
        return (self.due_at - reference).days <= within_days


def normalized_text(value: str | None, limit: int) -> str | None:
    """Empty and blank collapse to absence: a note nobody wrote is not an empty note."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:limit]


__all__ = [
    "ALLOWED_TRANSITIONS",
    "MAX_NEXT_ACTION_LENGTH",
    "MAX_NOTE_LENGTH",
    "START_STAGES",
    "TERMINAL_STAGES",
    "ApplicationNotFoundError",
    "ApplicationStage",
    "ApplicationStatus",
    "ApplicationVersionConflictError",
    "DuplicateActiveApplicationError",
    "InvalidStageTransitionError",
    "InvalidStartStageError",
    "NextAction",
    "PipelineError",
    "can_transition",
    "is_terminal",
    "normalized_text",
    "status_for",
    "validate_start",
    "validate_transition",
]
