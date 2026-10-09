"""Card F20-23: `job_classification` suggestions for a field left `UNKNOWN`.

Every provider call goes through a fake `LLMProvider` defined below: no test here
reaches Groq. Persistence assertions run against the real database, gated like the rest
of `tests/backend/opportunities/` by `RUN_DATABASE_INTEGRATION`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar import worker
from opportunity_radar.opportunities.domain import RoleFamily, Seniority, WorkMode
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.service import OpportunityVersionConflictError
from opportunity_radar.opportunities.suggestions import (
    ClassificationPrompt,
    OpportunitySuggestionModel,
    SuggestibleField,
    SuggestionAlreadyDecidedError,
    SuggestionDeferModel,
    SuggestionNotFoundError,
    SuggestionStatus,
    _suggestion_content_hash,
    accept_suggestion,
    candidates_needing_suggestion,
    load_classification_prompt,
    reject_suggestion,
    suggest_fields,
    unknown_fields,
)
from opportunity_radar.platform.ai.breaker import CircuitBreaker
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.metrics import ai_period_comparison
from opportunity_radar.platform.ai.providers.base import (
    LLMRequest,
    LLMResponse,
    RateLimit,
    Usage,
)
from opportunity_radar.platform.ai.providers.groq import GroqProvider
from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import AITask, default_routes
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService
from tests.backend.dashboard.test_queries import _assessment
from tests.backend.matching.test_evaluation_queue import _ensure_active_profile

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)

_FAST_MODEL = "openai/gpt-oss-20b"
_SUGGESTION_OWNER = "suggestions-test-owner"

_PROMPT = ClassificationPrompt(
    version="job_classification/v1",
    system="classify",
    user_template=(
        '{"pending_fields": {{ pending_fields }}, "title": {{ title }}, '
        '"description": {{ description }}}'
    ),
    schema_version="job_classification-v1",
    output_schema={"type": "object"},
)


def _ensure_suggestion_profile(session: Session) -> UUID:
    """Use a stable synthetic owner for the worker's profile-scoped candidate query."""
    _ensure_active_profile(session)
    service = ProfileService(session, _SUGGESTION_OWNER)
    try:
        return service.get_active().id
    except ProfileNotFoundError:
        pass
    snapshot = ProfileService(session).get_active().snapshot
    return service.create_active_version(snapshot, 0).id


def response(model: str, content: str, latency_ms: int = 10) -> LLMResponse:
    return LLMResponse(
        model=model,
        content=content,
        usage=Usage(prompt_tokens=100, completion_tokens=20, prompt_ms=None, completion_ms=None),
        rate_limit=RateLimit(None, None, None, None, None, None),
        latency_ms=latency_ms,
        finish_reason="stop",
    )


class FakeProvider:
    """Returns scripted outcomes per model, in order. Never reaches Groq."""

    name = "fake"

    def __init__(self, script: dict) -> None:
        self._script = {model: list(outcomes) for model, outcomes in script.items()}
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        outcome = self._script[request.model].pop(0)
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


def _settings(**overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg,arg-type]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", **overrides
    )


def _router(provider: FakeProvider) -> AIRouter:
    settings = _settings()
    return AIRouter(provider, default_routes(settings), max_retries=0)


def _run(coro):  # small helper, avoids repeating asyncio.run everywhere
    return asyncio.run(coro)


def _opportunity(
    *,
    title: str = "Backend Engineer",
    description: str = "We build APIs in Python.",
    role_family: str = "UNKNOWN",
    seniority: str = "UNKNOWN",
    work_mode: str = "UNKNOWN",
    version: int = 1,
) -> OpportunityModel:
    marker = uuid4().hex[:12]
    return OpportunityModel(
        id=uuid4(),
        fingerprint=uuid4().hex + uuid4().hex,
        fingerprint_version="v1",
        canonical_title=title,
        normalized_title=f"{title.lower()}-{marker}",
        description=description,
        work_mode=work_mode,
        seniority=seniority,
        contract_type="UNKNOWN",
        role_family=role_family,
        lifecycle_status="ACTIVE",
        created_at=NOW,
        version=version,
    )


def _rank(
    session: Session, profile_id: UUID, opportunities: list[OpportunityModel],
    verdict: str = "HIGH_PRIORITY",
) -> None:
    """A current assessment under the active profile: what puts a posting in the
    automatic queue, hence what a background suggestion requires. Flushes only."""
    for item in opportunities:
        _assessment(
            session, item, profile_id, verdict=verdict, score="90.0000",
            assessed_at=datetime.now(UTC),
        )
    session.flush()


def _cleanup(session: Session, opportunity_ids: list) -> None:
    session.execute(
        delete(OpportunitySuggestionModel).where(
            OpportunitySuggestionModel.opportunity_id.in_(opportunity_ids)
        )
    )
    session.execute(delete(OpportunityModel).where(OpportunityModel.id.in_(opportunity_ids)))
    session.commit()


def _classification_response(payload: dict) -> object:
    return response(_FAST_MODEL, content=json.dumps(payload))


# --- pure logic, no DB -------------------------------------------------------------


def test_unknown_fields_lists_only_unknown_columns() -> None:
    opportunity = _opportunity(
        role_family=RoleFamily.SOFTWARE_ENGINEERING.value,
        seniority="UNKNOWN",
        work_mode="UNKNOWN",
    )
    assert unknown_fields(opportunity) == [
        SuggestibleField.SENIORITY,
        SuggestibleField.WORK_MODE,
    ]


def test_unknown_fields_empty_when_everything_resolved() -> None:
    opportunity = _opportunity(
        role_family=RoleFamily.DATA.value,
        seniority=Seniority.SENIOR.value,
        work_mode=WorkMode.REMOTE.value,
    )
    assert unknown_fields(opportunity) == []


