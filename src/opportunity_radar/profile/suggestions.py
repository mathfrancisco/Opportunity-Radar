"""R55-D4: "not for me" marks become suggested profile adjustments, never automatic ones.

The owner marks a posting as not relevant and says why (area, seniority, location, company).
Repeated marks pointing at the same profile preference or company become a suggestion the
owner can read on the Profile page and apply to the form. Nothing here writes: a suggestion
is only a value the owner decides to save as a new profile version.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.models import OpportunityModel, RelevanceMarkModel
from opportunity_radar.opportunities.regions import ANY_COUNTRY
from opportunity_radar.profile.domain import EmploymentPreference

#: Distinct postings with the same cause before the radar suggests anything: one mark is a
#: judgement about one posting, two are a pattern.
MIN_MARKS = 2
_REASONS = frozenset({"AREA", "SENIORITY", "LOCATION", "COMPANY"})


class SuggestionKind(StrEnum):
    REMOVE_ROLE_FAMILY = "REMOVE_ROLE_FAMILY"
    REMOVE_SENIORITY = "REMOVE_SENIORITY"
    REMOVE_COUNTRY = "REMOVE_COUNTRY"
    #: Company priority lives on the company, not in the profile: informational only.
    LOWER_COMPANY_PRIORITY = "LOWER_COMPANY_PRIORITY"


@dataclass(frozen=True, slots=True)
class MarkedPosting:
    """What the current "not for me" mark of one posting says, and about which posting."""

    reason: str
    role_family: str | None
    seniority: str | None
    allowed_countries: tuple[str, ...]
    company_name: str | None


@dataclass(frozen=True, slots=True)
class ProfileSuggestion:
    kind: SuggestionKind
    value: str
    marks: int


def build_suggestions(
    preferences: EmploymentPreference, postings: Iterable[MarkedPosting]
) -> list[ProfileSuggestion]:
    """Suggest removing a preference (or lowering a company) that repeated marks contradict.

    A suggestion exists only for something the profile currently states: an area the profile
    does not target, or a level it does not accept, is already out and needs no advice.
    """
    counts: Counter[tuple[SuggestionKind, str]] = Counter()
    targeted = {item.upper() for item in preferences.target_role_families}
    levels = {item.upper() for item in preferences.accepted_seniorities}
    countries = {item.upper() for item in preferences.countries}
    company_names: dict[str, str] = {}
    for posting in postings:
        if posting.reason == "AREA":
            family = (posting.role_family or "").upper()
            if family in targeted:
                counts[(SuggestionKind.REMOVE_ROLE_FAMILY, family)] += 1
        elif posting.reason == "SENIORITY":
            level = (posting.seniority or "").upper()
            if level in levels and level != "UNKNOWN":
                counts[(SuggestionKind.REMOVE_SENIORITY, level)] += 1
        elif posting.reason == "LOCATION":
            # A multi-country posting says nothing about one country: it counts only when
            # exactly one of the profile's countries is among those it allows.
            matched = {
                item.upper() for item in posting.allowed_countries
            } & (countries - {ANY_COUNTRY.upper()})
            if len(matched) == 1:
                counts[(SuggestionKind.REMOVE_COUNTRY, next(iter(matched)))] += 1
        elif posting.reason == "COMPANY":
            name = (posting.company_name or "").strip()
            if name:
                key = name.casefold()
                company_names.setdefault(key, name)
                counts[(SuggestionKind.LOWER_COMPANY_PRIORITY, key)] += 1
    suggestions = [
        ProfileSuggestion(
            kind=kind,
            value=company_names[value] if kind is SuggestionKind.LOWER_COMPANY_PRIORITY else value,
            marks=marks,
        )
        for (kind, value), marks in counts.items()
        if marks >= MIN_MARKS
    ]
    return sorted(suggestions, key=lambda item: (-item.marks, item.kind.value, item.value))


def current_negative_marks(session: Session, owner_sub: str) -> list[MarkedPosting]:
    """The owner's latest mark of each posting, when that mark is a reasoned "not for me"."""
    latest = (
        select(RelevanceMarkModel)
        .where(RelevanceMarkModel.owner_sub == owner_sub)
        .distinct(RelevanceMarkModel.opportunity_id)
        .order_by(
            RelevanceMarkModel.opportunity_id,
            RelevanceMarkModel.marked_at.desc(),
            RelevanceMarkModel.id.desc(),
        )
        .subquery()
    )
    rows = session.execute(
        select(
            latest.c.reason,
            OpportunityModel.role_family,
            OpportunityModel.seniority,
            OpportunityModel.allowed_countries,
            OpportunityModel.company_name,
        )
        .join(OpportunityModel, OpportunityModel.id == latest.c.opportunity_id)
        .where(latest.c.relevant.is_(False), latest.c.reason.in_(_REASONS))
    )
    return [
        MarkedPosting(
            reason=reason,
            role_family=role_family,
            seniority=seniority,
            allowed_countries=tuple(countries or ()),
            company_name=company_name,
        )
        for reason, role_family, seniority, countries, company_name in rows
    ]
