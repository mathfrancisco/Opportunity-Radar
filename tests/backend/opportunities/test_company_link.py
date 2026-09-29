"""A proposed source (no CompanySource) still links its jobs to the company it names."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import (
    RawItemModel,
    RawItemPayloadModel,
    SourceDefinitionModel,
    SourceRunModel,
)
from opportunity_radar.companies.models import Company
from opportunity_radar.opportunities.repository import OpportunityRepository, RawItemEvidence
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


def _evidence(session: Session, configuration: dict[str, object]) -> RawItemEvidence | None:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="greenhouse",
        name=f"link {uuid4().hex[:8]}",
        enabled=False,
        configuration=configuration,
        rate_limit_policy={},
        evidence_status="ats_identified",
        company_source_id=None,
    )
    session.add(source)
    session.flush()
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="SCHEDULED",
        status="SUCCEEDED",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    marker = uuid4().hex[:12]
    raw = RawItemModel(
        id=uuid4(),
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=marker,
        identity_key=f"external:{marker}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    raw.payload_record = RawItemPayloadModel(payload={"title": "Probe"})
    session.add(raw)
    session.flush()
    return OpportunityRepository(session).raw_item_evidence(raw.id)


def test_unlinked_source_resolves_company_by_configured_name() -> None:
    marker = uuid4().hex[:8]
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        company = Company(
            canonical_name=f"Link Co {marker}",
            normalized_name=f"link co {marker}",
            priority="normal",
        )
        session.add(company)
        session.flush()
        linked = _evidence(session, {"company_name": f"  LINK CO {marker} "})
        unnamed = _evidence(session, {"board_token": "x"})
        company_id = company.id
        session.rollback()
    assert linked is not None and linked.company_id == company_id
    assert unnamed is not None and unnamed.company_id is None
