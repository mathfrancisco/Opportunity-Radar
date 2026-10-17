"""Ingestion prefilter by country (card R55-B5).

The area half of the prefilter reuses the `role-family` classification the run already
makes (`items_target_area` / `items_off_target`). This module adds the country half and the
profile reader for it. Both are conservative: anything unknown is kept, so an on-target
vacancy is never dropped.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from opportunity_radar.opportunities.regions import ANY_COUNTRY, resolve_allowed_countries
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService


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
        preferences = profile.snapshot.preferences
        if preferences.relocation_allowed:
            return ()
        return tuple(preferences.countries)

    return read


def profile_target_scope(
    engine: Engine, owner_sub: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(target_role_families, target_countries)` of the active profile, for retention.

    Best effort: any failure yields `((), ())`, which makes no opportunity off-target, so
    the shorter retention simply does not apply (never the other way around).
    """
    try:
        with Session(engine) as session:
            profile = ProfileService(session, owner_sub).get_active()
    except Exception:  # noqa: BLE001 - retention must not depend on the profile read
        return (), ()
    preferences = profile.snapshot.preferences
    countries = () if preferences.relocation_allowed else tuple(preferences.countries)
    return tuple(preferences.target_role_families), countries
