"""What makes an assessment current, in one place.

An assessment is a statement about a specific set of inputs. Five things can change under
it, and comparing only `profile_version_id` — the obvious one — silently accepts an
assessment of a posting that has since been rewritten, or scored by rules that no longer
apply. The five components are:

  * the opportunity content version;
  * the active `ProfileVersion`;
  * the ruleset version;
  * the skill taxonomy version;
  * the RECENCY band the posting's age falls in.

If any of them moved, the stored score describes inputs that no longer exist, and the
assessment is stale. The UTC reference day is not part of the identity: only the RECENCY
factor reads it, and only when the age crosses a band (card F50-07), so a new day alone
does not queue a re-evaluation of every open posting.

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

from sqlalchemy import ColumnElement, Date, Integer, String, case, cast, func, literal, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION
from opportunity_radar.opportunities.models import OpportunityModel, OpportunitySkillModel
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel

#: The components that decide currency. The reference day is deliberately absent: a new
#: day does not invalidate a score unless it moves the posting into another recency band.
CURRENCY_COMPONENTS = (
    "opportunity_version",
    "profile_version_id",
    "rules_version",
    "taxonomy_version",
    "recency_band",
)

#: Upper bounds, in days of age, of the RECENCY score steps in `matching.domain`
#: (`_recency_measurement`: 1.0 up to 3 days, 0.9 to 7, 0.75 to 14, 0.5 to 30, 0.25 after).
#: A test pins them to the scoring code.
RECENCY_BAND_LIMITS = (3, 7, 14, 30)
#: SQL stand-in for "no band": publication date missing or after the reference day.
_NO_BAND = -1


@dataclass(frozen=True, slots=True)
class EvaluationIdentity:
    """The full identity of one evaluation, currency plus reference day."""

    opportunity_id: UUID
    opportunity_version: int
    profile_version_id: UUID
    rules_version: str
    taxonomy_version: str
    reference_date: date
    published_at: datetime | None

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
        published_at: datetime | None,
    ) -> EvaluationIdentity:
        return cls(
            opportunity_id=opportunity_id,
            opportunity_version=opportunity_version,
            profile_version_id=profile_version_id,
            rules_version=rules_version,
            taxonomy_version=taxonomy_version,
            reference_date=reference_day(assessed_at),
            published_at=published_at,
        )

    def describes(self, assessment: MatchAssessmentModel) -> bool:
        """Whether the assessment still speaks about the inputs this identity names."""
        return (
            assessment.opportunity_id == self.opportunity_id
            and assessment.opportunity_version == self.opportunity_version
            and assessment.profile_version_id == self.profile_version_id
            and assessment.rules_version == self.rules_version
            and assessment.taxonomy_version == self.taxonomy_version
            and recency_band(self.published_at, reference_day(assessment.assessed_at))
            == recency_band(self.published_at, self.reference_date)
        )

    def is_stale(self, assessment: MatchAssessmentModel) -> bool:
        return not self.describes(assessment)


def reference_day(moment: datetime) -> date:
    """The UTC day an assessment belongs to, however the timestamp was stored."""
    if moment.tzinfo is None:
        return moment.date()
    return moment.astimezone(UTC).date()


def recency_band(published_at: datetime | None, reference: date) -> int | None:
    """The RECENCY score step a posting's age falls in on `reference`, `None` if unknown."""
    if published_at is None:
        return None
    age_days = (reference - reference_day(published_at)).days
    if age_days < 0:
        return None
    return next(
        (index for index, limit in enumerate(RECENCY_BAND_LIMITS) if age_days <= limit),
        len(RECENCY_BAND_LIMITS),
    )


def active_profile_version_id(owner_sub: str | None = None) -> Any:
    """Scalar subquery for an owner's active `ProfileVersion`, or NULL when absent.

    NULL is the honest answer: without an active profile nothing can be current, and every
    stored assessment is a statement about a profile that is no longer in force.
    """
    statement = select(ProfileVersionModel.id).where(ProfileVersionModel.status == "ACTIVE")
    if owner_sub is not None:
        statement = statement.join(CareerProfileModel).where(
            CareerProfileModel.owner_sub == owner_sub
        )
    return statement.limit(1).scalar_subquery()


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


def opportunity_taxonomy_versions() -> Any:
    """Every opportunity's taxonomy version, computed once, as a subquery to join.

    Same value as `opportunity_taxonomy_version()` (the correlated twin), but a reader that
    looks at thousands of rows joins this on `opportunity_id` and reads `taxonomy_version`
    (NULL for an opportunity with no skills: wrap it in `with_taxonomy_fallback`), instead
    of running one subquery per row.
    """
    return (
        select(
            OpportunitySkillModel.opportunity_id.label("opportunity_id"),
            func.string_agg(
                func.distinct(OpportunitySkillModel.taxonomy_version),
                aggregate_order_by(
                    literal("+", String), OpportunitySkillModel.taxonomy_version
                ),
            ).label("taxonomy_version"),
        )
        .group_by(OpportunitySkillModel.opportunity_id)
        .subquery("opportunity_taxonomy")
    )


def with_taxonomy_fallback(joined_version: Any) -> Any:
    """The joined taxonomy version, or the current taxonomy when the opportunity has no skills."""
    return func.coalesce(joined_version, literal(SKILL_TAXONOMY_VERSION))


def assessment_reference_day(column: Any) -> Any:
    """The UTC day of an assessment timestamp, as SQL.

    The column is `timestamptz`, so it must be converted to UTC before the date is taken:
    casting directly would give the server's local day and silently move the daily cap.
    """
    return cast(func.timezone(literal("UTC"), column), Date)


def _recency_band_sql(reference: Any) -> Any:
    """SQL twin of `recency_band` for the joined opportunity, on a UTC `reference` date."""
    published_day = cast(func.timezone(literal("UTC"), OpportunityModel.published_at), Date)
    age_days = reference.op("-", return_type=Integer)(published_day)
    return case(
        (OpportunityModel.published_at.is_(None), _NO_BAND),
        (age_days < 0, _NO_BAND),
        *((age_days <= limit, index) for index, limit in enumerate(RECENCY_BAND_LIMITS)),
        else_=len(RECENCY_BAND_LIMITS),
    )


def is_current_assessment(
    assessment: Any,
    *,
    rules_version: str,
    profile_version_id: Any | None = None,
    reference: datetime | None = None,
    taxonomy_version: Any | None = None,
) -> ColumnElement[bool]:
    """SQL predicate for the same components `EvaluationIdentity.describes` compares.

    `assessment` is any selectable exposing the assessment columns, so the read model can
    apply this to a ranked subquery rather than to the table. `reference` is the moment the
    recency band is measured at; it defaults to now. `taxonomy_version` is the opportunity's
    taxonomy version when the caller has already joined it (`opportunity_taxonomy_versions`);
    by default it is the correlated `opportunity_taxonomy_version()`.
    """
    profile = (
        active_profile_version_id() if profile_version_id is None else profile_version_id
    )
    return (
        (assessment.c.opportunity_version == OpportunityModel.version)
        & (assessment.c.profile_version_id == profile)
        & (assessment.c.rules_version == literal(rules_version))
        & (
            assessment.c.taxonomy_version
            == (opportunity_taxonomy_version() if taxonomy_version is None else taxonomy_version)
        )
        & (
            _recency_band_sql(assessment_reference_day(assessment.c.assessed_at))
            == _recency_band_sql(
                literal(reference_day(reference or datetime.now(UTC)), Date)
            )
        )
    )