def test_candidates_scope_current_assessments_to_the_configured_owner() -> None:
    """A worker owner never borrows another owner's active profile or queue."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        first_profile = CareerProfileModel(owner_sub="suggestion-owner-one")
        second_profile = CareerProfileModel(owner_sub="suggestion-owner-two")
        session.add_all((first_profile, second_profile))
        session.flush()
        first_version = ProfileVersionModel(
            career_profile_id=first_profile.id, number=1, status="ACTIVE"
        )
        second_version = ProfileVersionModel(
            career_profile_id=second_profile.id, number=1, status="ACTIVE"
        )
        first = _opportunity(title="Owner one")
        second = _opportunity(title="Owner two")
        session.add_all((first_version, second_version, first, second))
        session.flush()
        _rank(session, first_version.id, [first])
        _rank(session, second_version.id, [second])

        selected_one = {
            item.id
            for item in candidates_needing_suggestion(
                session, limit=10, owner_sub="suggestion-owner-one"
            )
        }
        selected_two = {
            item.id
            for item in candidates_needing_suggestion(
                session, limit=10, owner_sub="suggestion-owner-two"
            )
        }

        assert selected_one == {first.id}
        assert selected_two == {second.id}

        first_version.status = "ARCHIVED"
        session.flush()
        assert candidates_needing_suggestion(
            session, limit=10, owner_sub="suggestion-owner-one"
        ) == []
        assert {
            item.id
            for item in candidates_needing_suggestion(
                session, limit=10, owner_sub="suggestion-owner-two"
            )
        } == {second.id}
        session.rollback()


def test_defer_content_hash_changes_with_content_or_pending_fields() -> None:
    role = [SuggestibleField.ROLE_FAMILY]
    base = _suggestion_content_hash("Backend", "Python APIs", role)
    assert _suggestion_content_hash("Backend", "Python APIs", role) == base
    assert _suggestion_content_hash("Backend", "Python APIs updated", role) != base
    assert _suggestion_content_hash(
        "Backend", "Python APIs", [SuggestibleField.SENIORITY]
    ) != base


def test_load_classification_prompt_reads_the_real_artifacts() -> None:
    from opportunity_radar.opportunities.suggestions import load_classification_prompt

    prompt = load_classification_prompt()
    assert prompt.version == "job_classification/v1"
    assert prompt.schema_version == "job_classification-v1"
    assert "evidence" in prompt.system
    assert "{{ title }}" in prompt.user_template
    assert prompt.output_schema["required"] == ["role_family", "seniority", "work_mode"]


# --- gatilho + evidence check, against the real database ---------------------------


def test_suggest_fields_never_persists_a_field_already_resolved_by_rule() -> None:
    """A call that answers a resolved field anyway must not create a suggestion for it
    (acceptance criterion: "Nenhuma chamada para campo resolvido por regra")."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(
            title="Backend Engineer",
            description="Remote role building Python APIs.",
            role_family=RoleFamily.SOFTWARE_ENGINEERING.value,  # already resolved
            seniority="UNKNOWN",
            work_mode="UNKNOWN",
        )
        session.add(opportunity)
        session.commit()
        try:
            provider = FakeProvider(
                {
                    _FAST_MODEL: [
                        _classification_response(
                            {
                                "role_family": {
                                    "value": "data",
                                    "evidence": "Backend Engineer",
                                },
                                "seniority": {"value": "senior", "evidence": "Remote role"},
                                "work_mode": {"value": "remote", "evidence": "Remote role"},
                            }
                        )
                    ]
                }
            )
            outcome = _run(
                suggest_fields(session, _router(provider), opportunity, prompt=_PROMPT)
            )

            fields_created = {suggestion.field for suggestion in outcome.created}
            assert fields_created == {"seniority", "work_mode"}
            assert "role_family" not in fields_created

            persisted = session.scalars(
                select(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id == opportunity.id
                )
            ).all()
            assert {row.field for row in persisted} == {"seniority", "work_mode"}
        finally:
            _cleanup(session, [opportunity.id])


def test_suggest_fields_discards_suggestion_without_literal_evidence() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(
            title="Backend Engineer",
            description="Remote role building Python APIs.",
            role_family="UNKNOWN",
            seniority="UNKNOWN",
            work_mode="UNKNOWN",
        )
        session.add(opportunity)
        session.commit()
        try:
            provider = FakeProvider(
                {
                    _FAST_MODEL: [
                        _classification_response(
                            {
                                # "startup vibes" never appears in title or description.
                                "role_family": {
                                    "value": "software_engineering",
                                    "evidence": "startup vibes",
                                },
                                "seniority": {"value": "senior", "evidence": None},
                                "work_mode": {"value": "remote", "evidence": "Remote role"},
                            }
                        )
                    ]
                }
            )
            outcome = _run(
                suggest_fields(session, _router(provider), opportunity, prompt=_PROMPT)
            )

            fields_created = {suggestion.field for suggestion in outcome.created}
            assert fields_created == {"work_mode"}
            assert "role_family" in outcome.discarded_fields

            role_family_row = session.scalar(
                select(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id == opportunity.id,
                    OpportunitySuggestionModel.field == "role_family",
                )
            )
            assert role_family_row is None
        finally:
            _cleanup(session, [opportunity.id])


def test_suggest_fields_is_idempotent_per_opportunity_version() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(
            title="Backend Engineer",
            description="Remote role.",
            role_family="UNKNOWN",
            seniority=Seniority.SENIOR.value,
            work_mode="UNKNOWN",
        )
        session.add(opportunity)
        session.commit()
        try:
            # Only one scripted response: a second model call on the same version would
            # raise IndexError from the FakeProvider's script, failing this test.
            provider = FakeProvider(
                {
                    _FAST_MODEL: [
                        _classification_response(
                            {
                                "role_family": {
                                    "value": "software_engineering",
                                    "evidence": "Backend Engineer",
                                },
                                "seniority": {"value": None, "evidence": None},
                                "work_mode": {"value": "remote", "evidence": "Remote role"},
                            }
                        )
                    ]
                }
            )
            router = _router(provider)
            first = _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))
            assert len(first.created) == 2

            second = _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))
            assert second.created == ()
            assert second.called is False

            rows = session.scalars(
                select(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id == opportunity.id
                )
            ).all()
            assert len(rows) == 2
        finally:
            _cleanup(session, [opportunity.id])


def test_suggest_fields_returns_empty_outcome_when_provider_fails() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(role_family="UNKNOWN")
        session.add(opportunity)
        session.commit()
        try:
            provider = FakeProvider(
                {
                    _FAST_MODEL: [
                        ProviderError(ErrorKind.CONFIGURATION, "missing key"),
                    ]
                }
            )
            outcome = _run(
                suggest_fields(session, _router(provider), opportunity, prompt=_PROMPT)
            )
            assert outcome.created == ()
        finally:
            _cleanup(session, [opportunity.id])


# --- accept / reject -----------------------------------------------------------------


def test_accept_suggestion_writes_the_canonical_value_and_bumps_version() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(seniority="UNKNOWN", version=1)
        session.add(opportunity)
        session.commit()
        suggestion = OpportunitySuggestionModel(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            field="seniority",
            value=Seniority.SENIOR.value,
            evidence="senior backend role",
            model=_FAST_MODEL,
            prompt_version=_PROMPT.version,
            status=SuggestionStatus.PENDING.value,
        )
        session.add(suggestion)
        session.commit()
        try:
            accepted = accept_suggestion(session, suggestion.id, decided_by="operator@test")
            session.refresh(opportunity)

            assert accepted.status == SuggestionStatus.ACCEPTED.value
            assert accepted.decided_by == "operator@test"
            assert opportunity.seniority == Seniority.SENIOR.value
            assert opportunity.version == 2

            # Idempotent: accepting again does not bump the version a second time.
            accept_suggestion(session, suggestion.id, decided_by="operator@test")
            session.refresh(opportunity)
            assert opportunity.version == 2
        finally:
            _cleanup(session, [opportunity.id])


def test_accept_suggestion_records_llm_confirmed_evidence_for_role_family() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(role_family="UNKNOWN", version=1)
        session.add(opportunity)
        session.commit()
        suggestion = OpportunitySuggestionModel(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            field="role_family",
            value=RoleFamily.DATA.value,
            evidence="data pipelines",
            model=_FAST_MODEL,
            prompt_version=_PROMPT.version,
            status=SuggestionStatus.PENDING.value,
        )
        session.add(suggestion)
        session.commit()
        try:
            accept_suggestion(session, suggestion.id, decided_by="operator@test")
            session.refresh(opportunity)

            assert opportunity.role_family == RoleFamily.DATA.value
            assert opportunity.role_family_evidence is not None
            assert opportunity.role_family_evidence["origin"] == "llm_confirmed"
            assert opportunity.role_family_evidence["evidence"] == "data pipelines"
        finally:
            _cleanup(session, [opportunity.id])


