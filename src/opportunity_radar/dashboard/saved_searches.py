"""CRUD and novelty counts for saved Dashboard searches."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.dashboard.queries import (
    InboxOrder,
    InboxQuery,
    InvalidInboxQueryError,
    count_opportunity_inbox,
    count_opportunity_inbox_batch,
)
from opportunity_radar.opportunities.domain import (
    DEFAULT_RECENCY_WINDOW_DAYS,
    NEW_RECENCY_WINDOW_DAYS,
)
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


@dataclass(frozen=True, slots=True)
class SavedSearchSummary:
    saved_search: SavedSearch
    new_count: int | None
    count_error: str | None = None


class SavedSearchNotFoundError(LookupError):
    pass


class InvalidSavedSearchFiltersError(ValueError):
    """A persisted saved search cannot be converted back into an Inbox query."""


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


def validate_saved_search_filters(filters: dict[str, Any]) -> None:
    """Raise InvalidSavedSearchFiltersError unless the filters parse back into an Inbox query."""
    _saved_search_inbox_query(
        SavedSearch(
            id=uuid4(),
            name="",
            term=None,
            filters=filters,
            last_opened_at=None,
            created_at=datetime.now(UTC),
        )
    )


def create_saved_search(
    session: Session,
    *,
    name: str,
    term: str | None,
    filters: dict[str, Any],
    owner_sub: str,
) -> SavedSearch:
    validate_saved_search_filters(filters)
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


def list_saved_search_summaries(
    session: Session, *, owner_sub: str
) -> tuple[SavedSearchSummary, ...]:
    """List an owner's searches in the usual order with each Inbox-equivalent novelty count."""
    saved_searches = list_saved_searches(session, owner_sub=owner_sub)
    parsed: list[tuple[SavedSearch, InboxQuery, bool]] = []
    invalid_ids: set[UUID] = set()
    for saved_search in saved_searches:
        try:
            query, needs_profile_fallback = _saved_search_inbox_query(saved_search)
        except InvalidSavedSearchFiltersError:
            invalid_ids.add(saved_search.id)
            continue
        parsed.append((saved_search, query, needs_profile_fallback))

    fallback_role_families: tuple[str, ...] = ()
    if any(needs_profile_fallback for _, _, needs_profile_fallback in parsed):
        try:
            active = ProfileService(session, owner_sub).get_active()
            fallback_role_families = tuple(active.snapshot.preferences.target_role_families)
        except ProfileNotFoundError:
            pass
    queries = tuple(
        replace(query, role_families=fallback_role_families)
        if needs_profile_fallback
        else query
        for _, query, needs_profile_fallback in parsed
    )
    counts = count_opportunity_inbox_batch(session, queries, owner_sub=owner_sub)
    counts_by_id = {
        saved_search.id: count for (saved_search, _, _), count in zip(parsed, counts, strict=True)
    }
    return tuple(
        SavedSearchSummary(
            saved_search=saved_search,
            new_count=counts_by_id.get(saved_search.id),
            count_error="invalid_filters" if saved_search.id in invalid_ids else None,
        )
        for saved_search in saved_searches
    )


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
    query, needs_profile_fallback = _saved_search_inbox_query(saved_search)
    if needs_profile_fallback:
        try:
            active = ProfileService(session, owner_sub).get_active()
            query = replace(
                query,
                role_families=tuple(active.snapshot.preferences.target_role_families),
            )
        except ProfileNotFoundError:
            pass
    return count_opportunity_inbox(session, query, owner_sub=owner_sub)


def _saved_search_inbox_query(saved_search: SavedSearch) -> tuple[InboxQuery, bool]:
    # D1-1 stopgap: `InboxQuery` now rejects a salary bound without a unit; until the
    # adapter supplies the unit (D1-2) such a saved search is reported as invalid filters.
    try:
        return _read_saved_search_inbox_query(saved_search)
    except InvalidInboxQueryError as error:
        raise InvalidSavedSearchFiltersError(str(error)) from error


