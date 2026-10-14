"""Profile ownership is required for every service read and write."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import EmploymentPreference, ProfileSnapshot
from opportunity_radar.profile.service import ProfileService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _snapshot() -> ProfileSnapshot:
    return ProfileSnapshot(
        skills=(),
        experiences=(),
        projects=(),
        preferences=EmploymentPreference(),
    )


def test_profile_creation_without_an_owner_subject_fails_closed() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session:
            with pytest.raises(Exception, match="owner"):
                ProfileService(session).create_active_version(_snapshot(), 0)
    finally:
        engine.dispose()


def test_active_profile_lookup_is_scoped_when_two_owners_are_active() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_a = f"test-profile-owner-a-{uuid4().hex}"
    owner_b = f"test-profile-owner-b-{uuid4().hex}"
    try:
        with Session(engine) as session:
            active_a = ProfileService(session, owner_a).create_active_version(_snapshot(), 0)
            ProfileService(session, owner_b).create_active_version(_snapshot(), 0)

            assert ProfileService(session, owner_a).get_active().id == active_a.id
    finally:
        engine.dispose()
