"""Shared operational-owner resolution for one-shot scripts."""

from __future__ import annotations

from opportunity_radar.platform.config import Settings
from opportunity_radar.profile.service import ProfileService


def operational_owner(settings: Settings) -> str | None:
    return ProfileService.operational_owner(settings.worker_owner_sub)


def require_operational_owner(settings: Settings) -> str:
    owner_sub = operational_owner(settings)
    if owner_sub is None:
        raise ValueError("WORKER_OWNER_SUB is required for owner-scoped profile operations.")
    return owner_sub
