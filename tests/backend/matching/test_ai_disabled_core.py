"""Card F51-12 AC05: with `AI_ENABLED=false` the deterministic core is untouched and no
provider is ever built or called, whatever the worker jobs and the scheduler do.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar import worker
from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
from opportunity_radar.matching import adapters
from opportunity_radar.matching.adapters import build_analysis_adapter
from opportunity_radar.matching.analysis import NullAnalysisAdapter
from opportunity_radar.matching.service import MatchingService
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.ai.providers.base import LLMRequest, LLMResponse
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from tests.backend.dashboard.test_queries import _company, _opportunity
from tests.backend.matching.test_evaluation_queue import _ensure_active_profile

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _CountingProvider:
    name = "fake"

    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        raise AssertionError("no request may leave the process while AI is disabled")


def _core(
    session: Session, opportunity_id: UUID, marker: str, *, owner_sub: str
) -> tuple[object, ...]:
    """Score, verdict, eligibility, text-search hits and canonical content, as stored."""
    assessment = MatchingService(session, owner_sub=owner_sub).evaluate(opportunity_id)
    found = list_opportunity_inbox(
        session, InboxQuery(search=marker), owner_sub=owner_sub
    ).items
    opportunity = session.get(OpportunityModel, opportunity_id)
    assert opportunity is not None
    session.refresh(opportunity)
    return (
        assessment.id,
        assessment.score,
        assessment.verdict,
        assessment.eligibility,
        [item.opportunity_id for item in found],
        (
            opportunity.canonical_title,
            opportunity.description,
            opportunity.role_family,
            opportunity.seniority,
            opportunity.work_mode,
            opportunity.version,
        ),
    )


def test_ai_disabled_preserves_deterministic_core(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _CountingProvider()
    built: list[Settings] = []

    def build_provider(settings: Settings) -> _CountingProvider:
        built.append(settings)
        return provider

    monkeypatch.setattr(adapters, "build_provider", build_provider)
    monkeypatch.setattr(worker, "build_provider", build_provider)
    settings = Settings(  # type: ignore[call-arg,arg-type]
        _env_file=None,
        database_url=os.environ["DATABASE_URL"],
        ai_enabled=False,
        groq_api_key="a-key-that-must-stay-unused",
        worker_analyze_enabled=True,
        worker_suggest_enabled=True,
    )
    engine = create_database_engine(os.environ["DATABASE_URL"])
    marker = f"zq{uuid4().hex[:10]}"
    with Session(engine) as session:
        profile_version_id = _ensure_active_profile(session)
        owner_sub = session.scalar(
            select(CareerProfileModel.owner_sub)
            .join(ProfileVersionModel)
            .where(ProfileVersionModel.id == profile_version_id)
        )
        assert owner_sub is not None
        # Every field is decided by rule, so the row is no candidate for any later test.
        opportunity = _opportunity(
            session,
            _company(session, "normal"),
            title=f"Backend Engineer {marker}",
            published_at=datetime.now(UTC),
            description="Python backend role.",
            role_family="SOFTWARE_ENGINEERING",
        )
        opportunity_id = opportunity.id
        session.commit()
        before = _core(session, opportunity_id, marker, owner_sub=owner_sub)
        assert before[4] == [opportunity_id]
        session.commit()

    adapter = build_analysis_adapter(settings, engine)
    router = worker.build_classification_router(settings, engine)
    assert isinstance(adapter, NullAnalysisAdapter)
    assert router is None

    worker.evaluate_pending(engine)
    worker.analyze_pending(engine, adapter, batch_size=5)
    worker.suggest_fields_pending(engine, router)
    scheduler = worker.build_scheduler(settings)
    assert scheduler.get_job("analyze-pending") is not None
    assert scheduler.get_job("suggest-fields-pending") is not None

    with Session(engine) as session:
        after = _core(session, opportunity_id, marker, owner_sub=owner_sub)

    assert after == before
    assert built == []
    assert provider.requests == []
