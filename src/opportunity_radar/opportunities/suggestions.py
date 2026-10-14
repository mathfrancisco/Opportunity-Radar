"""AI-assisted suggestions for a field a deterministic rule left `UNKNOWN` (card F20-23).

`role-family-v1` (`role_family.py`), `seniority-v2` and `regions-v1` (SPEC 43 SS6, SS6.1)
decide most opportunities; the rest keep `role_family`, `seniority` or `work_mode` as
`UNKNOWN`. This module asks the `job_classification` task (routed to the `fast` model,
card F20-09) for a suggestion on exactly those fields, and keeps it in its own table
(`FieldSuggestionModel`) until an operator accepts or rejects it — the canonical
`OpportunityModel` column is never written without that confirmation (F18-06/F20-24).

Everything here is defensive rather than authoritative:

- only fields still `UNKNOWN` on the current row are ever asked about (never a field a
  rule already decided);
- a suggestion whose `evidence` does not appear literally in the sanitized text sent to
  the model is discarded before it is persisted;
- accepting writes `source=llm_confirmed` evidence for `role_family` (the only canonical
  field with an evidence column today) and simply sets the value for `seniority` and
  `work_mode`; the acceptance itself — who, when, from which suggestion — lives in this
  table's own `decided_by`/`decided_at`/`model`/`prompt_version` columns, which is the
  permanent audit trail for all three fields.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import yaml
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    exists,
    func,
    or_,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from opportunity_radar.matching import currency
from opportunity_radar.matching.models import CurrentAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.domain import RoleFamily, Seniority, WorkMode
from opportunity_radar.opportunities.models import SCHEMA, OpportunityModel
from opportunity_radar.opportunities.role_family import ROLE_FAMILY_VERSION
from opportunity_radar.platform.ai.budget import fits
from opportunity_radar.platform.ai.errors import ErrorKind, ProviderError
from opportunity_radar.platform.ai.providers.base import LLMResponse
from opportunity_radar.platform.ai.router import AIRouter, Attempt
from opportunity_radar.platform.ai.sanitizer import sanitize_for_llm
from opportunity_radar.platform.ai.tasks import AITask, ModelRoute
from opportunity_radar.platform.ai.telemetry import (
    finish_operation,
    record_attempt_started,
    record_calls,
    records_from_attempts,
    start_operation,
)
from opportunity_radar.platform.database import Base
from opportunity_radar.platform.logging import get_logger
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService

logger = get_logger("opportunity_radar.opportunities.suggestions")

#: Prompt family this module loads (`prompts/job_classification/v1/`), distinct from
#: `matching.prompts` (`opportunity_analysis`), whose loader is coupled to a different
#: schema family (`matching.analysis.OUTPUT_SCHEMAS`).
PROMPT_NAME = "job_classification/v1"
_PROMPT_FAMILY = "job_classification"
_DEFAULT_PROMPT_VERSION = "v1"


class SuggestibleField(StrEnum):
    ROLE_FAMILY = "role_family"
    SENIORITY = "seniority"
    WORK_MODE = "work_mode"


#: Verdicts worth a background model call: a suggestion can only change what the user does
#: with a posting the active profile already ranks at the top.
SUGGESTION_VERDICTS = ("HIGH_PRIORITY", "RECOMMENDED")


class SuggestionStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


#: What a suggested `field` may become on the canonical row, and the domain enum that
#: validates the model's answer for it. `UNKNOWN` is never a valid suggestion: a model
#: unsure of the field must answer `null`, not the value that means "still unsure".
_FIELD_ENUMS: dict[SuggestibleField, type] = {
    SuggestibleField.ROLE_FAMILY: RoleFamily,
    SuggestibleField.SENIORITY: Seniority,
    SuggestibleField.WORK_MODE: WorkMode,
}


class OpportunitySuggestionModel(Base):
    """One `fast`-model suggestion for one field of one opportunity version.

    `(opportunity_id, opportunity_version, field)` is unique: reclassifying the same
    version never creates a second row (idempotency per version, card F20-23's tests),
    and a posting edited after the suggestion was made gets its own row against the new
    `opportunity.version` instead of silently overwriting a suggestion an operator may
    still be reviewing.
    """

    __tablename__ = "field_suggestion"
    __table_args__ = (
        CheckConstraint(
            "field IN ('role_family', 'seniority', 'work_mode')",
            name="ck_field_suggestion_field",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED')",
            name="ck_field_suggestion_status",
        ),
        UniqueConstraint(
            "opportunity_id",
            "opportunity_version",
            "field",
            name="uq_field_suggestion_opportunity_version_field",
        ),
        Index("ix_field_suggestion_status", "status"),
        {"schema": SCHEMA},
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        nullable=False,
    )
    opportunity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SuggestionDeferModel(Base):
    """Retry schedule scoped to sanitized content, prompt, and model route."""

    __tablename__ = "ai_suggestion_defer"
    __table_args__ = (
        Index("ix_ai_suggestion_defer_next_attempt", "next_attempt_at"),
        {"schema": "platform"},
    )

    opportunity_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.opportunity.id", ondelete="CASCADE"),
        primary_key=True,
    )
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    route_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SuggestionNotFoundError(LookupError):
    pass


class SuggestionAlreadyDecidedError(ValueError):
    """The suggestion is `ACCEPTED` or `REJECTED` already; the requested transition
    (accepting a rejected suggestion, or vice-versa) is not a supported change of mind."""


@dataclass(frozen=True, slots=True)
class ClassificationPrompt:
    """The three artifacts `prompts/job_classification/v1/` holds, loaded once."""

    version: str
    system: str
    user_template: str
    schema_version: str
    output_schema: dict[str, Any]


def prompts_root() -> Path:
    candidates = (
        Path.cwd() / "prompts",
        Path(__file__).resolve().parents[3] / "prompts",
    )
    return next((path for path in candidates if path.is_dir()), candidates[0])


def load_classification_prompt(
    name: str = _DEFAULT_PROMPT_VERSION, *, root: Path | None = None
) -> ClassificationPrompt:
    directory = (root or prompts_root()) / _PROMPT_FAMILY / name
    system = (directory / "system.md").read_text(encoding="utf-8").strip()
    user_template = (directory / "user.md.j2").read_text(encoding="utf-8").strip()
    output_schema = json.loads((directory / "output.schema.json").read_text(encoding="utf-8"))
    metadata = yaml.safe_load((directory / "metadata.yaml").read_text(encoding="utf-8")) or {}
    return ClassificationPrompt(
        version=f"{_PROMPT_FAMILY}/{name}",
        system=system,
        user_template=user_template,
        schema_version=str(metadata.get("schema_version", f"{_PROMPT_FAMILY}-{name}")),
        output_schema=output_schema,
    )


def unknown_fields(opportunity: OpportunityModel) -> list[SuggestibleField]:
    """Fields the deterministic rules left `UNKNOWN` on this row, right now."""
    fields = []
    if opportunity.role_family == RoleFamily.UNKNOWN.value:
        fields.append(SuggestibleField.ROLE_FAMILY)
    if opportunity.seniority == Seniority.UNKNOWN.value:
        fields.append(SuggestibleField.SENIORITY)
    if opportunity.work_mode == WorkMode.UNKNOWN.value:
        fields.append(SuggestibleField.WORK_MODE)
    return fields


def existing_suggestion_fields(session: Session, opportunity: OpportunityModel) -> set[str]:
    """Fields already carrying a suggestion (any status) for this opportunity's version."""
    rows = session.scalars(
        select(OpportunitySuggestionModel.field).where(
            OpportunitySuggestionModel.opportunity_id == opportunity.id,
            OpportunitySuggestionModel.opportunity_version == opportunity.version,
        )
    ).all()
    return set(rows)


def candidates_needing_suggestion(
    session: Session,
    *,
    limit: int,
    owner_sub: str | None = None,
    over_fetch_factor: int = 5,
    after: tuple[datetime, UUID] | None = None,
    prompt_version: str | None = None,
    route_hash: str | None = None,
    prompt: ClassificationPrompt | None = None,
    route: ModelRoute | None = None,
    now: datetime | None = None,
) -> list[OpportunityModel]:
    """Return pending rows in stable `(created_at, id)` order.

    Eligibility stays in SQL so resolved rows cannot consume the page before newer
    candidates: a field still `UNKNOWN` without a suggestion for this version, and a
    current assessment under the active profile with a top verdict (none, with no active
    profile). `after` is the last row from the prior page for keyset pagination.
    `over_fetch_factor` remains accepted for callers using the previous signature.
    """
    del over_fetch_factor
    owner_sub = ProfileService.operational_owner(owner_sub)
    if owner_sub is None:
        return []
    pending_fields = (
        and_(
            OpportunityModel.role_family == RoleFamily.UNKNOWN.value,
            ~exists().where(
                OpportunitySuggestionModel.opportunity_id == OpportunityModel.id,
                OpportunitySuggestionModel.opportunity_version == OpportunityModel.version,
                OpportunitySuggestionModel.field == SuggestibleField.ROLE_FAMILY.value,
            ),
        ),
        and_(
            OpportunityModel.seniority == Seniority.UNKNOWN.value,
            ~exists().where(
                OpportunitySuggestionModel.opportunity_id == OpportunityModel.id,
                OpportunitySuggestionModel.opportunity_version == OpportunityModel.version,
                OpportunitySuggestionModel.field == SuggestibleField.SENIORITY.value,
            ),
        ),
        and_(
            OpportunityModel.work_mode == WorkMode.UNKNOWN.value,
            ~exists().where(
                OpportunitySuggestionModel.opportunity_id == OpportunityModel.id,
                OpportunitySuggestionModel.opportunity_version == OpportunityModel.version,
                OpportunitySuggestionModel.field == SuggestibleField.WORK_MODE.value,
            ),
        ),
    )
    pointer = CurrentAssessmentModel.__table__
    active_profile = currency.active_profile_version_id(owner_sub)
    owner_assessment = exists().where(
        ProfileVersionModel.id == pointer.c.profile_version_id,
        ProfileVersionModel.career_profile_id == CareerProfileModel.id,
        CareerProfileModel.owner_sub == owner_sub,
    )
    has_top_assessment = exists().where(
        pointer.c.opportunity_id == OpportunityModel.id,
        pointer.c.verdict.in_(SUGGESTION_VERDICTS),
        currency.is_current_assessment(
            pointer, rules_version=RULES_VERSION, profile_version_id=active_profile
        ),
        owner_assessment,
    )
    selection = or_(*pending_fields, has_top_assessment)
    # The worker runs under one configured operational identity. Do not let the global
    # "unknown field" branch select postings that identity has not matched.
    has_owner_assessment = exists().where(
        pointer.c.opportunity_id == OpportunityModel.id,
        pointer.c.verdict.in_(SUGGESTION_VERDICTS),
        currency.is_current_assessment(
            pointer, rules_version=RULES_VERSION, profile_version_id=active_profile
        ),
        owner_assessment,
    )
    selection = and_(selection, has_owner_assessment)
    query = select(OpportunityModel).where(selection)
    rows: list[OpportunityModel] = []
    cursor = after
    page_size = max(limit, 100)
    moment = now or datetime.now(UTC)
    while len(rows) < limit:
        page_query = query
        if cursor is not None:
            created_at, opportunity_id = cursor
            page_query = page_query.where(
                or_(
                    OpportunityModel.created_at > created_at,
                    and_(OpportunityModel.created_at == created_at,
                         OpportunityModel.id > opportunity_id),
                )
            )
        page = list(session.scalars(
            page_query.order_by(OpportunityModel.created_at, OpportunityModel.id)
            .limit(page_size)
        ).all())
        if not page:
            break
        cursor = (page[-1].created_at, page[-1].id)
        ids = [item.id for item in page]
        defers = session.scalars(
            select(SuggestionDeferModel).where(
                SuggestionDeferModel.opportunity_id.in_(ids),
                SuggestionDeferModel.next_attempt_at > moment,
                *([SuggestionDeferModel.prompt_version == prompt_version]
                  if prompt_version is not None else []),
                *([SuggestionDeferModel.route_hash == route_hash]
                  if route_hash is not None else []),
            )
        ).all()
        deferred_keys = {(item.opportunity_id, item.content_hash) for item in defers}
        for item in page:
            fields = [field for field in unknown_fields(item)
                      if field.value not in existing_suggestion_fields(session, item)]
            if not fields:
                continue
            sanitized = sanitize_for_llm({
                "title": item.canonical_title or "", "description": item.description or ""
            })
            title = str(sanitized.get("title") or "")
            description = str(sanitized.get("description") or "")
            if prompt is not None and route is not None:
                title, description, _ = _fit_submission(
                    prompt, route, fields, title, description
                )
            digest = _suggestion_content_hash(title, description, fields)
            if (item.id, digest) not in deferred_keys:
                rows.append(item)
                if len(rows) == limit:
                    break
        if len(page) < page_size:
            break
    return rows


def _render_user_content(
    prompt: ClassificationPrompt,
    *,
    pending_fields: Sequence[SuggestibleField],
    title: str,
    description: str,
) -> str:
    pending_json = json.dumps([field.value for field in pending_fields], ensure_ascii=False)
    values = {
        "pending_fields": pending_json,
        "title": json.dumps(title, ensure_ascii=False),
        "description": json.dumps(description, ensure_ascii=False),
    }
    rendered = prompt.user_template
    for name, encoded in values.items():
        rendered = rendered.replace("{{ " + name + " }}", encoded)
        rendered = rendered.replace("{{" + name + "}}", encoded)
    return rendered


def _fit_submission(
    prompt: ClassificationPrompt,
    route: ModelRoute,
    pending: Sequence[SuggestibleField],
    title: str,
    description: str,
) -> tuple[str, str, str | None]:
    """Return the exact sanitized/truncated description represented in the request."""
    while description and not fits(
        prompt.system,
        _render_user_content(
            prompt, pending_fields=pending, title=title, description=description
        ),
        route.budget,
    ):
        description = description[:max(0, len(description) - 200)]
    user_content = _render_user_content(
        prompt, pending_fields=pending, title=title, description=description
    )
    if not fits(prompt.system, user_content, route.budget):
        return title, description, None
    return title, description, user_content


@dataclass(frozen=True, slots=True)
class SuggestionOutcome:
    created: tuple[OpportunitySuggestionModel, ...] = ()
    discarded_fields: tuple[str, ...] = ()  # value/evidence rejected (no literal match)
    called: bool = False
    state: str = "not_needed"
    error_kind: str | None = None
    next_attempt_at: datetime | None = None
    quota_exhausted: bool = False  # the day/global balance is gone: no other call can pass


@contextmanager
def _suggestion_claim(engine: Engine, opportunity_id: UUID) -> Iterator[bool]:
    """Whether this caller owns the posting's suggestion for the duration of the block.

    A PostgreSQL session advisory lock on a connection of its own: two workers (or the
    worker and the API) never ask the provider about the same posting at the same time
    (F51-10 AC06). The lock dies with the connection, so a crashed owner leaves no claim
    behind and nothing has to expire."""
    digest = hashlib.sha256(f"field-suggestion:{opportunity_id}".encode()).digest()
    key = int.from_bytes(digest[:8], "big", signed=True)
    with engine.connect() as connection:
        claimed = bool(connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
        connection.commit()
        try:
            yield claimed
        finally:
            if claimed:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                connection.commit()


async def suggest_fields(
    session: Session,
    router: AIRouter,
    opportunity: OpportunityModel,
    *,
    prompt: ClassificationPrompt | None = None,
    quota_ceiling_requests: int | None = None,
    ai_enabled: bool = True,
) -> SuggestionOutcome:
    """Ask the `job_classification` task for the fields still `UNKNOWN`, and persist
    what survives the evidence check. Never raises for a provider failure: the caller
    (the worker job) must keep going through its batch.

    One caller at a time per posting: a second one gets `claimed_elsewhere` without a
    provider call, and a later one finds the fields already suggested."""
    bind = session.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    with _suggestion_claim(engine, opportunity.id) as claimed:
        if not claimed:
            operation_id = uuid4()
            _start_suggestion_operation(engine, operation_id, None)
            _finish_suggestion_operation(engine, operation_id, "preflight", "claimed_elsewhere")
            return SuggestionOutcome(state="preflight", error_kind="claimed_elsewhere")
        return await _suggest_fields_claimed(
            session,
            router,
            opportunity,
            prompt=prompt,
            quota_ceiling_requests=quota_ceiling_requests,
            ai_enabled=ai_enabled,
        )


async def _suggest_fields_claimed(
    session: Session,
    router: AIRouter,
    opportunity: OpportunityModel,
    *,
    prompt: ClassificationPrompt | None,
    quota_ceiling_requests: int | None,
    ai_enabled: bool,
) -> SuggestionOutcome:
    operation_id = uuid4()
    bind = session.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    try:
        prompt = prompt or load_classification_prompt()
    except Exception:
        _start_suggestion_operation(engine, operation_id, None)
        _finish_suggestion_operation(engine, operation_id, "internal_error", "prompt_error")
        raise
    _start_suggestion_operation(engine, operation_id, prompt.version)
    if not ai_enabled:
        _finish_suggestion_operation(engine, operation_id, "preflight", "ai_disabled")
        return SuggestionOutcome(state="preflight", error_kind="ai_disabled")

    pending = [
        field
        for field in unknown_fields(opportunity)
        if field.value not in existing_suggestion_fields(session, opportunity)
    ]
    if not pending:
        _finish_suggestion_operation(engine, operation_id, "preflight", "no_pending_fields")
        return SuggestionOutcome(state="preflight")

    sanitized = sanitize_for_llm(
        {"title": opportunity.canonical_title or "", "description": opportunity.description or ""}
    )
    title = str(sanitized.get("title") or "")
    description = str(sanitized.get("description") or "")
    if not title.strip() or not description.strip():
        _finish_suggestion_operation(engine, operation_id, "preflight", "insufficient_content")
        return SuggestionOutcome(state="preflight", error_kind="insufficient_content")

    try:
        route = router.route(AITask.JOB_CLASSIFICATION)
    except Exception:
        _finish_suggestion_operation(engine, operation_id, "internal_error", "route_error")
        raise
    title, description, user_content = _fit_submission(
        prompt, route, pending, title, description
    )
    if user_content is None:
        logger.info(
            "job_classification prompt does not fit the task budget even without a "
            "description; skipping",
            extra={"opportunity_id": str(opportunity.id)},
        )
        _finish_suggestion_operation(engine, operation_id, "preflight", "context_overflow")
        return SuggestionOutcome(state="preflight", error_kind="context_overflow")

    submitted_text = f"{title}\n{description}"
    content_hash = _suggestion_content_hash(title, description, pending)
    route_hash = hashlib.sha256("\0".join(route.chain).encode()).hexdigest()
    now = datetime.now(UTC)
    deferred = session.get(SuggestionDeferModel, (
        opportunity.id, content_hash, prompt.version, route_hash,
    ))
    if deferred is not None and deferred.next_attempt_at > now:
        _finish_suggestion_operation(engine, operation_id, "deferred", deferred.reason)
        return SuggestionOutcome(
            state="deferred", error_kind=deferred.reason,
            next_attempt_at=deferred.next_attempt_at,
        )

    async def on_attempt_started(
        op_id: UUID, ordinal: int, model: str, attempt: int
    ) -> None:
        try:
            await asyncio.to_thread(
                record_attempt_started,
                engine,
                operation_id=op_id,
                operation_ordinal=ordinal,
                task=AITask.JOB_CLASSIFICATION.value,
                provider="groq",
                model=model,
                attempt=attempt,
                prompt_version=prompt.version,
                fallback_used=model != route.chain[0],
            )
        except Exception:  # telemetry must never prevent the provider request
            logger.warning("AI suggestion attempt telemetry start failed", exc_info=True)

    try:
        result = await router.run(
            AITask.JOB_CLASSIFICATION,
            system=prompt.system,
            user=user_content,
            schema_name=prompt.schema_version.replace("-", "_"),
            json_schema=prompt.output_schema,
            temperature=0,
            operation_id=operation_id,
            quota_ceiling_requests=quota_ceiling_requests,
            on_attempt_started=on_attempt_started,
        )
    except ProviderError as error:
        logger.warning(
            "job_classification call failed",
            extra={"opportunity_id": str(opportunity.id), "error_kind": error.kind.value},
        )
        _record_suggestion_operation(
            engine, operation_id, attempts=error.attempts, state=(
                "provider_error" if error.attempts else (
                    "deferred" if error.quota_exhausted else "preflight"
                )
            ), error_kind=error.kind.value, prompt_version=prompt.version,
            fallback_used=any(
                attempt.model != route.chain[0] for attempt in error.attempts
            ),
        )
        retry_after = error.retry_after_seconds or min(
            6 * 60 * 60, 60 * (2 ** min(deferred.attempt_count if deferred else 0, 8))
        )
        next_attempt_at = now + timedelta(seconds=retry_after)
        _save_suggestion_defer(
            session, opportunity_id=opportunity.id, content_hash=content_hash,
            prompt_version=prompt.version, route_hash=route_hash,
            prior=deferred, reason=("quota" if error.kind is ErrorKind.QUOTA else error.kind.value),
            next_attempt_at=next_attempt_at,
        )
        return SuggestionOutcome(
            called=bool(error.attempts),
            state=("deferred" if error.quota_exhausted else "provider_error")
            if error.attempts else ("deferred" if error.quota_exhausted else "preflight"),
            error_kind=error.kind.value,
            next_attempt_at=next_attempt_at,
            quota_exhausted=error.quota_exhausted,
        )
    except asyncio.CancelledError as cancellation:
        cancelled_attempts = getattr(cancellation, "attempts", ())
        _record_suggestion_operation(
            engine, operation_id, attempts=cancelled_attempts,
            fallback_used=any(attempt.model != route.chain[0] for attempt in cancelled_attempts),
            state="cancelled", error_kind="cancelled", prompt_version=prompt.version,
        )
        raise
    except Exception:
        _record_suggestion_operation(
            engine, operation_id, attempts=(), state="internal_error",
            error_kind="internal_error", prompt_version=prompt.version,
        )
        raise

    try:
        payload = json.loads(result.response.content)
        if not isinstance(payload, Mapping):
            raise ValueError("response root must be an object")
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning(
            "job_classification response is not valid JSON",
            extra={"opportunity_id": str(opportunity.id)},
        )
        _record_suggestion_operation(
            engine, operation_id, attempts=result.attempts,
            fallback_used=result.fallback_used, response=result.response,
            state="parse_error", error_kind="parse_error", prompt_version=prompt.version,
        )
        return SuggestionOutcome(called=True, state="parse_error", error_kind="parse_error")

    created: list[OpportunitySuggestionModel] = []
    discarded: list[str] = []
    for field in pending:
        entry = payload.get(field.value)
        if not isinstance(entry, Mapping):
            continue
        raw_value = entry.get("value")
        raw_evidence = entry.get("evidence")
        if raw_value is None or not isinstance(raw_evidence, str) or not raw_evidence.strip():
            continue
        if raw_evidence not in submitted_text:
            discarded.append(field.value)
            continue
        enum_type = _FIELD_ENUMS[field]
        try:
            member = enum_type(str(raw_value).upper())
        except ValueError:
            discarded.append(field.value)
            continue
        if member.value == "UNKNOWN":
            continue
        suggestion = OpportunitySuggestionModel(
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            field=field.value,
            value=member.value,
            evidence=raw_evidence,
            model=result.response.model,
            prompt_version=prompt.version,
            status=SuggestionStatus.PENDING.value,
        )
        session.add(suggestion)
        created.append(suggestion)
    if created:
        session.commit()
        for suggestion in created:
            session.refresh(suggestion)
    if deferred is not None:
        session.delete(deferred)
        session.commit()
    _record_suggestion_operation(
        engine, operation_id, attempts=result.attempts,
        fallback_used=result.fallback_used, response=result.response,
        state="success", prompt_version=prompt.version,
    )
    return SuggestionOutcome(
        created=tuple(created), discarded_fields=tuple(discarded), called=True, state="success"
    )


def _suggestion_content_hash(
    title: str, description: str, pending: Sequence[SuggestibleField]
) -> str:
    material = json.dumps(
        {"title": title, "description": description,
         "fields": [field.value for field in pending]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _save_suggestion_defer(
    session: Session,
    *,
    opportunity_id: UUID,
    content_hash: str,
    prompt_version: str,
    route_hash: str,
    prior: SuggestionDeferModel | None,
    reason: str,
    next_attempt_at: datetime,
) -> None:
    defer = prior or SuggestionDeferModel(
        opportunity_id=opportunity_id,
        content_hash=content_hash,
        prompt_version=prompt_version,
        route_hash=route_hash,
        attempt_count=0,
        reason=reason,
        next_attempt_at=next_attempt_at,
    )
    defer.attempt_count += 1
    defer.reason = reason
    defer.next_attempt_at = next_attempt_at
    defer.updated_at = datetime.now(UTC)
    session.add(defer)
    session.commit()


def _start_suggestion_operation(
    engine: Engine, operation_id: UUID, prompt_version: str | None
) -> None:
    try:
        start_operation(
            engine, operation_id=operation_id, task=AITask.JOB_CLASSIFICATION.value,
            prompt_version=prompt_version,
        )
    except Exception:  # telemetry must never block deterministic classification
        logger.warning("AI suggestion operation start telemetry failed", exc_info=True)


def _finish_suggestion_operation(
    engine: Engine, operation_id: UUID, state: str, error_kind: str | None = None
) -> None:
    try:
        finish_operation(engine, operation_id=operation_id, state=state, error_kind=error_kind)
    except Exception:  # telemetry must never block deterministic classification
        logger.warning("AI suggestion operation finish telemetry failed", exc_info=True)


def _record_suggestion_operation(
    engine: Engine,
    operation_id: UUID,
    *,
    attempts: Sequence[Attempt],
    state: str,
    error_kind: str | None = None,
    prompt_version: str | None = None,
    fallback_used: bool = False,
    response: LLMResponse | None = None,
) -> None:
    try:
        if attempts:
            records = records_from_attempts(
                attempts,
                task=AITask.JOB_CLASSIFICATION.value,
                provider="groq",
                fallback_used=fallback_used,
                prompt_version=prompt_version,
                prompt_tokens=response.usage.prompt_tokens if response else None,
                completion_tokens=response.usage.completion_tokens if response else None,
                operation_id=operation_id,
            )
            record_calls(engine, records)
        finish_operation(engine, operation_id=operation_id, state=state, error_kind=error_kind)
    except Exception:  # telemetry must never block deterministic classification
        logger.warning("AI suggestion operation telemetry write failed", exc_info=True)


def accept_suggestion(
    session: Session, suggestion_id: UUID, *, decided_by: str
) -> OpportunitySuggestionModel:
    """Accept a suggestion: write its value onto the canonical column and bump
    `opportunity.version` (the same convention `duplicates.confirm_duplicate` uses for
    any mutation of a canonical field). Idempotent when already `ACCEPTED`."""
    suggestion = session.get(OpportunitySuggestionModel, suggestion_id)
    if suggestion is None:
        raise SuggestionNotFoundError(str(suggestion_id))
    if suggestion.status == SuggestionStatus.ACCEPTED.value:
        return suggestion
    if suggestion.status == SuggestionStatus.REJECTED.value:
        raise SuggestionAlreadyDecidedError("cannot accept an already-rejected suggestion")

    opportunity = session.get(OpportunityModel, suggestion.opportunity_id)
    if opportunity is None:
        raise SuggestionNotFoundError(str(suggestion_id))
    if opportunity.version != suggestion.opportunity_version:
        from opportunity_radar.opportunities.service import OpportunityVersionConflictError

        raise OpportunityVersionConflictError(
            "opportunity changed since this suggestion was made; reclassify instead of "
            "accepting a stale suggestion"
        )

    setattr(opportunity, suggestion.field, suggestion.value)
    if suggestion.field == SuggestibleField.ROLE_FAMILY.value:
        opportunity.role_family_evidence = {
            "origin": "llm_confirmed",
            "evidence": suggestion.evidence,
            "model": suggestion.model,
            "prompt_version": suggestion.prompt_version,
        }
        opportunity.role_family_version = ROLE_FAMILY_VERSION
    opportunity.version += 1

    suggestion.status = SuggestionStatus.ACCEPTED.value
    suggestion.decided_by = decided_by
    suggestion.decided_at = datetime.now(UTC)
    session.commit()
    session.refresh(suggestion)
    return suggestion


def reject_suggestion(
    session: Session, suggestion_id: UUID, *, decided_by: str
) -> OpportunitySuggestionModel:
    """Reject a suggestion: only its own status changes. Idempotent when already
    `REJECTED`."""
    suggestion = session.get(OpportunitySuggestionModel, suggestion_id)
    if suggestion is None:
        raise SuggestionNotFoundError(str(suggestion_id))
    if suggestion.status == SuggestionStatus.REJECTED.value:
        return suggestion
    if suggestion.status == SuggestionStatus.ACCEPTED.value:
        raise SuggestionAlreadyDecidedError("cannot reject an already-accepted suggestion")

    suggestion.status = SuggestionStatus.REJECTED.value
    suggestion.decided_by = decided_by
    suggestion.decided_at = datetime.now(UTC)
    session.commit()
    session.refresh(suggestion)
    return suggestion


__all__ = [
    "ClassificationPrompt",
    "OpportunitySuggestionModel",
    "SuggestibleField",
    "SuggestionAlreadyDecidedError",
    "SuggestionNotFoundError",
    "SuggestionOutcome",
    "SuggestionStatus",
    "SUGGESTION_VERDICTS",
    "accept_suggestion",
    "candidates_needing_suggestion",
    "load_classification_prompt",
    "reject_suggestion",
    "suggest_fields",
    "unknown_fields",
]
