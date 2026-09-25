"""Seniority, salary range and source filters for the Inbox (card F17-03 gap-close).

One DB integration test per filter, plus a no-duplicate test for source: an opportunity
with several occurrences from a matching source must appear once, not once per occurrence
(SPEC 37, "Contrato de consulta": "fonte filtra ocorrências, não duplica a oportunidade").
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
from opportunity_radar.opportunities.models import (
    OpportunityCompensationModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.platform.database import create_database_engine

from .test_queries import _company, _opportunity

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def _session() -> Session:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    return Session(engine)


def _source(session: Session, *, name: str | None = None) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="greenhouse",
        name=name or f"search-filters {uuid4().hex[:8]}",
        enabled=True,
        configuration={},
        rate_limit_policy={},
        evidence_status="confirmed",
    )
    session.add(source)
    session.flush()
    return source


def _run(session: Session, source: SourceDefinitionModel) -> SourceRunModel:
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="SCHEDULED",
        status="SUCCEEDED",
        started_at=NOW,
        finished_at=NOW,
    )
    session.add(run)
    session.flush()
    return run


def _occurrence(
    session: Session,
    opportunity: OpportunityModel,
    source: SourceDefinitionModel,
) -> SourceOccurrenceModel:
    marker = uuid4().hex[:12]
    run = _run(session, source)
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=marker,
        identity_key=f"external:{marker}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    raw_item.payload_record = RawItemPayloadModel(payload={"title": "Probe"})
    session.add(raw_item)
    session.flush()
    occurrence = SourceOccurrenceModel(
        opportunity_id=opportunity.id,
        raw_item_id=raw_item.id,
        source_definition_id=source.id,
        external_id=marker,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(occurrence)
    session.flush()
    return occurrence


def _compensation(
    session: Session,
    opportunity: OpportunityModel,
    occurrence: SourceOccurrenceModel,
    *,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
) -> None:
    session.add(
        OpportunityCompensationModel(
            opportunity_id=opportunity.id,
            source_occurrence_id=occurrence.id,
            raw_item_id=occurrence.raw_item_id,
            amount_min=amount_min,
            amount_max=amount_max,
            normalizer_version="v3",
        )
    )
    session.flush()


def test_seniority_filter_narrows_the_inbox() -> None:
    with _session() as session:
        company = _company(session, "normal")
        senior = _opportunity(
            session, company, title="Senior Role", published_at=NOW, seniority="SENIOR"
        )
        _opportunity(
            session, company, title="Junior Role", published_at=NOW, seniority="JUNIOR"
        )
        session.commit()

        filtered = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, seniorities=("SENIOR",))
        )
        assert [item.opportunity_id for item in filtered.items] == [senior.id]


def test_salary_range_filter_matches_overlapping_compensation() -> None:
    with _session() as session:
        company = _company(session, "normal")
        source = _source(session)
        in_range = _opportunity(session, company, title="In Range", published_at=NOW)
        out_of_range = _opportunity(session, company, title="Out of Range", published_at=NOW)
        _compensation(
            session,
            in_range,
            _occurrence(session, in_range, source),
            amount_min=Decimal("8000"),
            amount_max=Decimal("12000"),
        )
        _compensation(
            session,
            out_of_range,
            _occurrence(session, out_of_range, source),
            amount_min=Decimal("2000"),
            amount_max=Decimal("3000"),
        )
        session.commit()

        filtered = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                salary_min=Decimal("6000"),
                salary_max=Decimal("15000"),
            ),
        )
        assert [item.opportunity_id for item in filtered.items] == [in_range.id]


def test_source_filter_matches_occurrences() -> None:
    with _session() as session:
        company = _company(session, "normal")
        matching_source = _source(session)
        other_source = _source(session)
        matching = _opportunity(session, company, title="From Source", published_at=NOW)
        not_matching = _opportunity(session, company, title="Other Source", published_at=NOW)
        _occurrence(session, matching, matching_source)
        _occurrence(session, not_matching, other_source)
        session.commit()

        filtered = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id, source_definition_ids=(matching_source.id,)
            ),
        )
        assert [item.opportunity_id for item in filtered.items] == [matching.id]


def test_source_filter_does_not_duplicate_a_multi_source_opportunity() -> None:
    with _session() as session:
        company = _company(session, "normal")
        source_a = _source(session)
        source_b = _source(session)
        opportunity = _opportunity(
            session, company, title="Multi Source", published_at=NOW
        )
        _occurrence(session, opportunity, source_a)
        _occurrence(session, opportunity, source_b)
        session.commit()

        filtered = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                source_definition_ids=(source_a.id, source_b.id),
            ),
        )
        assert [item.opportunity_id for item in filtered.items] == [opportunity.id]
        assert filtered.total == 1
