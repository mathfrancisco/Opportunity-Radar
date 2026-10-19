"""R55-B5: the shared-row prefilter and short retention need exactly one profile owner."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.prefilter import (
    active_owner_count,
    profile_target_scope,
    single_active_owner,
)
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import (
    CareerProfileModel,
    EmploymentPreferenceModel,
    ProfileVersionModel,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _Owners:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.profile_ids: list[object] = []

    def add_active(self, status: str = "ACTIVE") -> str:
        owner = f"prefilter-owner-{uuid4().hex[:10]}"
        with Session(self.engine) as session:
            profile = CareerProfileModel(version=1, owner_sub=owner)
            session.add(profile)
            session.flush()
            version = ProfileVersionModel(career_profile_id=profile.id, number=1, status=status)
            session.add(version)
            session.flush()
            session.add(
                EmploymentPreferenceModel(
                    profile_version_id=version.id,
                    target_role_families=["SOFTWARE_ENGINEERING"],
                    countries=["BR"],
                )
            )
            session.commit()
            self.profile_ids.append(profile.id)
        return owner

    def cleanup(self) -> None:
        with Session(self.engine) as session:
            for profile_id in self.profile_ids:
                session.execute(
                    text(
                        "DELETE FROM profile.employment_preference WHERE profile_version_id IN "
                        "(SELECT id FROM profile.profile_version WHERE career_profile_id = :p)"
                    ),
                    {"p": profile_id},
                )
                session.execute(
                    text("DELETE FROM profile.profile_version WHERE career_profile_id = :p"),
                    {"p": profile_id},
                )
                session.execute(
                    text("DELETE FROM profile.career_profile WHERE id = :p"), {"p": profile_id}
                )
            session.commit()


@pytest.fixture()
def owners() -> _Owners:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    fixture = _Owners(engine)
    try:
        yield fixture  # type: ignore[misc]
    finally:
        fixture.cleanup()
        engine.dispose()


def test_one_active_owner_keeps_prefilter_and_short_retention_on(owners: _Owners) -> None:
    with Session(owners.engine) as session:
        baseline = active_owner_count(session)
    if baseline:
        pytest.skip("another test left an active profile in this database")
    owner = owners.add_active()

    with Session(owners.engine) as session:
        assert active_owner_count(session) == 1
        assert single_active_owner(session) is True
    families, countries = profile_target_scope(owners.engine, owner)
    assert families == ("SOFTWARE_ENGINEERING",)
    assert countries == ("BR",)


def test_two_active_owners_disable_prefilter_and_short_retention(owners: _Owners) -> None:
    with Session(owners.engine) as session:
        baseline = active_owner_count(session)
    first = owners.add_active()
    owners.add_active()
    owners.add_active(status="DRAFT")  # a draft is not an active profile

    with Session(owners.engine) as session:
        assert active_owner_count(session) == baseline + 2
        assert single_active_owner(session) is False
    assert profile_target_scope(owners.engine, first) == ((), ())
