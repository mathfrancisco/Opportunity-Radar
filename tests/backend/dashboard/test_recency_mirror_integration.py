"""F48-16: the SQL recency rule mirrors `recency_decision`, and the "Abertas na fonte"
lens follows the last complete run of each occurrence's source."""

from __future__ import annotations

import itertools
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
from opportunity_radar.opportunities.domain import (
    DEFAULT_RECENCY_WINDOW_DAYS,
    NEW_RECENCY_WINDOW_DAYS,
    recency_basis_of,
    recency_decision,
)
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def _opportunity(marker: str, **changes: object) -> OpportunityModel:
    values: dict[str, object] = {
        "id": uuid4(),
        "fingerprint": uuid4().hex + uuid4().hex,
        "fingerprint_version": "v1",
        "canonical_title": f"Role {marker}",
        "normalized_title": f"role {marker}",
        "work_mode": "UNKNOWN",
        "seniority": "UNKNOWN",
        "contract_type": "UNKNOWN",
        "lifecycle_status": "ACTIVE",
        "version": 1,
    }
    values.update(changes)
    return OpportunityModel(**values)  # type: ignore[arg-type]


def test_sql_condition_matches_recency_decision_over_an_input_grid() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    marker = uuid4().hex[:10]
    ages = (None, 5, 20, 45)
    program_flags = (False, True)
    deadlines = (None, 3, -3)
    windows = (DEFAULT_RECENCY_WINDOW_DAYS, NEW_RECENCY_WINDOW_DAYS)
    expected: dict[tuple[object, int], bool] = {}
    rows: list[OpportunityModel] = []
    for published, updated, seen, program, deadline in itertools.product(
        ages, ages, (1, 20, 45), program_flags, deadlines
    ):
        published_at = NOW - timedelta(days=published) if published is not None else None
        updated_at = NOW - timedelta(days=updated) if updated is not None else None
        first_seen = NOW - timedelta(days=seen)
        valid_through = NOW + timedelta(days=deadline) if deadline is not None else None
        row = _opportunity(
            marker,
            published_at=published_at,
            source_updated_at=updated_at,
            first_seen_at=first_seen,
            recency_basis=recency_basis_of(
                published_at=published_at, source_updated_at=updated_at
            ).value,
            recency_exempt_program=program,
            valid_through=valid_through,
        )
        rows.append(row)
        for window in windows:
            expected[(row.id, window)] = recency_decision(
                published_at=published_at,
                source_updated_at=updated_at,
                first_seen_at=first_seen,
                valid_through=valid_through,
                recency_exempt_program=program,
                now=NOW,
                window_days=window,
            ).visible

    with Session(engine) as session:
        session.add_all(rows)
        session.commit()
        try:
            for window in windows:
                page = list_opportunity_inbox(
                    session,
                    InboxQuery(
                        search=marker,
                        only_recent=True,
                        recency_window_days=window,
                        now=NOW,
                        limit=500,
                    ),
                )
                assert page.total == sum(expected[(row.id, window)] for row in rows)
                sql_visible = {item.opportunity_id for item in page.items}
                for row in rows:
                    assert (row.id in sql_visible) is expected[(row.id, window)]
        finally:
            session.execute(
                delete(OpportunityModel).where(OpportunityModel.id.in_([r.id for r in rows]))
            )
            session.commit()


def test_open_at_source_lens_uses_last_complete_run_and_ignores_age() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    marker = uuid4().hex[:10]
    with Session(engine) as session:
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type="manual",
            name=f"lens {marker}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        session.add(source)
        session.commit()
        base = datetime.now(UTC)

        def run(hours_ago: float, *, complete: bool) -> SourceRunModel:
            return SourceRunModel(
                id=uuid4(),
                source_definition_id=source.id,
                execution_trigger="SCHEDULED",
                status="SUCCEEDED" if complete else "PARTIAL",
                started_at=base - timedelta(hours=hours_ago),
                complete=complete,
            )

        older = run(2, complete=True)
        latest_complete = run(1, complete=True)
        partial_after = run(0.2, complete=False)
        session.add_all([older, latest_complete, partial_after])
        session.commit()

        old_but_open = _opportunity(marker, published_at=base - timedelta(days=200))
        gone = _opportunity(marker, published_at=base - timedelta(days=1))
        only_in_partial = _opportunity(marker, published_at=base - timedelta(days=1))
        opportunities = [old_but_open, gone, only_in_partial]
        session.add_all(opportunities)
        session.flush()
        raw_ids = []
        for opportunity, source_run in (
            (old_but_open, latest_complete),
            (gone, older),
            (only_in_partial, partial_after),
        ):
            raw = RawItemModel(
                id=uuid4(),
                source_run_id=source_run.id,
                source_definition_id=source.id,
                external_id=f"ext-{uuid4().hex[:8]}",
                identity_key=f"external:{uuid4().hex[:8]}",
                payload_hash=uuid4().hex + uuid4().hex,
                item_metadata={},
            )
            session.add(raw)
            session.flush()
            raw_ids.append(raw.id)
            session.add(
                SourceOccurrenceModel(
                    id=uuid4(),
                    opportunity_id=opportunity.id,
                    raw_item_id=raw.id,
                    source_definition_id=source.id,
                    external_id=raw.external_id,
                    first_seen_at=source_run.started_at,
                    last_seen_at=source_run.started_at,
                    last_seen_run_id=source_run.id,
                )
            )
        session.commit()
        try:
            lens = list_opportunity_inbox(
                session, InboxQuery(search=marker, open_at_source=True, only_recent=True)
            )
            assert {item.opportunity_id for item in lens.items} == {old_but_open.id}
            default = list_opportunity_inbox(session, InboxQuery(search=marker, only_recent=True))
            assert old_but_open.id not in {item.opportunity_id for item in default.items}
        finally:
            session.execute(
                delete(SourceOccurrenceModel).where(
                    SourceOccurrenceModel.source_definition_id == source.id
                )
            )
            session.execute(
                delete(OpportunityModel).where(
                    OpportunityModel.id.in_([item.id for item in opportunities])
                )
            )
            session.execute(delete(RawItemModel).where(RawItemModel.id.in_(raw_ids)))
            session.execute(
                delete(SourceRunModel).where(SourceRunModel.source_definition_id == source.id)
            )
            session.execute(
                delete(SourceDefinitionModel).where(SourceDefinitionModel.id == source.id)
            )
            session.commit()