def _read_saved_search_inbox_query(saved_search: SavedSearch) -> tuple[InboxQuery, bool]:
    """Read a saved search's filters back as the Inbox query the Inbox page would run.

    Recency rules (single source of truth, mirrors `GET /inbox` and `InboxPage`):
    - `only_recent`: absent/true -> True (the Inbox default); false -> False.
    - `lens`: `novas` -> recency_window_days=14; `abertas` -> open_at_source=True;
      absent or "" -> no effect; any other value is invalid.
    - `recency_window_days`: integer 1-365 (int or digit string); `lens=novas` wins.
    - `open_at_source`, `only_startups`: booleans, same name on the query.
    """
    filters = saved_search.filters
    _validate_saved_search_filter_shapes(filters)
    search_filter = filters.get("search")

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
        "only_recent",
        "recency_window_days",
        "open_at_source",
        "only_startups",
        "lens",
    }
    for key in filters.keys() - known_filter_keys:
        logger.warning("Ignoring unknown saved search filter key %r", key)

    verdicts = _saved_search_string_values(filters.get("verdict", ()), "verdict")
    area_value = filters.get("area", filters.get("role_family", ()))
    role_families = _saved_search_string_values(area_value, "area")
    seniorities = _saved_search_string_values(filters.get("seniority", ()), "seniority")
    source_value = filters.get("source", filters.get("source_definition_id", ()))
    source_ids = _saved_search_string_values(source_value, "source")
    all_areas = filters.get("all_areas") is True or filters.get("all_areas") == "true"
    needs_profile_fallback = not role_families and not all_areas

    applied_value = filters.get("applied")
    applied = (
        applied_value
        if isinstance(applied_value, bool)
        else applied_value == "true"
        if applied_value in ("true", "false")
        else None
    )
    only_recent = filters.get("only_recent") not in (False, "false")
    open_at_source = filters.get("open_at_source") in (True, "true")
    only_startups = filters.get("only_startups") in (True, "true")
    recency_window_days = _saved_search_recency_window(filters.get("recency_window_days"))
    lens = filters.get("lens")
    if lens == "novas":
        recency_window_days = NEW_RECENCY_WINDOW_DAYS
    elif lens == "abertas":
        open_at_source = True
    only_assessed_value = filters.get("only_assessed", False)
    only_assessed = only_assessed_value is True or only_assessed_value == "true"
    published_after_value = filters.get("published_after")
    published_after = _saved_search_datetime(published_after_value)
    minimum_score_value = filters.get("minimum_score")
    salary_min_value = filters.get("salary_min")
    salary_max_value = filters.get("salary_max")
    query = InboxQuery(
        verdicts=verdicts,
        minimum_score=_saved_search_decimal(minimum_score_value),
        company_id=_saved_search_uuid(filters["company_id"]) if filters.get("company_id") else None,
        work_mode=str(filters["work_mode"]) if filters.get("work_mode") else None,
        lifecycle_status=(
            str(filters["lifecycle_status"]) if filters.get("lifecycle_status") else None
        ),
        published_after=published_after,
        created_after=saved_search.last_opened_at,
        only_assessed=only_assessed,
        applied=applied,
        search=saved_search.term or search_filter,
        role_families=role_families,
        seniorities=seniorities,
        allowed_country=(
            str(filters["allowed_country"]) if filters.get("allowed_country") else None
        ),
        salary_min=_saved_search_decimal(salary_min_value),
        salary_max=_saved_search_decimal(salary_max_value),
        source_definition_ids=tuple(_saved_search_uuid(value) for value in source_ids),
        profile_version_id=(
            _saved_search_uuid(filters["profile_version_id"])
            if filters.get("profile_version_id")
            else None
        ),
        only_recent=only_recent,
        recency_window_days=recency_window_days,
        open_at_source=open_at_source,
        only_startups=only_startups,
        order=_saved_search_order(filters.get("order", InboxOrder.PRIORITY.value)),
    )
    return query, needs_profile_fallback


def _saved_search_string_values(value: object, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        return tuple(value)
    raise InvalidSavedSearchFiltersError(f"invalid {name} filter")


def _validate_saved_search_filter_shapes(filters: dict[str, Any]) -> None:
    string_keys = ("search", "work_mode", "lifecycle_status", "allowed_country")
    for key in string_keys:
        value = filters.get(key)
        if value is not None and not isinstance(value, str):
            raise InvalidSavedSearchFiltersError(f"invalid {key} filter")

    lens = filters.get("lens")
    if lens is not None and lens not in ("", "novas", "abertas"):
        raise InvalidSavedSearchFiltersError("invalid lens filter")

    for key in (
        "applied",
        "only_assessed",
        "all_areas",
        "only_recent",
        "open_at_source",
        "only_startups",
    ):
        value = filters.get(key)
        if value is not None and not (
            isinstance(value, bool) or value in ("true", "false")
        ):
            raise InvalidSavedSearchFiltersError(f"invalid {key} filter")


def _saved_search_recency_window(value: object) -> int:
    if value is None or value == "":
        return DEFAULT_RECENCY_WINDOW_DAYS
    if isinstance(value, bool) or not (
        isinstance(value, int) or (isinstance(value, str) and value.isascii() and value.isdigit())
    ):
        raise InvalidSavedSearchFiltersError("invalid recency_window_days filter")
    days = int(value)
    if not 1 <= days <= 365:
        raise InvalidSavedSearchFiltersError("invalid recency_window_days filter")
    return days


def _saved_search_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise InvalidSavedSearchFiltersError("invalid decimal filter")
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise InvalidSavedSearchFiltersError("invalid decimal filter") from error
    if not result.is_finite():
        raise InvalidSavedSearchFiltersError("invalid decimal filter")
    return result


def _saved_search_uuid(value: object) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as error:
        raise InvalidSavedSearchFiltersError("invalid UUID filter") from error


def _saved_search_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidSavedSearchFiltersError("invalid datetime filter")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidSavedSearchFiltersError("invalid datetime filter") from error


def _saved_search_order(value: object) -> InboxOrder:
    try:
        return InboxOrder(str(value))
    except ValueError as error:
        raise InvalidSavedSearchFiltersError("invalid order filter") from error