def test_accept_suggestion_rejects_a_stale_opportunity_version() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(seniority="UNKNOWN", version=1)
        session.add(opportunity)
        session.commit()
        suggestion = OpportunitySuggestionModel(
            opportunity_id=opportunity.id,
            opportunity_version=1,
            field="seniority",
            value=Seniority.SENIOR.value,
            evidence="senior role",
            model=_FAST_MODEL,
            prompt_version=_PROMPT.version,
            status=SuggestionStatus.PENDING.value,
        )
        session.add(suggestion)
        opportunity.version = 2  # the posting changed after the suggestion was made
        session.commit()
        try:
            with pytest.raises(OpportunityVersionConflictError):
                accept_suggestion(session, suggestion.id, decided_by="operator@test")
        finally:
            _cleanup(session, [opportunity.id])


def test_reject_suggestion_only_changes_its_own_status() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        opportunity = _opportunity(work_mode="UNKNOWN", version=1)
        session.add(opportunity)
        session.commit()
        suggestion = OpportunitySuggestionModel(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            field="work_mode",
            value=WorkMode.HYBRID.value,
            evidence="hybrid setup",
            model=_FAST_MODEL,
            prompt_version=_PROMPT.version,
            status=SuggestionStatus.PENDING.value,
        )
        session.add(suggestion)
        session.commit()
        try:
            rejected = reject_suggestion(session, suggestion.id, decided_by="operator@test")
            session.refresh(opportunity)

            assert rejected.status == SuggestionStatus.REJECTED.value
            assert opportunity.work_mode == "UNKNOWN"
            assert opportunity.version == 1

            # Idempotent.
            reject_suggestion(session, suggestion.id, decided_by="operator@test")
        finally:
            _cleanup(session, [opportunity.id])


def test_cannot_accept_a_rejected_suggestion_or_reject_an_accepted_one() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        rejected_opportunity = _opportunity(work_mode="UNKNOWN", version=1)
        accepted_opportunity = _opportunity(work_mode="UNKNOWN", version=1)
        session.add_all([rejected_opportunity, accepted_opportunity])
        session.commit()
        rejected = OpportunitySuggestionModel(
            opportunity_id=rejected_opportunity.id,
            opportunity_version=rejected_opportunity.version,
            field="work_mode",
            value=WorkMode.ONSITE.value,
            evidence="on-site office",
            model=_FAST_MODEL,
            prompt_version=_PROMPT.version,
            status=SuggestionStatus.REJECTED.value,
        )
        accepted = OpportunitySuggestionModel(
            opportunity_id=accepted_opportunity.id,
            opportunity_version=accepted_opportunity.version,
            field="work_mode",
            value=WorkMode.ONSITE.value,
            evidence="on-site office",
            model=_FAST_MODEL,
            prompt_version=_PROMPT.version,
            status=SuggestionStatus.ACCEPTED.value,
        )
        session.add_all([rejected, accepted])
        session.commit()
        try:
            with pytest.raises(SuggestionAlreadyDecidedError):
                accept_suggestion(session, rejected.id, decided_by="operator@test")
            with pytest.raises(SuggestionAlreadyDecidedError):
                reject_suggestion(session, accepted.id, decided_by="operator@test")
        finally:
            _cleanup(session, [rejected_opportunity.id, accepted_opportunity.id])


def test_accept_suggestion_not_found() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        with pytest.raises(SuggestionNotFoundError):
            accept_suggestion(session, uuid4(), decided_by="operator@test")


# --- candidate selection for the worker job -----------------------------------------


def test_candidates_needing_suggestion_skips_opportunities_already_suggested() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        needs_suggestion = _opportunity(
            role_family=RoleFamily.DATA.value,
            seniority="UNKNOWN",
            work_mode=WorkMode.REMOTE.value,
        )
        already_suggested = _opportunity(
            role_family=RoleFamily.DATA.value,
            seniority="UNKNOWN",
            work_mode=WorkMode.REMOTE.value,
        )
        fully_resolved = _opportunity(
            role_family=RoleFamily.DATA.value,
            seniority=Seniority.SENIOR.value,
            work_mode=WorkMode.REMOTE.value,
        )
        session.add_all([needs_suggestion, already_suggested, fully_resolved])
        session.flush()
        _rank(session, profile_id, [needs_suggestion, already_suggested, fully_resolved])
        session.add(
            OpportunitySuggestionModel(
                opportunity_id=already_suggested.id,
                opportunity_version=already_suggested.version,
                field="seniority",
                value=Seniority.SENIOR.value,
                evidence="senior",
                model=_FAST_MODEL,
                prompt_version=_PROMPT.version,
                status=SuggestionStatus.PENDING.value,
            )
        )
        session.flush()
        try:
            # The query is catalogue-wide and ordered by creation; rows other tests left
            # in the shared database would push this test's rows out of a small window,
            # so the limit must cover every candidate that could exist.
            candidates = candidates_needing_suggestion(
                session, limit=100_000, owner_sub=_SUGGESTION_OWNER
            )
            candidate_ids = {opportunity.id for opportunity in candidates}
            assert needs_suggestion.id in candidate_ids
            assert already_suggested.id not in candidate_ids
            assert fully_resolved.id not in candidate_ids
        finally:
            # Assessments are immutable, so nothing here is committed: rollback is the cleanup.
            session.rollback()


def test_suggestion_queue_filters_before_limit_and_pages_stably() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        # Older than any row another test may have left in the shared database.
        created_at = datetime(2000, 1, 1, tzinfo=UTC)
        known = {
            "role_family": RoleFamily.SOFTWARE_ENGINEERING.value,
            "work_mode": WorkMode.REMOTE.value,
        }
        resolved = [_opportunity(seniority="UNKNOWN", **known) for _ in range(100)]
        eligible = [_opportunity(seniority="UNKNOWN", **known) for _ in range(3)]
        for item in resolved + eligible:
            item.created_at = created_at
        session.add_all(resolved + eligible)
        session.flush()
        _rank(session, profile_id, resolved + eligible)
        session.add_all(
            OpportunitySuggestionModel(
                opportunity_id=item.id,
                opportunity_version=item.version,
                field=SuggestibleField.SENIORITY.value,
                value=Seniority.SENIOR.value,
                evidence="senior",
                model=_FAST_MODEL,
                prompt_version=_PROMPT.version,
                status=SuggestionStatus.PENDING.value,
            )
            for item in resolved
        )
        session.flush()
        try:
            first_page = candidates_needing_suggestion(
                session, limit=2, owner_sub=_SUGGESTION_OWNER
            )
            assert [item.id for item in first_page] == [
                item.id for item in sorted(eligible, key=lambda row: row.id)[:2]
            ]
            last = first_page[-1]
            second_page = candidates_needing_suggestion(
                session, limit=2, after=(last.created_at, last.id),
                owner_sub=_SUGGESTION_OWNER,
            )
            # The shared database may hold newer candidates from other tests; they come
            # after this test's rows and never include a resolved one.
            assert second_page[0].id == sorted(eligible, key=lambda row: row.id)[2].id
            assert {item.id for item in second_page}.isdisjoint(
                {item.id for item in resolved} | {item.id for item in first_page}
            )
        finally:
            session.rollback()


