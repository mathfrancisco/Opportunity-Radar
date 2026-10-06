"""Card F20-23: `job_classification` suggestions for a field left `UNKNOWN`.

Every provider call goes through a fake `LLMProvider` defined below: no test here
reaches Groq. Persistence assertions run against the real database, gated like the rest
of `tests/backend/opportunities/` by `RUN_DATABASE_INTEGRATION`.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.domain import RoleFamily, Seniority, WorkMode
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.service import OpportunityVersionConflictError
from opportunity_radar.opportunities.suggestions import (
    ClassificationPrompt,
    OpportunitySuggestionModel,
    SuggestibleField,
    SuggestionAlreadyDecidedError,
    SuggestionNotFoundError,
    SuggestionStatus,
    _suggestion_content_hash,
    accept_suggestion,
    candidates_needing_suggestion,
    reject_suggestion,
    suggest_fields,
    unknown_fields,
)
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import (
    LLMRequest,
    LLMResponse,
    RateLimit,
    Usage,
)
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.tasks import default_routes
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)

_FAST_MODEL = "openai/gpt-oss-20b"

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
        session.commit()
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
        session.commit()
        try:
            # The query is catalogue-wide and ordered by creation; rows other tests left
            # in the shared database would push this test's rows out of a small window,
            # so the limit must cover every candidate that could exist.
            candidates = candidates_needing_suggestion(session, limit=100_000)
            candidate_ids = {opportunity.id for opportunity in candidates}
            assert needs_suggestion.id in candidate_ids
            assert already_suggested.id not in candidate_ids
            assert fully_resolved.id not in candidate_ids
        finally:
            _cleanup(
                session,
                [needs_suggestion.id, already_suggested.id, fully_resolved.id],
            )


def test_suggestion_queue_filters_before_limit_and_pages_stably() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
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
        session.commit()
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
        session.commit()
        try:
            first_page = candidates_needing_suggestion(session, limit=2)
            assert [item.id for item in first_page] == [
                item.id for item in sorted(eligible, key=lambda row: row.id)[:2]
            ]
            last = first_page[-1]
            second_page = candidates_needing_suggestion(
                session, limit=2, after=(last.created_at, last.id)
            )
            # The shared database may hold newer candidates from other tests; they come
            # after this test's rows and never include a resolved one.
            assert second_page[0].id == sorted(eligible, key=lambda row: row.id)[2].id
            assert {item.id for item in second_page}.isdisjoint(
                {item.id for item in resolved} | {item.id for item in first_page}
            )
        finally:
            _cleanup(session, [item.id for item in resolved + eligible])


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
