"""Card F51-12: what the automatic queue filters keep out, and what an analysis survives."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from test_analysis_persistence import _completed, _seed_assessment, _StubAdapter

from opportunity_radar.matching.analysis import AnalysisStatus
from opportunity_radar.matching.service import (
    DEFAULT_ANALYSIS_VERDICTS,
    MatchingService,
    is_reused_analysis,
)
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _queued(session: Session) -> set[object]:
    return set(
        MatchingService(session).pending_analysis_ids(
            limit=1_000_000,
            eligible_verdicts=DEFAULT_ANALYSIS_VERDICTS,
            now=datetime.now(UTC) + timedelta(seconds=1),
        )
    )


def test_explicit_analysis_bypasses_only_automatic_queue_filters() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        excluded: dict[str, object] = {}
        for reason in ("closed", "short_description", "verdict"):
            repository, record = _seed_assessment(session)
            if reason == "verdict":
                # Assessments are immutable: a LOW_MATCH one is a new assessment.
                record = replace(
                    record, input_hash=uuid4().hex + uuid4().hex, verdict="LOW_MATCH"
                )
                repository.add(record, [])
            assessment = repository.get_existing(input_hash=record.input_hash)
            assert assessment is not None
            opportunity = session.get(OpportunityModel, assessment.opportunity_id)
            assert opportunity is not None
            opportunity.description = "x" * 500
            if reason == "closed":
                opportunity.lifecycle_status = "CLOSED"
            elif reason == "short_description":
                opportunity.description = "short"
            session.commit()
            excluded[reason] = assessment.id

        # None of them is in the automatic queue...
        assert _queued(session).isdisjoint(excluded.values())

        # ...and an explicit request for each still reaches the provider.
        for assessment_id in excluded.values():
            adapter = _StubAdapter(_completed())
            analysis = asyncio.run(
                MatchingService(session).analyze(assessment_id, adapter)  # type: ignore[arg-type]
            )
            assert adapter.calls == 1
            assert analysis.status == AnalysisStatus.AI_COMPLETED.value


def test_a_new_rules_version_reuses_the_completed_analysis_without_a_provider_call() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        repository, record = _seed_assessment(session)
        first = repository.get_existing(input_hash=record.input_hash)
        assert first is not None
        original = asyncio.run(
            MatchingService(session).analyze(first.id, _StubAdapter(_completed()))
        )
        # Same posting, profile, verdict and content; only the rules and taxonomy moved.
        reassessed = replace(
            record,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version="matching-v2",
            taxonomy_version="skills-v2",
        )
        repository.add(reassessed, [])
        session.commit()
        second = repository.get_existing(input_hash=reassessed.input_hash)
        assert second is not None
        second_id, original_id = second.id, original.id

        adapter = _StubAdapter(_completed())
        reused = asyncio.run(MatchingService(session).analyze(second_id, adapter))

        assert adapter.calls == 0
        assert reused.assessment_id == second_id
        assert reused.id != original_id
        assert reused.cache_key == original.cache_key
        assert is_reused_analysis(reused)
