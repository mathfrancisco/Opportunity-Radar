"""Filters shared by every way of searching the collection.

Card F17-03 (full-text) and card F16-10 (search by meaning) must answer over the same
universe: a filter that only one mode applies would make the gate between them compare
different sets. These conditions only touch `OpportunityModel` (subqueries allowed), so
any query that selects from it can apply them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from opportunity_radar.opportunities.models import OpportunityModel


@dataclass(frozen=True, slots=True)
class OpportunityFilters:
    """Each field narrows the result; an empty or `None` field does not filter."""

    company_id: UUID | None = None
    lifecycle_status: str | None = None
    published_after: datetime | None = None
    work_modes: tuple[str, ...] = ()
    seniorities: tuple[str, ...] = ()


def opportunity_conditions(filters: OpportunityFilters) -> list[Any]:
    """SQL conditions over `OpportunityModel` for the given filters."""
    conditions: list[Any] = []
    if filters.company_id is not None:
        conditions.append(OpportunityModel.canonical_company_id == filters.company_id)
    if filters.lifecycle_status:
        conditions.append(OpportunityModel.lifecycle_status == filters.lifecycle_status)
    if filters.published_after is not None:
        conditions.append(OpportunityModel.published_at >= filters.published_after)
    if filters.work_modes:
        conditions.append(OpportunityModel.work_mode.in_(filters.work_modes))
    if filters.seniorities:
        conditions.append(OpportunityModel.seniority.in_(filters.seniorities))
    return conditions


__all__ = ["OpportunityFilters", "opportunity_conditions"]
