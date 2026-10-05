"""Database-backed proof of F48-03: a Remotive item with a naive date becomes an opportunity.

The collected snapshot carries `published_at = "2026-09-29T08:00:00"` (no timezone), the shape
of the 35 Remotive raw items whose normalization used to end `FAILED`. The script clears only
those failures so `normalize_pending` creates the opportunities.
"""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.acquisition.service import COLLECTED_ITEM_V1_KEY
from opportunity_radar.opportunities.models import NormalizationResultModel, OpportunityModel
from opportunity_radar.opportunities.service import NORMALIZER_VERSION, OpportunityService
from opportunity_radar.platform.database import create_database_engine
from scripts import backfill_failed_normalizations

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_TIMEZONE_ERROR = "collected_item_v1 published_at must include a timezone"


def _reset(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE acquisition.source_definition, opportunities.opportunity CASCADE")
        )


def _raw_item(
    session: Session, source: SourceDefinitionModel, run: SourceRunModel, external_id: str
) -> RawItemModel:
    url = f"https://remotive.com/remote-jobs/software-dev/{external_id}"
    snapshot = {
        "version": 1,
        "source_type": "remotive",
        "external_id": external_id,
        "url": url,
        "title": f"Python Engineer {external_id}",
        "company_name": "Acme Remote",
        "location_text": "Worldwide",
        "description": "Build things.",
        "published_at": "2026-09-29T08:00:00",
        "updated_at": None,
        "valid_through": None,
        "parser_version": "remotive-remote-jobs-v2",
        "metadata": {"parser_version": "remotive-remote-jobs-v2"},
    }
    item = RawItemModel(
        id=uuid4(),
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=external_id,
        canonical_url=url,
        identity_key=f"external:{external_id}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={COLLECTED_ITEM_V1_KEY: snapshot},
    )
    item.payload_record = RawItemPayloadModel(payload={"id": external_id})
    session.add(item)
    session.flush()
    return item


def _failed(session: Session, raw_item_id: UUID, code: str, summary: str) -> None:
    session.add(
        NormalizationResultModel(
            raw_item_id=raw_item_id,
            status="FAILED",
            normalizer_version=NORMALIZER_VERSION,
            reasons=[{"code": code}],
            error_summary=summary,
        )
    )


def test_naive_published_at_no_longer_fails_the_item() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    _reset(engine)
    with Session(engine) as session:
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type="remotive",
            name=f"remotive {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        run = SourceRunModel(
            id=uuid4(),
            source_definition_id=source.id,
            execution_trigger="ON_DEMAND",
            status="SUCCEEDED",
        )
        session.add_all([source, run])
        session.commit()
        item = _raw_item(session, source, run, "300001")
        session.commit()

        result = OpportunityService(session).normalize(item.id)

        assert result.status == "SUCCEEDED"
        opportunity = session.scalars(select(OpportunityModel)).one()
        assert opportunity.canonical_title == "Python Engineer 300001"


def test_backfill_dry_run_writes_nothing_and_real_run_reprocesses_only_affected() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    _reset(engine)
    with Session(engine) as session:
        source = SourceDefinitionModel(
            id=uuid4(),
            source_type="remotive",
            name=f"remotive {uuid4().hex[:8]}",
            enabled=True,
            configuration={},
            rate_limit_policy={},
        )
        run = SourceRunModel(
            id=uuid4(),
            source_definition_id=source.id,
            execution_trigger="ON_DEMAND",
            status="SUCCEEDED",
        )
        session.add_all([source, run])
        session.commit()
        affected = _raw_item(session, source, run, "300010")
        other_invalid = _raw_item(session, source, run, "300011")
        expired = _raw_item(session, source, run, "300012")
        _failed(session, affected.id, "INVALID_COLLECTED_ITEM_V1", _TIMEZONE_ERROR)
        _failed(session, other_invalid.id, "INVALID_COLLECTED_ITEM_V1", "title is missing")
        _failed(session, expired.id, "PAYLOAD_EXPIRED_RECOLLECTION_REQUIRED", _TIMEZONE_ERROR)
        session.commit()

        dry = backfill_failed_normalizations.backfill(session, dry_run=True)
        assert dry["affected"] == 1 and dry["deleted"] == 0
        assert [entry["external_id"] for entry in dry["items"]] == ["300010"]
        assert session.scalar(select(func.count(NormalizationResultModel.id))) == 3

        real = backfill_failed_normalizations.backfill(session, dry_run=False)
        assert real["affected"] == 1 and real["deleted"] == 1
        remaining = {
            row.raw_item_id
            for row in session.scalars(select(NormalizationResultModel))
        }
        assert remaining == {other_invalid.id, expired.id}

        # Idempotent: nothing left to clear.
        again = backfill_failed_normalizations.backfill(session, dry_run=False)
        assert again["affected"] == 0 and again["deleted"] == 0

        batch = OpportunityService(session).normalize_pending(limit=10)
        assert batch.succeeded == 1
        opportunity = session.scalars(select(OpportunityModel)).one()
        assert opportunity.canonical_title == "Python Engineer 300010"
