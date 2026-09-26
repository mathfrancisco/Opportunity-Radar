"""Saved search CRUD and novelty counts use the dashboard inbox query."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
from opportunity_radar.dashboard.saved_searches import (
    create_saved_search,
    delete_saved_search,
    list_saved_searches,
    new_count,
    open_saved_search,
    rename_saved_search,
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


def _company(session: Session) -> Company:
    marker = uuid4().hex[:12]
    company = Company(
        canonical_name=f"Saved search {marker}",
        normalized_name=f"saved-search-{marker}",
        priority="normal",
    )
    session.add(company)
    session.flush()
    return company


def _opportunity(
    session: Session,
    company: Company,
    *,
    title: str,
    created_at: datetime,
    work_mode: str = "REMOTE",
) -> OpportunityModel:
    opportunity = OpportunityModel(
        fingerprint=uuid4().hex,
        fingerprint_version="v1",
        canonical_title=title,
        normalized_title=title.lower(),
        canonical_company_id=company.id,
        company_name=company.canonical_name,
        work_mode=work_mode,
        seniority="SENIOR",
        contract_type="FULL_TIME",
        lifecycle_status="ACTIVE",
        role_family="UNKNOWN",
        version=1,
        created_at=created_at,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def test_create_list_rename_delete_saved_search() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        saved = create_saved_search(
            session, name="Busca original", term="backend", filters={"work_mode": "REMOTE"}
        )

        listed = list_saved_searches(session)

        assert saved in listed
        assert saved.name == "Busca original"
        assert saved.term == "backend"
        assert saved.filters == {"work_mode": "REMOTE"}

        renamed = rename_saved_search(session, saved.id, name="Busca renomeada")
        assert renamed.name == "Busca renomeada"

        delete_saved_search(session, saved.id)
        assert all(item.id != saved.id for item in list_saved_searches(session))


def test_open_saved_search_updates_last_opened_at() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    reference = datetime.now(UTC) - timedelta(days=1)
    with Session(engine) as session:
        saved = create_saved_search(session, name="Busca", term=None, filters={})
        model = session.get(SavedSearchModel, saved.id)
        assert model is not None
        model.last_opened_at = reference - timedelta(days=1)
        session.flush()

        opened = open_saved_search(session, saved.id)

        assert opened.last_opened_at is not None
        assert opened.last_opened_at > reference - timedelta(days=1)


def test_new_count_uses_same_query_as_inbox() -> None:
    # Real-clock reference, not a fixed distant date: `create_saved_search` commits the
    # session, which also commits these flushed opportunities. A fixed 2040 date here would
    # collide with the coverage-funnel tests' absolute yield window
    # (tests/backend/dashboard/test_coverage_funnel.py), which relies on 2040 being outside
    # the persisted corpus.
    engine = create_database_engine(os.environ["DATABASE_URL"])
    reference = datetime.now(UTC)
    with Session(engine) as session:
        company = _company(session)
        _opportunity(
            session, company, title="Remote saved search fixture", created_at=reference
        )
        _opportunity(
            session,
            company,
            title="Onsite saved search fixture",
            created_at=reference,
            work_mode="ONSITE",
        )
        session.flush()
        saved = create_saved_search(
            session,
            name="Remote roles",
            term=None,
            filters={"company_id": str(company.id), "work_mode": "REMOTE"},
        )

        inbox = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, work_mode="REMOTE")
        )

        assert new_count(session, saved) == inbox.total == 1


def test_new_count_counts_only_opportunities_created_after_last_opened() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    reference = datetime.now(UTC)
    with Session(engine) as session:
        company = _company(session)
        _opportunity(
            session,
            company,
            title="Before saved search opened",
            created_at=reference - timedelta(seconds=1),
        )
        _opportunity(
            session,
            company,
            title="At saved search opened",
            created_at=reference,
        )
        _opportunity(
            session,
            company,
            title="After saved search opened",
            created_at=reference + timedelta(seconds=1),
        )
        session.flush()
        saved = create_saved_search(
            session,
            name="New roles",
            term=None,
            filters={"company_id": str(company.id)},
        )
        model = session.get(SavedSearchModel, saved.id)
        assert model is not None
        model.last_opened_at = reference
        session.flush()
        saved = next(item for item in list_saved_searches(session) if item.id == saved.id)

        assert new_count(session, saved) == 1


def test_unknown_filter_key_is_ignored_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    reference = datetime.now(UTC)
    with Session(engine) as session:
        company = _company(session)
        _opportunity(
            session, company, title="Known saved filter", created_at=reference
        )
        session.flush()
        saved = create_saved_search(
            session,
            name="Old filters",
            term=None,
            filters={
                "company_id": str(company.id),
                "renamed_filter": "legacy-value",
            },
        )

        with caplog.at_level("WARNING"):
            count = new_count(session, saved)

        assert count == 1
        assert "renamed_filter" in caplog.text
