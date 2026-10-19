"""R55-E6 against a real database: recompute refuses cut text, the trim script is race-safe."""

from __future__ import annotations

import os
from collections import Counter

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from opportunity_radar.matching.text import trim_stored_description
from opportunity_radar.opportunities.models import NormalizationResultModel, OpportunityModel
from opportunity_radar.opportunities.service import recompute_from_stored_description
from scripts import trim_stored_descriptions as trim_script
from tests.backend.acquisition.test_delta_presence_resume import _engine, _Fixture
from tests.backend.opportunities.test_normalizer_v7_renormalization import _collect_and_normalize

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_LONG = "Requirements: Python.\n\n" + "The team ships weekly and values clear writing. " * 120
_LONG += "\n\nNice to have: Kubernetes."


def _opportunity(session: Session, fixture: _Fixture) -> OpportunityModel:
    raw_item = _collect_and_normalize(session, fixture)
    opportunity = session.scalar(
        select(OpportunityModel).where(
            OpportunityModel.id.in_(
                select(NormalizationResultModel.opportunity_id).where(
                    NormalizationResultModel.raw_item_id == raw_item.id
                )
            )
        )
    )
    assert opportunity is not None
    return opportunity


def test_recompute_without_the_full_text_is_skipped_for_real_trim_output() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            opportunity = _opportunity(session, fixture)
            trimmed = trim_stored_description(_LONG, 4000)
            assert trimmed is not None and len(trimmed) < len(_LONG)
            opportunity.description = trimmed
            session.commit()
            version = opportunity.version
            skipped: Counter[str] = Counter()

            changed = recompute_from_stored_description(session, opportunity.id, skipped=skipped)
            session.commit()

            session.refresh(opportunity)
            assert changed is False
            assert skipped == {"full_description_required": 1}
            assert opportunity.version == version
            assert not any(s.canonical_name == "kubernetes" for s in opportunity.skills)
        finally:
            fixture.cleanup()


def test_recompute_with_the_full_text_derives_skills_past_the_cut() -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            opportunity = _opportunity(session, fixture)
            opportunity.description = trim_stored_description(_LONG, 4000)
            session.commit()

            changed = recompute_from_stored_description(
                session, opportunity.id, full_description=_LONG
            )
            session.commit()

            session.refresh(opportunity)
            assert changed is True
            assert "kubernetes" in {s.canonical_name for s in opportunity.skills}
        finally:
            fixture.cleanup()


def test_trim_script_trims_without_version_or_updated_at_and_skips_races(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        fixture = _Fixture(session)
        try:
            opportunity = _opportunity(session, fixture)
            opportunity.description = _LONG
            session.commit()
            dry = trim_script.trim_all(session, max_chars=4000, dry_run=True)
            session.refresh(opportunity)
            assert dry["rows"] >= 1 and opportunity.description == _LONG

            real_trim = trim_script.trim_stored_description

            def edit_then_trim(text: str, cap: int) -> str | None:
                # Another writer changes the row between the read and the update.
                with Session(engine) as other:
                    other.execute(
                        update(OpportunityModel)
                        .where(OpportunityModel.id == opportunity.id)
                        .values(description=_LONG + " edited")
                    )
                    other.commit()
                return real_trim(text, cap)

            monkeypatch.setattr(trim_script, "trim_stored_description", edit_then_trim)
            raced = trim_script.trim_all(session, max_chars=4000, dry_run=False)
            session.refresh(opportunity)
            assert raced["skipped_races"] >= 1
            assert opportunity.description == _LONG + " edited"
            version, updated_at = opportunity.version, opportunity.updated_at

            monkeypatch.setattr(trim_script, "trim_stored_description", real_trim)
            done = trim_script.trim_all(session, max_chars=4000, dry_run=False)
            session.refresh(opportunity)
            assert done["skipped_races"] == 0
            assert len(opportunity.description) <= 4000
            assert (opportunity.version, opportunity.updated_at) == (version, updated_at)
            assert trim_script.trim_all(session, max_chars=4000, dry_run=False)["rows"] == 0
        finally:
            fixture.cleanup()
