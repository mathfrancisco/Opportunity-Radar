"""R55-C5 follow-up: a null AI answer is remembered per (opportunity, version, field, prompt)."""

from __future__ import annotations

import os
from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import RoleFamily, WorkMode
from opportunity_radar.opportunities.suggestions import (
    SuggestionUnansweredModel,
    candidates_needing_suggestion,
    suggest_fields,
)
from opportunity_radar.platform.database import create_database_engine
from tests.backend.opportunities.test_suggestions import (
    _FAST_MODEL,
    _PROMPT,
    _SUGGESTION_OWNER,
    FakeProvider,
    _classification_response,
    _cleanup,
    _ensure_suggestion_profile,
    _opportunity,
    _rank,
    _router,
    _run,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_NULL_SENIORITY = {"seniority": {"value": None, "evidence": None}}


def _markers(session: Session, opportunity_id):
    session.expire_all()
    return sorted(
        (row.opportunity_version, row.field, row.prompt_version)
        for row in session.scalars(
            select(SuggestionUnansweredModel).where(
                SuggestionUnansweredModel.opportunity_id == opportunity_id
            )
        )
    )


def test_a_null_answer_is_not_asked_again_for_the_same_version_and_prompt() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(
            role_family=RoleFamily.DATA.value, work_mode=WorkMode.REMOTE.value
        )
        session.add(opportunity)
        session.commit()
        try:
            # One scripted answer only: a second provider call raises IndexError.
            provider = FakeProvider({_FAST_MODEL: [_classification_response(_NULL_SENIORITY)]})
            router = _router(provider)

            first = _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))
            assert first.called is True and first.created == ()
            assert _markers(session, opportunity.id) == [(1, "seniority", _PROMPT.version)]

            second = _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))
            assert second.called is False
            assert len(provider.requests) == 1
        finally:
            _cleanup(session, [opportunity.id])


def test_a_new_opportunity_version_or_prompt_version_asks_again() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(
            role_family=RoleFamily.DATA.value, work_mode=WorkMode.REMOTE.value
        )
        session.add(opportunity)
        session.commit()
        try:
            provider = FakeProvider(
                {_FAST_MODEL: [_classification_response(_NULL_SENIORITY) for _ in range(3)]}
            )
            router = _router(provider)
            _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))

            other_prompt = replace(_PROMPT, version="job_classification/v9")
            _run(suggest_fields(session, router, opportunity, prompt=other_prompt))
            assert len(provider.requests) == 2

            opportunity.version += 1
            session.commit()
            _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))
            assert len(provider.requests) == 3
            assert _markers(session, opportunity.id) == [
                (1, "seniority", "job_classification/v1"),
                (1, "seniority", "job_classification/v9"),
                (2, "seniority", "job_classification/v1"),
            ]
        finally:
            _cleanup(session, [opportunity.id])


def test_an_answered_field_leaves_a_suggestion_and_no_marker() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(
            title="Senior Backend Engineer",
            role_family=RoleFamily.DATA.value,
            work_mode=WorkMode.REMOTE.value,
        )
        session.add(opportunity)
        session.commit()
        try:
            provider = FakeProvider(
                {
                    _FAST_MODEL: [
                        _classification_response(
                            {"seniority": {"value": "senior", "evidence": "Senior Backend"}}
                        )
                    ]
                }
            )
            outcome = _run(suggest_fields(session, _router(provider), opportunity, prompt=_PROMPT))

            assert [item.field for item in outcome.created] == ["seniority"]
            assert _markers(session, opportunity.id) == []
        finally:
            _cleanup(session, [opportunity.id])


def test_the_queue_skips_a_marked_field_only_for_the_same_key() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        opportunity = _opportunity(
            role_family=RoleFamily.DATA.value, work_mode=WorkMode.REMOTE.value
        )
        session.add(opportunity)
        edited = _opportunity(
            role_family=RoleFamily.DATA.value, work_mode=WorkMode.REMOTE.value, version=2
        )
        session.add(edited)
        session.flush()
        _rank(session, profile_id, [opportunity, edited])
        for item, marked_version in ((opportunity, 1), (edited, 1)):
            session.add(
                SuggestionUnansweredModel(
                    opportunity_id=item.id,
                    opportunity_version=marked_version,
                    field="seniority",
                    prompt_version=_PROMPT.version,
                )
            )
        session.flush()
        try:

            def queued(item, prompt_version: str | None) -> bool:
                found = candidates_needing_suggestion(
                    session,
                    limit=100_000,
                    owner_sub=_SUGGESTION_OWNER,
                    prompt_version=prompt_version,
                )
                return item.id in {candidate.id for candidate in found}

            assert queued(opportunity, _PROMPT.version) is False  # same key: not asked again
            assert queued(opportunity, "job_classification/v9") is True  # other prompt asks anew
            # The marker is for version 1; the posting is now at version 2: asked anew.
            assert queued(edited, _PROMPT.version) is True
        finally:
            session.rollback()
