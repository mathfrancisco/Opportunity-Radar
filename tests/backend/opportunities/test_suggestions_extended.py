"""Card R55-C5: the model suggests country and work authorization, and decides nothing.

A fake provider answers every call; nothing here reaches Groq. The load-bearing test is
`test_an_ai_suggestion_cannot_change_the_deterministic_verdict`: the same snapshot rebuilt
from the database after the suggestion yields the same result, and an acceptance (a
person's act) still leaves the stored assessment untouched until a re-evaluation.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from opportunity_radar.matching.domain import (
    OpportunitySnapshot,
    OpportunityStatus,
    ProfileSnapshot,
    default_rule_set,
    evaluate_match,
)
from opportunity_radar.matching.service import _allowed_countries
from opportunity_radar.opportunities.domain import RoleFamily, Seniority, WorkMode
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.suggestions import (
    SUGGESTION_ORIGIN,
    OpportunitySuggestionModel,
    SuggestibleField,
    SuggestionStatus,
    accept_suggestion,
    candidates_needing_suggestion,
    load_classification_prompt,
    mentions_work_authorization,
    suggest_fields,
    unknown_fields,
)
from opportunity_radar.platform.database import create_database_engine
from tests.backend.opportunities.test_suggestions import (
    _FAST_MODEL,
    FakeProvider,
    _classification_response,
    _cleanup,
    _ensure_suggestion_profile,
    _opportunity,
    _rank,
    _router,
)

_DESCRIPTION = (
    "Backend role. This position is open to candidates based in the United Kingdom only. "
    "We cannot offer visa sponsorship for this role."
)


def _resolved(**overrides: object) -> OpportunityModel:
    base: dict[str, object] = {
        "role_family": RoleFamily.SOFTWARE_ENGINEERING.value,
        "seniority": Seniority.SENIOR.value,
        "work_mode": WorkMode.REMOTE.value,
        "description": _DESCRIPTION,
    }
    base.update(overrides)
    return _opportunity(**base)  # type: ignore[arg-type]


def _answer(**fields: dict[str, object]) -> object:
    empty = {"value": None, "evidence": None}
    keys = ("role_family", "seniority", "work_mode", "country", "work_authorization")
    return _classification_response({key: fields.get(key, empty) for key in keys})


def test_the_extended_fields_are_opt_in_and_only_for_what_the_rules_missed() -> None:
    opportunity = _resolved()

    assert unknown_fields(opportunity) == []
    assert unknown_fields(opportunity, extended=True) == [
        SuggestibleField.COUNTRY,
        SuggestibleField.WORK_AUTHORIZATION,
    ]
    resolved = _resolved(description="Backend role, no mention of rights.")
    resolved.allowed_countries = ["GB"]
    assert unknown_fields(resolved, extended=True) == []


def test_a_posting_silent_on_authorization_is_not_asked_about_it() -> None:
    assert mentions_work_authorization("We offer Visa support")
    assert not mentions_work_authorization("Build APIs in Python")
    assert not mentions_work_authorization(None)


def test_the_v2_prompt_asks_for_all_five_fields() -> None:
    prompt = load_classification_prompt("v2")

    assert prompt.version == "job_classification/v2"
    assert set(prompt.output_schema["required"]) == {
        "role_family",
        "seniority",
        "work_mode",
        "country",
        "work_authorization",
    }


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)
class TestWithDatabase:
    def test_the_model_suggestion_is_stored_with_origin_ai_and_pending(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            opportunity = _resolved()
            session.add(opportunity)
            session.commit()
            try:
                provider = FakeProvider(
                    {
                        _FAST_MODEL: [
                            _answer(
                                country={"value": "gb", "evidence": "United Kingdom only"},
                                work_authorization={
                                    "value": "SPONSORSHIP_NOT_AVAILABLE",
                                    "evidence": "cannot offer visa sponsorship",
                                },
                            )
                        ]
                    }
                )
                outcome = asyncio.run(
                    suggest_fields(
                        session,
                        _router(provider),
                        opportunity,
                        prompt=load_classification_prompt("v2"),
                        extended=True,
                    )
                )

                rows = session.scalars(
                    select(OpportunitySuggestionModel).where(
                        OpportunitySuggestionModel.opportunity_id == opportunity.id
                    )
                ).all()
                assert {(row.field, row.value) for row in rows} == {
                    ("country", "GB"),
                    ("work_authorization", "SPONSORSHIP_NOT_AVAILABLE"),
                }
                assert {row.origin for row in rows} == {SUGGESTION_ORIGIN} == {"ai"}
                assert {row.status for row in rows} == {SuggestionStatus.PENDING.value}
                assert not outcome.discarded_fields
                sent = json.loads(provider.requests[0].user)
                assert sent["pending_fields"] == ["country", "work_authorization"]
            finally:
                _cleanup(session, [opportunity.id])

    def test_a_bad_country_or_a_quote_not_in_the_text_is_discarded(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            opportunity = _resolved()
            session.add(opportunity)
            session.commit()
            try:
                provider = FakeProvider(
                    {
                        _FAST_MODEL: [
                            _answer(
                                country={"value": "ANY", "evidence": "United Kingdom only"},
                                work_authorization={
                                    "value": "SPONSORSHIP_AVAILABLE",
                                    "evidence": "we love sponsoring",
                                },
                            )
                        ]
                    }
                )
                outcome = asyncio.run(
                    suggest_fields(
                        session,
                        _router(provider),
                        opportunity,
                        prompt=load_classification_prompt("v2"),
                        extended=True,
                    )
                )

                assert set(outcome.discarded_fields) == {"country", "work_authorization"}
                assert outcome.created == ()
            finally:
                _cleanup(session, [opportunity.id])

    def test_without_the_flag_the_extended_fields_are_never_asked(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            opportunity = _resolved()
            session.add(opportunity)
            session.commit()
            try:
                provider = FakeProvider({_FAST_MODEL: []})
                outcome = asyncio.run(suggest_fields(session, _router(provider), opportunity))

                assert outcome.state == "preflight" and provider.requests == []
            finally:
                _cleanup(session, [opportunity.id])

    def test_an_ai_suggestion_cannot_change_the_deterministic_verdict(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            profile_id = _ensure_suggestion_profile(session)
            opportunity = _resolved()
            session.add(opportunity)
            session.flush()
            _rank(session, profile_id, [opportunity])
            session.commit()

            def deterministic() -> tuple[str, str, str]:
                session.expire_all()
                row = session.get(OpportunityModel, opportunity.id)
                assert row is not None
                snapshot = OpportunitySnapshot(
                    opportunity_id=row.id,
                    content_version=row.version,
                    status=OpportunityStatus(row.lifecycle_status),
                    allowed_countries=_allowed_countries(row.allowed_countries),
                )
                result = evaluate_match(
                    snapshot,
                    ProfileSnapshot(profile_version_id=profile_id, countries=("BR",)),
                    default_rule_set(),
                )
                stored = (
                    session.execute(
                        text(
                            "SELECT verdict FROM matching.current_assessment "
                            "WHERE opportunity_id = :id"
                        ),
                        {"id": row.id},
                    )
                    .scalars()
                    .all()
                )
                return result.verdict.value, result.eligibility.status.value, ",".join(stored)

            try:
                before = deterministic()
                provider = FakeProvider(
                    {
                        _FAST_MODEL: [
                            _answer(
                                country={"value": "GB", "evidence": "United Kingdom only"},
                            )
                        ]
                    }
                )
                asyncio.run(
                    suggest_fields(
                        session,
                        _router(provider),
                        opportunity,
                        prompt=load_classification_prompt("v2"),
                        extended=True,
                    )
                )

                # Stored apart: the canonical row and the stored assessment are untouched.
                assert deterministic() == before
                session.refresh(opportunity)
                assert not opportunity.allowed_countries and opportunity.version == 1

                # Only a person accepting it writes the country; even then the stored
                # assessment keeps its verdict until a re-evaluation produces a new row.
                suggestion = session.scalars(
                    select(OpportunitySuggestionModel).where(
                        OpportunitySuggestionModel.opportunity_id == opportunity.id,
                        OpportunitySuggestionModel.field == "country",
                    )
                ).one()
                accept_suggestion(session, suggestion.id, decided_by="reviewer@test")
                session.refresh(opportunity)
                assert opportunity.allowed_countries == ["GB"]
                _, _, stored_after = deterministic()
                assert stored_after == before[2]
            finally:
                # Assessments are immutable (a trigger refuses their deletion), so the
                # posting stays in the disposable test database; only the suggestions go.
                session.execute(
                    delete(OpportunitySuggestionModel).where(
                        OpportunitySuggestionModel.opportunity_id == opportunity.id
                    )
                )
                session.commit()

    def test_accepting_work_authorization_records_the_review_and_changes_nothing_else(
        self,
    ) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            opportunity = _resolved()
            session.add(opportunity)
            session.commit()
            suggestion = OpportunitySuggestionModel(
                opportunity_id=opportunity.id,
                opportunity_version=opportunity.version,
                field="work_authorization",
                value="SPONSORSHIP_NOT_AVAILABLE",
                evidence="cannot offer visa sponsorship",
                model=_FAST_MODEL,
                prompt_version="job_classification/v2",
                status=SuggestionStatus.PENDING.value,
            )
            session.add(suggestion)
            session.commit()
            try:
                accepted = accept_suggestion(session, suggestion.id, decided_by="reviewer@test")
                session.refresh(opportunity)

                assert accepted.status == SuggestionStatus.ACCEPTED.value
                assert accepted.decided_by == "reviewer@test"
                assert opportunity.version == 1 and not opportunity.allowed_countries
            finally:
                _cleanup(session, [opportunity.id])

    def test_a_country_suggestion_never_overwrites_a_country_already_set(self) -> None:
        from opportunity_radar.opportunities.service import OpportunityVersionConflictError

        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            opportunity = _resolved()
            opportunity.allowed_countries = ["BR"]
            opportunity.allowed_countries_version = "regions-v1"
            empty = _resolved()
            session.add_all([opportunity, empty])
            session.commit()
            suggestions = [
                OpportunitySuggestionModel(
                    opportunity_id=row.id,
                    opportunity_version=row.version,
                    field="country",
                    value="GB",
                    evidence="United Kingdom only",
                    model=_FAST_MODEL,
                    prompt_version="job_classification/v2",
                    status=SuggestionStatus.PENDING.value,
                )
                for row in (opportunity, empty)
            ]
            session.add_all(suggestions)
            session.commit()
            try:
                with pytest.raises(OpportunityVersionConflictError):
                    accept_suggestion(session, suggestions[0].id, decided_by="reviewer@test")
                session.rollback()
                session.refresh(opportunity)
                assert opportunity.allowed_countries == ["BR"]

                accept_suggestion(session, suggestions[1].id, decided_by="reviewer@test")
                session.refresh(empty)
                assert empty.allowed_countries == ["GB"]
            finally:
                _cleanup(session, [opportunity.id, empty.id])

    def test_the_database_only_accepts_origin_ai(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            opportunity = _resolved()
            session.add(opportunity)
            session.commit()
            try:
                session.add(
                    OpportunitySuggestionModel(
                        opportunity_id=opportunity.id,
                        opportunity_version=opportunity.version,
                        field="country",
                        value="GB",
                        evidence="United Kingdom only",
                        model=_FAST_MODEL,
                        prompt_version="job_classification/v2",
                        origin="human",
                    )
                )
                with pytest.raises(IntegrityError):
                    session.commit()
                session.rollback()
            finally:
                _cleanup(session, [opportunity.id])

    def test_the_queue_includes_extended_candidates_only_when_asked(self) -> None:
        engine = create_database_engine(os.environ["DATABASE_URL"])
        with Session(engine) as session:
            profile_id = _ensure_suggestion_profile(session)
            opportunity = _resolved()
            session.add(opportunity)
            session.flush()
            _rank(session, profile_id, [opportunity])
            try:
                owner = "suggestions-test-owner"
                base = candidates_needing_suggestion(session, limit=500, owner_sub=owner)
                extended = candidates_needing_suggestion(
                    session, limit=500, owner_sub=owner, extended=True
                )

                assert opportunity.id not in {item.id for item in base}
                assert opportunity.id in {item.id for item in extended}
            finally:
                session.rollback()


@pytest.mark.parametrize(("raw", "expected"), [("gb", "GB"), ("UK", "GB"), (" br ", "BR")])
def test_a_country_answer_is_an_iso_code(raw: str, expected: str) -> None:
    from opportunity_radar.opportunities.suggestions import _valid_value

    assert _valid_value(SuggestibleField.COUNTRY, raw) == expected


@pytest.mark.parametrize("raw", ["EU", "ZZ", "XX", "ANY", "USA", "B"])
def test_a_non_iso_country_answer_is_rejected(raw: str) -> None:
    from opportunity_radar.opportunities.suggestions import _valid_value

    with pytest.raises(ValueError):
        _valid_value(SuggestibleField.COUNTRY, raw)


def test_a_confirmed_country_survives_rules_that_find_none() -> None:
    from types import SimpleNamespace

    from opportunity_radar.opportunities.service import _keeps_confirmed_countries

    confirmed = SimpleNamespace(
        allowed_countries=["GB"], allowed_countries_version="ai-confirmed:job_classification/v2"
    )
    by_rules = SimpleNamespace(allowed_countries=["GB"], allowed_countries_version="rules-v1")
    none_found = SimpleNamespace(allowed_countries=())
    found = SimpleNamespace(allowed_countries=("BR",))

    assert _keeps_confirmed_countries(confirmed, none_found)  # type: ignore[arg-type]
    assert not _keeps_confirmed_countries(confirmed, found)  # type: ignore[arg-type]
    assert not _keeps_confirmed_countries(by_rules, none_found)  # type: ignore[arg-type]