# --- F51-09: no reservation without a call record ------------------------------------

_TH_MODELS = ("tokenharbor:deepseek-v4.1-flash:free", "tokenharbor:mimo-v2.6-flash:free")
_CHAIN = (_FAST_MODEL, "qwen/qwen3.8-27b", *_TH_MODELS)


class _StepProvider:
    """Scripted per model like `FakeProvider`, but honours `on_transport_start` the way
    the Groq adapter does: it fires only once the request is really handed to transport."""

    name = "fake"

    def __init__(self, script: dict) -> None:
        self._script = {model: list(items) for model, items in script.items()}

    async def complete(self, request: LLMRequest) -> LLMResponse:
        items = self._script[request.model]
        step = items.pop(0) if len(items) > 1 else items[0]
        transport = step.get("transport", True)
        if transport and request.on_transport_start is not None:
            await request.on_transport_start()
        kind = step["kind"]
        if kind == "ok":
            return response(request.model, step.get("content", "{}"))
        if kind == "cancel":
            cancellation = asyncio.CancelledError()
            cancellation.transport_started = transport  # type: ignore[attr-defined]
            raise cancellation
        usage = step.get("usage", False)
        raise ProviderError(
            kind, "boom", model=request.model, transport_started=transport,
            prompt_tokens=100 if usage else None, completion_tokens=20 if usage else None,
        )


def _everywhere(step: dict) -> dict:
    return {model: [step] for model in _CHAIN}


_QUOTA_AFTER = {"kind": ErrorKind.QUOTA, "usage": True}
_OK = {"kind": "ok"}
_RESERVATION_CASES = {
    "success-first": _everywhere(_OK),
    "fallthrough-mixed-chain": {
        _CHAIN[0]: [_QUOTA_AFTER],
        _CHAIN[1]: [{"kind": ErrorKind.TRANSIENT, "transport": False}],
        _CHAIN[2]: [{"kind": ErrorKind.INVALID_OUTPUT}],
        _CHAIN[3]: [_OK],
    },
    "all-transient-after-transport": _everywhere({"kind": ErrorKind.TRANSIENT}),
    "all-quota-before-transport": _everywhere({"kind": ErrorKind.QUOTA, "transport": False}),
    "all-transient-before-transport": _everywhere(
        {"kind": ErrorKind.TRANSIENT, "transport": False}
    ),
    "parse-error": _everywhere({"kind": "ok", "content": "not json"}),
    "request-error": _everywhere({"kind": ErrorKind.REQUEST, "usage": True}),
    "configuration-before-transport": _everywhere(
        {"kind": ErrorKind.CONFIGURATION, "transport": False}
    ),
    "cancel-after-transport": _everywhere({"kind": "cancel", "transport": True}),
    "cancel-before-transport": _everywhere({"kind": "cancel", "transport": False}),
}


@pytest.mark.parametrize("label", list(_RESERVATION_CASES))
def test_suggest_fields_leaves_no_reservation_without_a_call_record(label: str) -> None:
    from sqlalchemy import text

    from opportunity_radar.platform.ai.quota import QuotaGuard, QuotaLimits

    async def no_sleep(_: float) -> None:
        return None

    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_quota_usage, platform.ai_call_record"))
    guard = QuotaGuard(engine, QuotaLimits(10_000, 10_000_000, 10_000, 10_000_000))
    settings = Settings(  # type: ignore[call-arg,arg-type]
        _env_file=None, database_url="postgresql+psycopg://u@h/db", tokenharbor_api_key="k"
    )
    router = AIRouter(
        _StepProvider(_RESERVATION_CASES[label]), default_routes(settings),
        max_retries=1, sleeper=no_sleep, quota_guard=guard,
    )
    with Session(engine) as session:
        opportunity = _opportunity(role_family="UNKNOWN")
        session.add(opportunity)
        session.commit()
        try:
            try:
                _run(suggest_fields(session, router, opportunity, prompt=_PROMPT))
            except (ProviderError, asyncio.CancelledError):
                pass
            with engine.connect() as connection:
                reserved = {
                    row.model: row.requests
                    for row in connection.execute(text(
                        "SELECT model, requests FROM platform.ai_quota_usage "
                        "WHERE window_kind = 'day' AND requests > 0"
                    ))
                }
                recorded = {
                    row.model: row.calls
                    for row in connection.execute(text(
                        "SELECT model, count(*) AS calls FROM platform.ai_call_record "
                        "WHERE task = 'job_classification' AND transport_started "
                        "GROUP BY model"
                    ))
                }
            assert reserved == recorded
        finally:
            _cleanup(session, [opportunity.id])
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE platform.ai_call_record"))


# --- F51-12: suggestions only where they can matter, and only with quota -------------

_KNOWN = {"role_family": RoleFamily.SOFTWARE_ENGINEERING.value, "work_mode": WorkMode.REMOTE.value}


class _RecordingProvider:
    """Answers every request with an empty classification and remembers what was asked."""

    name = "fake"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return response(request.model, "{}")


def test_ai_runs_only_for_pending_suggestion_fields() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        pending = _opportunity(
            title="Senior Python engineer",
            description="Senior Python engineer, fully remote.",
            seniority="UNKNOWN",
            **_KNOWN,
        )
        resolved = _opportunity(seniority=Seniority.SENIOR.value, **_KNOWN)
        session.add_all([pending, resolved])
        session.commit()
        try:
            canonical_before = (
                pending.role_family, pending.work_mode, pending.seniority, pending.version
            )
            provider = FakeProvider({
                _FAST_MODEL: [_classification_response({
                    "seniority": {"value": "senior", "evidence": "Senior Python engineer"},
                })],
            })
            router = _router(provider)

            _run(suggest_fields(session, router, pending, prompt=_PROMPT))

            # One call, asking only about the field still UNKNOWN.
            assert len(provider.requests) == 1
            assert '"pending_fields": ["seniority"]' in provider.requests[0].user

            outcome = _run(suggest_fields(session, router, resolved, prompt=_PROMPT))

            # Every field of this one is decided by rule: no second call.
            assert outcome.called is False
            assert len(provider.requests) == 1
            session.refresh(pending)
            assert (
                pending.role_family, pending.work_mode, pending.seniority, pending.version
            ) == canonical_before
            stored = session.scalars(
                select(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id == pending.id
                )
            ).all()
            assert [(row.field, row.status) for row in stored] == [("seniority", "PENDING")]
        finally:
            _cleanup(session, [pending.id, resolved.id])


