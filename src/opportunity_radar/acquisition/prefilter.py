"""Ingestion prefilter by country (card R55-B5).

The area half of the prefilter reuses the `role-family` classification the run already
makes (`items_target_area` / `items_off_target`). This module adds the country half and the
profile reader for it. Both are conservative: anything unknown is kept, so an on-target
vacancy is never dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Sequence

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.regions import ANY_COUNTRY, resolve_allowed_countries
from opportunity_radar.opportunities.role_family import RoleFamily, classify_role_family
from opportunity_radar.platform.logging import get_logger
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from opportunity_radar.profile.service import ProfileService

logger = get_logger("opportunity_radar.acquisition.prefilter")


def area_off_target(
    title: str | None, departments: Sequence[str], targets: Collection[str]
) -> bool:
    """True only when the title and the department each name an area outside `targets`.

    The combined classification lets a department override the title ("Technical Product
    Manager" in "Engineering" is SOFTWARE_ENGINEERING), so a profile that targets PRODUCT
    would lose it. Dropping needs a known title-only family outside the targets and, when
    the item has departments, a known department family outside the targets too. Unknown on
    either side, or an error, keeps the item.
    """
    if not targets:
        return False
    try:
        title_family = classify_role_family(title=title, departments=()).role_family
        if title_family is RoleFamily.UNKNOWN or title_family.value in targets:
            return False
        if not any(name.strip() for name in departments):
            return True
        department_family = classify_role_family(title=None, departments=departments).role_family
    except Exception:  # noqa: BLE001 - when in doubt, keep
        return False
    return department_family is not RoleFamily.UNKNOWN and department_family.value not in targets


def active_owner_count(session: Session) -> int:
    """How many distinct owners have an ACTIVE profile version."""
    return int(
        session.scalar(
            select(func.count(func.distinct(CareerProfileModel.owner_sub)))
            .select_from(ProfileVersionModel)
            .join(
                CareerProfileModel,
                CareerProfileModel.id == ProfileVersionModel.career_profile_id,
            )
            .where(ProfileVersionModel.status == "ACTIVE")
        )
        or 0
    )


def single_active_owner(session: Session) -> bool:
    """True when at most one owner has an active profile.

    Opportunities and acquisition rows are shared across owners, so dropping or shortening
    by one owner's profile is only safe when no other owner has one. When in doubt (a
    second owner, or the count failing) this is False and the caller keeps everything.
    """
    try:
        owners = active_owner_count(session)
    except Exception as error:  # noqa: BLE001 - when in doubt, keep
        try:
            session.rollback()
        except Exception:  # noqa: BLE001 - best effort
            pass
        logger.warning(
            "off-target prefilter disabled: owner count failed",
            extra={"job": "prefilter", "error": type(error).__name__},
        )
        return False
    if owners > 1:
        logger.info(
            "off-target prefilter disabled: more than one owner has an active profile",
            extra={"job": "prefilter", "active_owners": owners},
        )
        return False
    return True


def location_outside_countries(location_text: str | None, target_countries: Iterable[str]) -> bool:
    """True only when the location names countries and none is a target country.

    An empty target list (profile without countries), a missing or unrecognised location,
    a "Worldwide/Anywhere" location and a region that contains a target country are all
    kept (False). "Remote" without a country resolves to nothing, hence kept.
    """
    targets = {code.strip().upper() for code in target_countries if code.strip()}
    if not targets:
        return False
    named = {code.upper() for code in resolve_allowed_countries(location_text)}
    if not named or ANY_COUNTRY in named:
        return False
    return named.isdisjoint(targets)


def active_profile_target_countries(
    session: Session, owner_sub: str | None = None
) -> Callable[[], tuple[str, ...]]:
    """Read the active profile's countries on demand; empty when none is usable.

    A profile that accepts relocation has no country to rule out, so it yields empty.
    """

    def read() -> tuple[str, ...]:
        try:
            profile = ProfileService(session, owner_sub).get_active()
        except ProfileNotFoundError:
            return ()
        except Exception:  # noqa: BLE001 - a failed read means "no countries": keep
            try:
                session.rollback()
            except Exception:  # noqa: BLE001 - best effort
                pass
            return ()
        preferences = profile.snapshot.preferences
        if preferences.relocation_allowed:
            return ()
        return tuple(preferences.countries)

    return read


def owner_target_scope(
    engine: Engine, owner_sub: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(target_role_families, target_countries)` of the owner's active profile.

    Raises when the profile cannot be read (no active profile included); callers that
    report on it must fail loudly. No multi-owner check: see `profile_target_scope`.
    """
    with Session(engine) as session:
        profile = ProfileService(session, owner_sub).get_active()
    preferences = profile.snapshot.preferences
    countries = () if preferences.relocation_allowed else tuple(preferences.countries)
    return tuple(preferences.target_role_families), countries


def profile_target_scope(
    engine: Engine, owner_sub: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(target_role_families, target_countries)` for the shorter off-target retention.

    Best effort: any failure, and any deployment where more than one owner has an active
    profile (the rows are shared, so one owner's profile must not shorten their life),
    yields `((), ())`, which makes no opportunity off-target. The short retention then
    simply does not apply (never the other way around).
    """
    try:
        with Session(engine) as session:
            if not single_active_owner(session):
                return (), ()
        return owner_target_scope(engine, owner_sub)
    except Exception:  # noqa: BLE001 - retention must not depend on the profile read
        return (), ()
