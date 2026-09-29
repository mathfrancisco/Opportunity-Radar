"""F48-14: the reclassification touches only companies that are low by research maturity."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine
from scripts.reclassify_company_priority import reclassify_company_priority

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
    reason="database integration is enabled only in the isolated CI database",
)


def _company(
    session: Session, *, priority: str, research_confidence: str, version: int = 1
) -> Company:
    marker = uuid4().hex[:12]
    company = Company(
        canonical_name=f"Reclassify {marker}",
        normalized_name=f"reclassify-{marker}",
        priority=priority,
        research_confidence=research_confidence,
        version=version,
    )
    session.add(company)
    session.flush()
    return company


def _seed(session: Session) -> dict[str, Company]:
    return {
        "maturity": _company(session, priority="low", research_confidence="low"),
        "edited": _company(
            session, priority="low", research_confidence="low", version=2
        ),
        "chosen_low": _company(session, priority="low", research_confidence="normal"),
        "high": _company(session, priority="high", research_confidence="low"),
        "normal": _company(session, priority="normal", research_confidence="low"),
    }


def test_dry_run_reports_and_writes_nothing() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        companies = _seed(session)

        report = reclassify_company_priority(session, dry_run=True)
        for company in companies.values():
            session.refresh(company)

        assert report["dry_run"] is True
        assert report["eligible"] >= 1
        assert report["reclassified"] == 0
        assert companies["maturity"].priority == "low"
        session.rollback()


def test_real_run_skips_user_edited_and_non_maturity_companies() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        companies = _seed(session)

        report = reclassify_company_priority(session, dry_run=False)
        for company in companies.values():
            session.refresh(company)

        assert report["reclassified"] >= 1
        assert companies["maturity"].priority == "normal"
        assert companies["edited"].priority == "low"
        assert companies["chosen_low"].priority == "low"
        assert companies["high"].priority == "high"
        assert companies["normal"].priority == "normal"
        assert companies["maturity"].version == 1
        session.rollback()