def test_suggestion_candidates_need_an_unknown_field_and_a_top_verdict() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        high = _opportunity(seniority="UNKNOWN", **_KNOWN)
        recommended = _opportunity(seniority="UNKNOWN", **_KNOWN)
        watchlist = _opportunity(seniority="UNKNOWN", **_KNOWN)
        resolved_top = _opportunity(seniority=Seniority.SENIOR.value, **_KNOWN)
        unassessed = _opportunity(seniority="UNKNOWN", **_KNOWN)
        session.add_all([high, recommended, watchlist, resolved_top, unassessed])
        session.flush()
        _rank(session, profile_id, [high])
        _rank(session, profile_id, [recommended], verdict="RECOMMENDED")
        _rank(session, profile_id, [watchlist], verdict="WATCHLIST")
        _rank(session, profile_id, [resolved_top])
        try:
            ids = {
                item.id
                for item in candidates_needing_suggestion(
                    session, limit=100_000, owner_sub=_SUGGESTION_OWNER
                )
            }

            assert {high.id, recommended.id} <= ids
            # Top verdict without an UNKNOWN field, an UNKNOWN field without a top verdict
            # and a posting the automatic queue never sees are all left alone.
            assert not {watchlist.id, resolved_top.id, unassessed.id} & ids
        finally:
            session.rollback()


def test_no_background_suggestion_without_an_active_profile() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        item = _opportunity(seniority="UNKNOWN", **_KNOWN)
        session.add(item)
        session.flush()
        _rank(session, profile_id, [item])
        try:
            assert item.id in {
                c.id
                for c in candidates_needing_suggestion(
                    session, limit=100_000, owner_sub=_SUGGESTION_OWNER
                )
            }

            session.execute(update(ProfileVersionModel).values(status="ARCHIVED"))
            session.flush()

            assert candidates_needing_suggestion(
                session, limit=100_000, owner_sub=_SUGGESTION_OWNER
            ) == []
        finally:
            session.rollback()


def test_the_suggestion_job_skips_postings_outside_the_automatic_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    marker = uuid4().hex[:10]
    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        queued = _opportunity(title=f"Queued {marker}", seniority="UNKNOWN", **_KNOWN)
        unassessed = _opportunity(title=f"Unassessed {marker}", seniority="UNKNOWN", **_KNOWN)
        watched = _opportunity(title=f"Watched {marker}", seniority="UNKNOWN", **_KNOWN)
        items = [queued, unassessed, watched]
        for item in items:
            # Older than anything another test left, so a small batch reaches them first.
            item.created_at = datetime(2000, 1, 1, tzinfo=UTC)
        session.add_all(items)
        session.flush()
        _rank(session, profile_id, [queued])
        _rank(session, profile_id, [watched], verdict="WATCHLIST")
        # Assessments are immutable: the job runs on this uncommitted session instead.
        monkeypatch.setattr(worker, "Session", lambda _engine: nullcontext(session))
        try:
            provider = _RecordingProvider()

            worker.suggest_fields_pending(
                engine, _router(provider), batch_size=50, owner_sub=_SUGGESTION_OWNER
            )

            asked = " ".join(request.user for request in provider.requests)
            assert f"Queued {marker}" in asked
            assert f"Unassessed {marker}" not in asked
            assert f"Watched {marker}" not in asked
        finally:
            session.rollback()
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE platform.ai_call_record"))


def _quota_router(
    engine: Engine, provider: _RecordingProvider, *, day_requests: int
) -> tuple[AIRouter, QuotaGuard, tuple[str, ...]]:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_quota_usage"))
    guard = QuotaGuard(engine, QuotaLimits(10_000, 10_000_000, day_requests, 10_000_000))
    router = AIRouter(provider, default_routes(_settings()), max_retries=0, quota_guard=guard)
    return router, guard, router.route(AITask.JOB_CLASSIFICATION).chain


