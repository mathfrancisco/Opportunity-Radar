"""What makes an assessment current, in one place.

An assessment is a statement about a specific set of inputs. Five things can change under
it, and comparing only `profile_version_id` — the obvious one — silently accepts an
assessment of a posting that has since been rewritten, or scored by rules that no longer
apply. The five components are:

  * the opportunity content version;
  * the active `ProfileVersion`;
  * the ruleset version;
  * the skill taxonomy version;
  * the UTC reference day.

The first four define **currency**: if any of them moved, the stored score describes
inputs that no longer exist, and the assessment is stale. The fifth defines **frequency**:
the same inputs are evaluated at most once per UTC day, so a queue that keeps finding the
same opportunity does not re-score it every pass.

Currency is asked in two very different places — the worker, over ORM objects, and the
Inbox read model, in SQL over millions of rows. Both are built from the same component
list here, because two implementations of "is this current" drift, and the drift shows up
as an Inbox that disagrees with the worker about what it is looking at.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Date, String, cast, func, literal, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel, OpportunitySkillModel
from opportunity_radar.profile.models import ProfileVersionModel

#: The components that decide currency. The reference day is deliberately absent: a new
#: day does not invalidate a score, it only permits a fresh evaluation.
CURRENCY_COMPONENTS = (
    "opportunity_version",
    "profile_version_id",
    "rules_version",
    "taxonomy_version",
)


@dataclass(frozen=True, slots=True)
class EvaluationIdentity:
    """The full identity of one evaluation, currency plus reference day."""

    opportunity_id: UUID
    opportunity_version: int
    profile_version_id: UUID
    rules_version: str
    taxonomy_version: str
    reference_date: date

    @classmethod
    def build(
        cls,
        *,
        opportunity_id: UUID,
        opportunity_version: int,
        profile_version_id: UUID,
        rules_version: str,
        taxonomy_version: str,
        assessed_at: datetime,
    ) -> EvaluationIdentity:
        return cls(
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
            profile_version_id=profile_version_id,
            rules_version=rules_version,
            taxonomy_version=taxonomy_version,
            reference_date=reference_day(assessed_at),
        )

    def describes(self, assessment: MatchAssessmentModel) -> bool:
        """Whether the assessment still speaks about the inputs this identity names."""
        return (
            assessment.opportunity_id == self.opportunity_id
            and assessment.opportunity_version == self.opportunity_version
            and assessment.profile_version_id == self.profile_version_id
            and assessment.rules_version == self.rules_version
            and assessment.taxonomy_version == self.taxonomy_version
        )

    def is_stale(self, assessment: MatchAssessmentModel) -> bool:
        return not self.describes(assessment)

    def evaluated_on_reference_day(self, assessment: MatchAssessmentModel) -> bool:
        """Whether this identity was already evaluated within its UTC day."""
        return self.describes(assessment) and (
            reference_day(assessment.assessed_at) == self.reference_date
        )


def reference_day(moment: datetime) -> date:
    """The UTC day an assessment belongs to, however the timestamp was stored."""
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(UTC).date()


def active_profile_version_id() -> Any:
    """Scalar subquery for the single active `ProfileVersion`, or NULL when there is none.

    NULL is the honest answer: without an active profile nothing can be current, and every
    stored assessment is a statement about a profile that is no longer in force.
    """
    return (
        select(ProfileVersionModel.id)
        .where(ProfileVersionModel.status == "ACTIVE")
        .limit(1)
        .scalar_subquery()
    )


def opportunity_taxonomy_version() -> Any:
    """SQL twin of the taxonomy version the matching service derives from an opportunity.

    Both sides sort the distinct versions and join them with `+`, and both fall back to the
    current taxonomy when an opportunity carries no skills at all.
    """
    aggregated = (
        select(
            func.string_agg(
                func.distinct(OpportunitySkillModel.taxonomy_version),
                aggregate_order_by(
                    literal("+", String), OpportunitySkillModel.taxonomy_version
                ),
            )
        )
        .where(OpportunitySkillModel.opportunity_id == OpportunityModel.id)
        # Explicit, not auto-correlated. Nested inside an EXISTS, SQLAlchemy adds
        # `opportunity` to this subquery's own FROM instead of referring to the outer row,
        # and the aggregate silently becomes every skill of every opportunity.
        .correlate(OpportunityModel)
        .scalar_subquery()
    )
    return func.coalesce(aggregated, literal(SKILL_TAXONOMY_VERSION))


def assessment_reference_day(column: Any) -> Any:
    """The UTC day of an assessment timestamp, as SQL.

    The column is `timestamptz`, so it must be converted to UTC before the date is taken:
    casting directly would give the server's local day and silently move the daily cap.
    """
    return cast(func.timezone(literal("UTC"), column), Date)


def is_current_assessment(
    assessment: Any,
    *,
    rules_version: str,
    profile_version_id: Any | None = None,
) -> ColumnElement[bool]:
    """SQL predicate for the same four components `EvaluationIdentity.describes` compares.

    `assessment` is any selectable exposing the assessment columns, so the read model can
    apply this to a ranked subquery rather than to the table.
    """
    profile = (
        active_profile_version_id() if profile_version_id is None else profile_version_id
    )
    return (
        (assessment.c.opportunity_version == OpportunityModel.version)
        & (assessment.c.profile_version_id == profile)
        & (assessment.c.rules_version == literal(rules_version))
        & (assessment.c.taxonomy_version == opportunity_taxonomy_version())
    )
