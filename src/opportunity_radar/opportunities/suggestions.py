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

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
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
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from opportunity_radar.opportunities.domain import RoleFamily, Seniority, WorkMode
from opportunity_radar.opportunities.models import SCHEMA, OpportunityModel
from opportunity_radar.opportunities.role_family import ROLE_FAMILY_VERSION
from opportunity_radar.platform.ai.budget import fits
from opportunity_radar.platform.ai.errors import ProviderError
from opportunity_radar.platform.ai.router import AIRouter
from opportunity_radar.platform.ai.sanitizer import sanitize_for_llm
from opportunity_radar.platform.ai.tasks import AITask
from opportunity_radar.platform.database import Base
from opportunity_radar.platform.logging import get_logger

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
    session: Session, *, limit: int, over_fetch_factor: int = 5
) -> list[OpportunityModel]:
    """Opportunities with at least one `UNKNOWN` field lacking a suggestion for the
    current version, up to `limit`. Over-fetches from the database because whether a
    row still needs a call depends on suggestion rows already keyed by its version,
    which the query itself does not filter by (three different columns, one row)."""
    rows = session.scalars(
        select(OpportunityModel)
        .where(
            or_(
                OpportunityModel.role_family == RoleFamily.UNKNOWN.value,
                OpportunityModel.seniority == Seniority.UNKNOWN.value,
                OpportunityModel.work_mode == WorkMode.UNKNOWN.value,
            )
        )
        .order_by(OpportunityModel.created_at)
        .limit(limit * over_fetch_factor)
    ).all()
    selected: list[OpportunityModel] = []
    for opportunity in rows:
        pending = {field.value for field in unknown_fields(opportunity)}
        if pending - existing_suggestion_fields(session, opportunity):
            selected.append(opportunity)
        if len(selected) >= limit:
            break
    return selected


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


@dataclass(frozen=True, slots=True)
class SuggestionOutcome:
    created: tuple[OpportunitySuggestionModel, ...] = ()
    discarded_fields: tuple[str, ...] = ()  # value/evidence rejected (no literal match)
    called: bool = False


async def suggest_fields(
    session: Session,
    router: AIRouter,
    opportunity: OpportunityModel,
    *,
    prompt: ClassificationPrompt | None = None,
) -> SuggestionOutcome:
    """Ask the `job_classification` task for the fields still `UNKNOWN`, and persist
    what survives the evidence check. Never raises for a provider failure: the caller
    (the worker job) must keep going through its batch."""
    pending = [
        field
        for field in unknown_fields(opportunity)
        if field.value not in existing_suggestion_fields(session, opportunity)
    ]
    if not pending:
        return SuggestionOutcome()

    prompt = prompt or load_classification_prompt()
    sanitized = sanitize_for_llm(
        {"title": opportunity.canonical_title or "", "description": opportunity.description or ""}
    )
    title = str(sanitized.get("title") or "")
    description = str(sanitized.get("description") or "")
    submitted_text = f"{title}\n{description}"

    route = router.route(AITask.JOB_CLASSIFICATION)
    while description and not fits(prompt.system, _render_user_content(
        prompt, pending_fields=pending, title=title, description=description
    ), route.budget):
        description = description[: max(0, len(description) - 200)]
    submitted_text = f"{title}\n{description}"
    user_content = _render_user_content(
        prompt, pending_fields=pending, title=title, description=description
    )
    if not fits(prompt.system, user_content, route.budget):
        logger.info(
            "job_classification prompt does not fit the task budget even without a "
            "description; skipping",
            extra={"opportunity_id": str(opportunity.id)},
        )
        return SuggestionOutcome()

    try:
        result = await router.run(
            AITask.JOB_CLASSIFICATION,
            system=prompt.system,
            user=user_content,
            schema_name=prompt.schema_version.replace("-", "_"),
            json_schema=prompt.output_schema,
            temperature=0,
        )
    except ProviderError as error:
        logger.warning(
            "job_classification call failed",
            extra={"opportunity_id": str(opportunity.id), "error": error.summary},
        )
        return SuggestionOutcome()

    try:
        payload = json.loads(result.response.content)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning(
            "job_classification response is not valid JSON",
            extra={"opportunity_id": str(opportunity.id)},
        )
        return SuggestionOutcome()

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
    return SuggestionOutcome(created=tuple(created), discarded_fields=tuple(discarded), called=True)


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
    "accept_suggestion",
    "candidates_needing_suggestion",
    "load_classification_prompt",
    "reject_suggestion",
    "suggest_fields",
    "unknown_fields",
]