def _classification_operations(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(connection.execute(text(
            "SELECT count(*) FROM platform.ai_operation_record WHERE task = 'job_classification'"
        )).scalar_one())


def _day_requests(guard: QuotaGuard, model: str) -> int:
    return next(
        row["requests"] for row in guard.snapshot()
        if row["model"] == model and row["window_kind"] == "day"
    )


def test_the_suggestion_job_does_nothing_without_day_quota(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    router, guard, chain = _quota_router(engine, provider, day_requests=5)
    for model in chain:
        for _ in range(5):
            assert guard.reserve(model, 10) is not None
    selections: list[int] = []

    def select_candidates(_session: Session, **_kwargs: object) -> list[OpportunityModel]:
        selections.append(1)
        return []

    monkeypatch.setattr(worker, "candidates_needing_suggestion", select_candidates)
    operations_before = _classification_operations(engine)

    worker.suggest_fields_pending(engine, router, owner_sub=_SUGGESTION_OWNER)

    # No candidate is even read, so no operation row is written per candidate.
    assert selections == []
    assert provider.requests == []
    assert _classification_operations(engine) == operations_before

    # With balance on a single model of the chain the job proceeds as before.
    for model in chain[1:]:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM platform.ai_quota_usage WHERE model = :m"),
                               {"m": model})

    worker.suggest_fields_pending(engine, router, owner_sub=_SUGGESTION_OWNER)

    assert selections == [1]


def test_background_suggestions_respect_interactive_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Card F51-12 AC04, suggestion side: at day requests minus the interactive reserve the
    job consumes nothing, and an interactive reservation (no ceiling) still goes through."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    router, guard, chain = _quota_router(engine, provider, day_requests=10)
    worker_ceiling = 10 - 3  # day requests minus an interactive reserve of 3
    for model in chain:
        for _ in range(worker_ceiling):
            assert guard.reserve(model, 10) is not None
    monkeypatch.setattr(
        worker, "candidates_needing_suggestion",
        lambda *_args, **_kwargs: pytest.fail("the job read candidates with no worker budget"),
    )

    worker.suggest_fields_pending(
        engine, router, worker_requests_ceiling=worker_ceiling,
        owner_sub=_SUGGESTION_OWNER,
    )

    assert provider.requests == []
    assert [_day_requests(guard, model) for model in chain] == [worker_ceiling] * len(chain)
    # The same day still has balance for the user's own call, which takes from the reserve.
    assert guard.has_day_balance(chain[0])
    assert guard.reserve(chain[0], 100) is not None
    assert _day_requests(guard, chain[0]) == worker_ceiling + 1


def test_global_quota_exhaustion_defers_a_suggestion_instead_of_failing_it() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    router, guard, chain = _quota_router(engine, provider, day_requests=5)
    for model in chain:
        for _ in range(5):
            assert guard.reserve(model, 10) is not None
    with Session(engine) as session:
        item = _opportunity(seniority="UNKNOWN", **_KNOWN)
        session.add(item)
        session.commit()
        try:
            outcome = _run(suggest_fields(
                session, router, item, prompt=_PROMPT, quota_ceiling_requests=5
            ))

            assert provider.requests == []
            assert (outcome.state, outcome.error_kind, outcome.called) == (
                "deferred", "quota", False
            )
            assert outcome.next_attempt_at is not None
            assert outcome.next_attempt_at > datetime.now(UTC)
            assert session.scalars(
                select(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id == item.id
                )
            ).all() == []
        finally:
            session.execute(text(
                "DELETE FROM platform.ai_suggestion_defer WHERE opportunity_id = :id"
            ), {"id": item.id})
            _cleanup(session, [item.id])


def test_a_failed_suggestion_does_not_hide_the_next_candidate(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        first = _opportunity(
            title="Broken answer", description="Broken answer for the first one.", **_KNOWN
        )
        second = _opportunity(
            title="Senior Python engineer", description="Senior Python engineer, remote.", **_KNOWN
        )
        session.add_all([first, second])
        session.commit()
        monkeypatch.setattr(
            worker, "candidates_needing_suggestion",
            lambda *_args, **_kwargs: [first, second],
        )
        provider = FakeProvider({_FAST_MODEL: [
            response(_FAST_MODEL, "not json"),
            _classification_response({
                "seniority": {"value": "senior", "evidence": "Senior Python engineer"},
            }),
        ]})
        try:
            with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
                worker.suggest_fields_pending(
                    engine, _router(provider), owner_sub=_SUGGESTION_OWNER
                )

            assert len(provider.requests) == 2
            summary = next(
                item for item in caplog.records if item.message == "suggest fields batch finished"
            )
            assert (summary.processed, summary.suggestions_created) == (2, 1)
            assert summary.failure_classes == {"parse_error": 1}
            stored = session.scalars(
                select(OpportunitySuggestionModel).where(
                    OpportunitySuggestionModel.opportunity_id.in_([first.id, second.id])
                )
            ).all()
            assert [(row.opportunity_id, row.field) for row in stored] == [
                (second.id, "seniority")
            ]
        finally:
            _cleanup(session, [first.id, second.id])
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE platform.ai_call_record"))


def test_global_quota_exhaustion_defers_rest_of_batch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Card F51-10 AC04: exactly one request, then none; the rest get no operation row."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    router, _guard, _chain = _quota_router(engine, provider, day_requests=1)
    with Session(engine) as session:
        items = [
            _opportunity(title=f"Engineer {n}", description=f"Engineer {n}, remote.", **_KNOWN)
            for n in range(4)
        ]
        session.add_all(items)
        session.commit()
        monkeypatch.setattr(
            worker, "candidates_needing_suggestion", lambda *_args, **_kwargs: items
        )
        operations_before = _classification_operations(engine)
        try:
            with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
                worker.suggest_fields_pending(
                    engine, router, worker_requests_ceiling=1,
                    owner_sub=_SUGGESTION_OWNER,
                )

            assert len(provider.requests) == 1
            # The first candidate used the only request; the second found no balance, was
            # deferred and ended the batch; the third and fourth were never started.
            assert _classification_operations(engine) - operations_before == 2
            summary = next(
                item for item in caplog.records if item.message == "suggest fields batch finished"
            )
            assert (summary.not_attempted, summary.stopped_by) == (2, "quota")
            assert summary.failure_classes == {"quota_defer": 1}
        finally:
            session.execute(text(
                "DELETE FROM platform.ai_suggestion_defer WHERE opportunity_id = ANY(:ids)"
            ), {"ids": [item.id for item in items]})
            _cleanup(session, [item.id for item in items])
            with engine.begin() as connection:
                connection.execute(text("TRUNCATE platform.ai_call_record"))


class _GatedProvider:
    """Holds its first call open until released, so a second caller can arrive meanwhile."""

    name = "fake"

    def __init__(self, answer: object) -> None:
        self.requests: list[LLMRequest] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self._answer = answer

    async def complete(self, request: LLMRequest) -> object:
        self.requests.append(request)
        self.entered.set()
        await self.release.wait()
        return self._answer


def test_suggestion_claim_prevents_duplicate_provider_call() -> None:
    """F51-10 AC06: two workers on the same posting make one provider call."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    other_engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session, Session(other_engine) as other_session:
        opportunity = _opportunity(
            description="Remote role building Python APIs.",
            role_family=RoleFamily.SOFTWARE_ENGINEERING.value,
            seniority=Seniority.MID.value,
        )
        session.add(opportunity)
        session.commit()
        same_posting = other_session.get(OpportunityModel, opportunity.id)
        assert same_posting is not None
        provider = _GatedProvider(
            _classification_response({"work_mode": {"value": "remote", "evidence": "Remote role"}})
        )
        router = AIRouter(provider, default_routes(_settings()), max_retries=0)  # type: ignore[arg-type]

        async def two_workers() -> tuple[object, object, int]:
            owner = asyncio.create_task(
                suggest_fields(session, router, opportunity, prompt=_PROMPT)
            )
            await provider.entered.wait()
            second = await suggest_fields(other_session, router, same_posting, prompt=_PROMPT)
            with engine.connect() as connection:
                active_claims = connection.scalar(
                    text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted")
                )
            provider.release.set()
            return await owner, second, active_claims

        try:
            first, second, active_claims = _run(two_workers())

            assert active_claims == 1
            assert (second.state, second.error_kind) == ("preflight", "claimed_elsewhere")
            assert not second.created
            assert [suggestion.field for suggestion in first.created] == ["work_mode"]
            assert len(provider.requests) == 1

            # Once the owner is done the claim is gone and nothing is left to ask.
            other_session.expire_all()
            later = _run(suggest_fields(other_session, router, same_posting, prompt=_PROMPT))
            assert not later.created and later.error_kind is None
            assert len(provider.requests) == 1
            with engine.connect() as connection:
                assert connection.scalar(
                    text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
                ) == 0
        finally:
            _cleanup(session, [opportunity.id])
    other_engine.dispose()


# --- F51-09 / F51-10 acceptance criteria: operations, attempts and defers -----------


class _SteppedClock:
    """A monotonic clock that advances 50 ms per reading, so a measured latency is known."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        self._now += 0.05
        return self._now


def _groq_router(
    handler, *, fallback_enabled: bool = False
) -> tuple[AIRouter, list[httpx.Request]]:
    """The real Groq adapter over a fake HTTP transport: whatever `handler` answers (or
    raises) is what the router sees, and `requests` is what reached the transport."""
    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    provider = GroqProvider(
        api_key="k",
        base_url="https://groq.test",
        clock=_SteppedClock(),
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(recording)),
    )
    router = AIRouter(
        provider, default_routes(_settings()), fallback_enabled=fallback_enabled, max_retries=0
    )
    return router, requests


def _groq_body(model: str, content: str, usage: dict | None = None) -> dict:
    body: dict = {
        "model": model,
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _classification_operation_ids(engine: Engine) -> set[UUID]:
    with engine.connect() as connection:
        return set(connection.execute(text(
            "SELECT id FROM platform.ai_operation_record WHERE task = 'job_classification'"
        )).scalars())


def _operations_after(engine: Engine, known: set[UUID]) -> list:
    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT id, state, error_kind FROM platform.ai_operation_record "
            "WHERE task = 'job_classification' ORDER BY started_at"
        )).all()
    return [row for row in rows if row.id not in known]


def _attempts_of(engine: Engine, operation_id: UUID) -> list:
    with engine.connect() as connection:
        return list(connection.execute(text(
            "SELECT operation_ordinal, model, success, error_kind, http_status, latency_ms, "
            "prompt_tokens, completion_tokens, transport_started, attempt_state "
            "FROM platform.ai_call_record WHERE operation_id = :id ORDER BY operation_ordinal"
        ), {"id": operation_id}).all())


