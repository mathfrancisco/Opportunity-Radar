"""CRUD and novelty counts for saved Dashboard searches."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.dashboard.queries import InboxOrder, InboxQuery, list_opportunity_inbox
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SavedSearch:
    id: UUID
    name: str
    term: str | None
    filters: dict[str, Any]
    last_opened_at: datetime | None
    created_at: datetime


class SavedSearchNotFoundError(LookupError):
    pass


def _saved_search(model: SavedSearchModel) -> SavedSearch:
    return SavedSearch(
        id=model.id,
        name=model.name,
        term=model.term,
        filters=dict(model.filters),
        last_opened_at=model.last_opened_at,
        created_at=model.created_at,
    )


def _find_saved_search(session: Session, saved_search_id: UUID, owner_sub: str) -> SavedSearchModel:
    saved_search = session.scalar(
        select(SavedSearchModel).where(
            SavedSearchModel.id == saved_search_id, SavedSearchModel.owner_sub == owner_sub
        )
    )
    if saved_search is None:
        raise SavedSearchNotFoundError(str(saved_search_id))
    return saved_search


def create_saved_search(
    session: Session,
    *,
    name: str,
    term: str | None,
    filters: dict[str, Any],
    owner_sub: str,
) -> SavedSearch:
    saved_search = SavedSearchModel(owner_sub=owner_sub, name=name, term=term, filters=filters)
    session.add(saved_search)
    session.flush()
    result = _saved_search(saved_search)
    session.commit()
    return result


def list_saved_searches(session: Session, *, owner_sub: str) -> tuple[SavedSearch, ...]:
    rows = session.scalars(
        select(SavedSearchModel)
        .where(SavedSearchModel.owner_sub == owner_sub)
        .order_by(SavedSearchModel.created_at.desc(), SavedSearchModel.id)
    )
    return tuple(_saved_search(row) for row in rows)


def rename_saved_search(
    session: Session, saved_search_id: UUID, *, name: str, owner_sub: str
) -> SavedSearch:
    saved_search = _find_saved_search(session, saved_search_id, owner_sub)
    saved_search.name = name
    session.flush()
    result = _saved_search(saved_search)
    session.commit()
    return result


def delete_saved_search(session: Session, saved_search_id: UUID, *, owner_sub: str) -> None:
    saved_search = _find_saved_search(session, saved_search_id, owner_sub)
    session.delete(saved_search)
    session.commit()


def open_saved_search(session: Session, saved_search_id: UUID, *, owner_sub: str) -> SavedSearch:
    saved_search = _find_saved_search(session, saved_search_id, owner_sub)
    saved_search.last_opened_at = datetime.now(UTC)
    session.flush()
    result = _saved_search(saved_search)
    session.commit()
    return result


def new_count(session: Session, saved_search: SavedSearch, *, owner_sub: str) -> int:
    filters = saved_search.filters
    known_filter_keys = {
        "verdict",
        "minimum_score",
        "company_id",
        "work_mode",
        "lifecycle_status",
        "published_after",
        "only_assessed",
        "applied",
        "search",
        "area",
        "role_family",
        "all_areas",
        "seniority",
        "allowed_country",
        "salary_min",
        "salary_max",
        "source",
        "source_definition_id",
        "profile_version_id",
        "order",
    }
    for key in filters.keys() - known_filter_keys:
        logger.warning("Ignoring unknown saved search filter key %r", key)

    verdict_value = filters.get("verdict", ())
    verdicts = (
        (verdict_value,)
        if isinstance(verdict_value, str)
        else tuple(verdict_value)
        if isinstance(verdict_value, list)
        else ()
    )
    area_value = filters.get("area", filters.get("role_family", ()))
    role_families = (
        (area_value,)
        if isinstance(area_value, str)
        else tuple(area_value)
        if isinstance(area_value, list)
        else ()
    )
    seniority_value = filters.get("seniority", ())
    seniorities = (
        (seniority_value,)
        if isinstance(seniority_value, str)
        else tuple(seniority_value)
        if isinstance(seniority_value, list)
        else ()
    )
    source_value = filters.get("source", filters.get("source_definition_id", ()))
    source_ids = (
        (source_value,)
        if isinstance(source_value, str)
        else tuple(source_value)
        if isinstance(source_value, list)
        else ()
    )
    all_areas = filters.get("all_areas") is True or filters.get("all_areas") == "true"
    if not role_families and not all_areas:
        try:
            active = ProfileService(session, owner_sub).get_active()
            role_families = tuple(active.snapshot.preferences.target_role_families)
        except ProfileNotFoundError:
            role_families = ()

    applied_value = filters.get("applied")
    applied = (
        applied_value
        if isinstance(applied_value, bool)
        else applied_value == "true"
        if applied_value in ("true", "false")
        else None
    )
    only_assessed_value = filters.get("only_assessed", False)
    only_assessed = only_assessed_value is True or only_assessed_value == "true"
    published_after_value = filters.get("published_after")
    published_after = (
        datetime.fromisoformat(published_after_value.replace("Z", "+00:00"))
        if isinstance(published_after_value, str)
        else None
    )
    minimum_score_value = filters.get("minimum_score")
    salary_min_value = filters.get("salary_min")
    salary_max_value = filters.get("salary_max")
    query = InboxQuery(
        verdicts=verdicts,
        minimum_score=(Decimal(str(minimum_score_value)) if minimum_score_value else None),
        company_id=UUID(str(filters["company_id"])) if filters.get("company_id") else None,
        work_mode=str(filters["work_mode"]) if filters.get("work_mode") else None,
        lifecycle_status=(
            str(filters["lifecycle_status"]) if filters.get("lifecycle_status") else None
        ),
        published_after=published_after,
        created_after=saved_search.last_opened_at,
        only_assessed=only_assessed,
        applied=applied,
        search=saved_search.term or filters.get("search"),
        role_families=role_families,
        seniorities=seniorities,
        allowed_country=(
            str(filters["allowed_country"]) if filters.get("allowed_country") else None
        ),
        salary_min=Decimal(str(salary_min_value)) if salary_min_value else None,
        salary_max=Decimal(str(salary_max_value)) if salary_max_value else None,
        source_definition_ids=tuple(UUID(str(value)) for value in source_ids),
        profile_version_id=(
            UUID(str(filters["profile_version_id"])) if filters.get("profile_version_id") else None
        ),
        order=InboxOrder(str(filters.get("order", InboxOrder.PRIORITY.value))),
        limit=200,
    )
    return list_opportunity_inbox(session, query).total