def _forget_calls(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE platform.ai_call_record"))


def _drop_defers(session: Session, opportunity_ids: list[UUID]) -> None:
    session.rollback()
    session.execute(text(
        "DELETE FROM platform.ai_suggestion_defer WHERE opportunity_id = ANY(:ids)"
    ), {"ids": opportunity_ids})
    session.commit()


def test_a_connection_error_after_transport_start_is_one_failed_attempt_of_one_operation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """F51-09 AC01: the request left, then the connection broke. One `provider_error`
    operation, one failed attempt with `transport_started`, correlated by operation id."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    engine = create_database_engine(os.environ["DATABASE_URL"])
    router, requests = _groq_router(refuse)
    _forget_calls(engine)
    with Session(engine) as session:
        item = _opportunity(
            title="Backend Engineer", description="Remote role building Python APIs.", **_KNOWN
        )
        session.add(item)
        session.commit()
        monkeypatch.setattr(worker, "candidates_needing_suggestion", lambda *_a, **_k: [item])
        known = _classification_operation_ids(engine)
        try:
            with caplog.at_level(logging.INFO, logger="opportunity_radar.worker"):
                worker.suggest_fields_pending(
                    engine, router, owner_sub=_SUGGESTION_OWNER
                )

            assert len(requests) == 1
            [operation] = _operations_after(engine, known)
            assert (operation.state, operation.error_kind) == ("provider_error", "transient")
            [attempt] = _attempts_of(engine, operation.id)
            assert attempt.transport_started is True
            assert (attempt.success, attempt.error_kind, attempt.attempt_state) == (
                False, "transient", "completed"
            )
            assert attempt.operation_ordinal == 0 and attempt.http_status is None
            summary = next(
                record for record in caplog.records
                if record.message == "suggest fields batch finished"
            )
            # `failed` counts only unexpected exceptions; a provider error is a failure
            # class of its own, so the card's "failed=1" is not what the batch reports.
            assert (summary.processed, summary.failed) == (1, 0)
            assert summary.failure_classes == {"provider_error": 1}
        finally:
            _drop_defers(session, [item.id])
            _cleanup(session, [item.id])
            _forget_calls(engine)


def test_http_200_with_an_unparseable_body_and_no_usage_keeps_status_and_unknown_tokens() -> None:
    """F51-09 AC02: one `parse_error` operation; its attempt keeps status 200 and latency,
    and the tokens the provider never reported stay unknown (NULL), not zero."""

    def unparseable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_groq_body(_FAST_MODEL, "this is not json"))

    engine = create_database_engine(os.environ["DATABASE_URL"])
    router, requests = _groq_router(unparseable)
    _forget_calls(engine)
    since = datetime.now(UTC) - timedelta(minutes=1)
    with Session(engine) as session:
        item = _opportunity(role_family="UNKNOWN")
        session.add(item)
        session.commit()
        known = _classification_operation_ids(engine)
        try:
            outcome = _run(suggest_fields(session, router, item, prompt=_PROMPT))

            assert (outcome.state, outcome.called) == ("parse_error", True)
            assert len(requests) == 1
            [operation] = _operations_after(engine, known)
            assert (operation.state, operation.error_kind) == ("parse_error", "parse_error")
            [attempt] = _attempts_of(engine, operation.id)
            assert (attempt.http_status, attempt.latency_ms) == (200, 50)
            assert (attempt.prompt_tokens, attempt.completion_tokens) == (None, None)
            assert attempt.transport_started is True
            window = (since, datetime.now(UTC) + timedelta(minutes=1))
            totals = ai_period_comparison(
                engine, task="job_classification", baseline=(since, since), pilot=window
            )
            assert (totals.pilot.requests, totals.pilot.recorded_tokens) == (1, 0)
            assert totals.pilot.requests_without_tokens == 1  # unknown, reported as a gap
            assert "pilot.tokens" in totals.gaps
        finally:
            _drop_defers(session, [item.id])
            _cleanup(session, [item.id])
            _forget_calls(engine)


def test_an_open_breaker_is_decided_before_transport_and_records_no_attempt() -> None:
    """F51-09 AC03 (breaker): every model of the route is open, so the operation ends
    `preflight`: no transport call, no attempt row, no token recorded as zero."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    breaker = CircuitBreaker(failures=1, cooldown_seconds=3600)
    router = AIRouter(provider, default_routes(_settings()), max_retries=0, breaker=breaker)
    for model in router.route(AITask.JOB_CLASSIFICATION).chain:
        breaker.record_failure(model)
    _forget_calls(engine)
    with Session(engine) as session:
        item = _opportunity(role_family="UNKNOWN")
        session.add(item)
        session.commit()
        known = _classification_operation_ids(engine)
        try:
            outcome = _run(suggest_fields(session, router, item, prompt=_PROMPT))

            assert provider.requests == []
            # The router reports "no model available" as a quota error: an open breaker and
            # an exhausted balance are told apart only by the operation's `preflight` state.
            assert (outcome.state, outcome.called, outcome.error_kind) == (
                "preflight", False, "quota"
            )
            [operation] = _operations_after(engine, known)
            assert operation.state == "preflight"
            assert _attempts_of(engine, operation.id) == []
            with engine.connect() as connection:
                assert connection.scalar(text(
                    "SELECT count(*) FROM platform.ai_call_record WHERE task = 'job_classification'"
                )) == 0
        finally:
            _drop_defers(session, [item.id])
            _cleanup(session, [item.id])
            _forget_calls(engine)


@pytest.mark.parametrize("fallback_usage", [30, None])
def test_a_rate_limited_primary_and_a_fallback_answer_are_one_operation_with_summed_usage(
    fallback_usage: int | None,
) -> None:
    """F51-09 AC04: primary 429 reporting 12 tokens, fallback 200 reporting 30: one
    operation, two ordered attempts, 42 recorded tokens; usage the provider never sent is
    unknown, and the failed attempt's tokens are not discarded."""
    primary, fallback = _CHAIN[0], _CHAIN[1]

    def answer(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["model"] == primary:
            return httpx.Response(429, json={
                "error": {"message": "rate limit reached"},
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            })
        usage = (
            None if fallback_usage is None
            else {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": fallback_usage}
        )
        return httpx.Response(200, json=_groq_body(fallback, "{}", usage))

    engine = create_database_engine(os.environ["DATABASE_URL"])
    router, requests = _groq_router(answer, fallback_enabled=True)
    _forget_calls(engine)
    since = datetime.now(UTC) - timedelta(minutes=1)
    with Session(engine) as session:
        item = _opportunity(role_family="UNKNOWN")
        session.add(item)
        session.commit()
        known = _classification_operation_ids(engine)
        try:
            outcome = _run(suggest_fields(session, router, item, prompt=_PROMPT))

            assert outcome.state == "success"
            assert [json.loads(request.content)["model"] for request in requests] == [
                primary, fallback
            ]
            [operation] = _operations_after(engine, known)
            assert operation.state == "success"
            first, second = _attempts_of(engine, operation.id)
            assert (first.operation_ordinal, first.model, first.http_status) == (0, primary, 429)
            assert (first.error_kind, first.prompt_tokens, first.completion_tokens) == (
                "quota", 8, 4
            )
            assert (second.operation_ordinal, second.model, second.http_status) == (
                1, fallback, 200
            )
            assert second.success is True
            window = (since, datetime.now(UTC) + timedelta(minutes=1))
            totals = ai_period_comparison(
                engine, task="job_classification", baseline=(since, since), pilot=window
            )
            assert totals.pilot.requests == 2
            if fallback_usage is None:
                assert (second.prompt_tokens, second.completion_tokens) == (None, None)
                assert totals.pilot.recorded_tokens == 12  # the failed attempt still counts
                assert totals.pilot.requests_without_tokens == 1
                assert "pilot.tokens" in totals.gaps
            else:
                assert (second.prompt_tokens, second.completion_tokens) == (20, 10)
                assert totals.pilot.recorded_tokens == 42
                assert totals.pilot.requests_without_tokens == 0
                assert "pilot.tokens" not in totals.gaps
        finally:
            _drop_defers(session, [item.id])
            _cleanup(session, [item.id])
            _forget_calls(engine)


def test_quota_exhaustion_persists_one_coherent_defer_and_a_rerun_waits_for_availability(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """F51-10 AC04: after the shared balance is gone no second request is sent. The persisted
    defer is scoped to the content, prompt and route, and ends at the real availability; the
    posting is not asked about again until then. Candidates the batch never reached get no
    defer row (the card says every candidate does)."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    router, guard, chain = _quota_router(engine, provider, day_requests=1)
    prompt = load_classification_prompt()
    with Session(engine) as session:
        items = [
            _opportunity(title=f"Engineer {n}", description=f"Engineer {n}, remote.", **_KNOWN)
            for n in range(4)
        ]
        session.add_all(items)
        session.commit()
        ids = [item.id for item in items]
        monkeypatch.setattr(
            worker, "candidates_needing_suggestion", lambda *_args, **_kwargs: items
        )
        started = datetime.now(UTC)
        try:
            worker.suggest_fields_pending(
                engine, router, worker_requests_ceiling=1,
                owner_sub=_SUGGESTION_OWNER,
            )

            assert len(provider.requests) == 1
            defers = session.scalars(
                select(SuggestionDeferModel).where(SuggestionDeferModel.opportunity_id.in_(ids))
            ).all()
            # Only the candidate that met the exhausted balance is deferred; the third and
            # fourth were never attempted and have no row.
            assert [defer.opportunity_id for defer in defers] == [items[1].id]
            defer = defers[0]
            assert (defer.reason, defer.attempt_count, defer.prompt_version) == (
                "quota", 1, prompt.version
            )
            assert defer.route_hash == hashlib.sha256("\0".join(chain).encode()).hexdigest()
            assert defer.content_hash == _suggestion_content_hash(
                "Engineer 1", "Engineer 1, remote.", [SuggestibleField.SENIORITY]
            )
            availability = guard.next_available_at(chain[0])
            assert defer.next_attempt_at > started
            assert abs((defer.next_attempt_at - availability).total_seconds()) < 5

            # Before `next_attempt_at` the deferred posting makes no request, whatever the
            # balance: the provider behind a router with plenty of quota is never reached.
            quiet = _RecordingProvider()
            open_router = AIRouter(quiet, default_routes(_settings()), max_retries=0)
            blocked = _run(suggest_fields(session, open_router, items[1], prompt=prompt))
            assert (blocked.state, blocked.error_kind, blocked.called) == (
                "deferred", "quota", False
            )
            assert blocked.next_attempt_at == defer.next_attempt_at
            assert quiet.requests == []

            # Once the availability time has passed the same content is attempted again.
            session.execute(text(
                "UPDATE platform.ai_suggestion_defer "
                "SET next_attempt_at = now() - interval '1 second' WHERE opportunity_id = :id"
            ), {"id": items[1].id})
            session.commit()
            session.expire_all()
            retried = _run(suggest_fields(session, open_router, items[1], prompt=prompt))
            assert (retried.state, retried.called) == ("success", True)
            assert len(quiet.requests) == 1
            assert session.scalars(
                select(SuggestionDeferModel).where(SuggestionDeferModel.opportunity_id == ids[1])
            ).all() == []
        finally:
            _drop_defers(session, ids)
            _cleanup(session, ids)
            _forget_calls(engine)


def test_a_defer_is_scoped_to_its_content_hash_and_changed_content_is_selectable() -> None:
    """F51-10 AC05: a defer for hash H keeps that content out of the queue and out of the
    provider until it expires; the same posting with content hashing to H2 is selected and
    asked about, while H's defer stays untouched."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    provider = _RecordingProvider()
    router = AIRouter(provider, default_routes(_settings()), max_retries=0)
    route = router.route(AITask.JOB_CLASSIFICATION)
    route_hash = hashlib.sha256("\0".join(route.chain).encode()).hexdigest()
    pending = [SuggestibleField.SENIORITY]

    def selected(session: Session) -> set[UUID]:
        return {
            candidate.id
            for candidate in candidates_needing_suggestion(
                session, limit=100_000, prompt_version=_PROMPT.version,
                route_hash=route_hash, prompt=_PROMPT, route=route,
                owner_sub=_SUGGESTION_OWNER,
            )
        }

    with Session(engine) as session:
        profile_id = _ensure_suggestion_profile(session)
        item = _opportunity(
            title="Backend Engineer", description="We build APIs in Python.", **_KNOWN
        )
        session.add(item)
        session.flush()
        _rank(session, profile_id, [item])
        first_hash = _suggestion_content_hash(
            "Backend Engineer", "We build APIs in Python.", pending
        )
        changed_description = "We build APIs in Python and Go."
        changed_hash = _suggestion_content_hash("Backend Engineer", changed_description, pending)
        assert changed_hash != first_hash
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        defer = SuggestionDeferModel(
            opportunity_id=item.id, content_hash=first_hash, prompt_version=_PROMPT.version,
            route_hash=route_hash, attempt_count=1, reason="transient", next_attempt_at=expires_at,
        )
        session.add(defer)
        session.flush()
        try:
            # H, before it expires: out of the queue, and no request even if asked directly.
            assert item.id not in selected(session)
            blocked = _run(suggest_fields(session, router, item, prompt=_PROMPT))
            assert (blocked.state, blocked.error_kind, blocked.called) == (
                "deferred", "transient", False
            )
            assert blocked.next_attempt_at == expires_at
            assert provider.requests == []

            # H2: the same posting with other content is a different key.
            item.description = changed_description
            session.flush()
            assert item.id in selected(session)
            asked = _run(suggest_fields(session, router, item, prompt=_PROMPT))
            assert asked.called is True
            assert len(provider.requests) == 1
            assert changed_description in provider.requests[0].user
            assert session.get(SuggestionDeferModel, (
                item.id, first_hash, _PROMPT.version, route_hash
            )).next_attempt_at == expires_at

            # Back to H once its defer has expired: selectable again.
            item.description = "We build APIs in Python."
            defer.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            session.flush()
            assert item.id in selected(session)
        finally:
            session.rollback()
            _forget_calls(engine)
