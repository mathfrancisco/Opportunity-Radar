"""Full-text search over the Inbox (card F17-03, SPEC 37 §10).

One test per acceptance criterion. All exercise `search_document`/`websearch_to_tsquery`
in Postgres, so they run only against the isolated CI database, like the rest of
`tests/backend/dashboard/test_queries.py`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
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


def test_term_present_only_in_description_is_found() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Software Engineer",
            published_at=NOW,
            description="Requires strong Kubernetes experience running production clusters.",
        )
        _opportunity(session, company, title="Unrelated Analyst", published_at=NOW)
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="Kubernetes")
        )
        assert [item.opportunity_id for item in found.items] == [target.id]


def test_search_ignores_accent_and_matches_plural_from_singular() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Engenheira de Dados Júnior",
            published_at=NOW,
            description="Vaga para atuação remota, foco em pipelines de dados.",
        )
        session.commit()

        no_accent = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="Junior")
        )
        assert [item.opportunity_id for item in no_accent.items] == [target.id]

        singular_from_plural = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="pipeline")
        )
        assert [item.opportunity_id for item in singular_from_plural.items] == [target.id]


def test_domain_synonyms_widen_the_search() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Desenvolvedor Backend Sênior",
            published_at=NOW,
        )
        session.commit()

        by_synonym = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="developer senior")
        )
        assert [item.opportunity_id for item in by_synonym.items] == [target.id]


def test_filters_combine_with_the_search_term() -> None:
    with _session() as session:
        company = _company(session, "normal")
        matching = _opportunity(
            session,
            company,
            title="Data Engineer",
            published_at=NOW,
            work_mode="REMOTE",
            description="Own the pipeline that feeds analytics dashboards.",
        )
        _opportunity(
            session,
            company,
            title="Data Engineer",
            published_at=NOW,
            work_mode="ONSITE",
            description="Own the pipeline that feeds analytics dashboards.",
        )
        session.commit()

        combined = list_opportunity_inbox(
            session,
            InboxQuery(company_id=company.id, search="pipeline", work_mode="REMOTE"),
        )
        assert [item.opportunity_id for item in combined.items] == [matching.id]


def test_title_match_ranks_above_description_only_match() -> None:
    with _session() as session:
        company = _company(session, "normal")
        title_match = _opportunity(
            session, company, title="Kubernetes Platform Engineer", published_at=NOW
        )
        description_match = _opportunity(
            session,
            company,
            title="Backend Engineer",
            published_at=NOW,
            description="Some Kubernetes exposure is a plus, not required.",
        )
        session.commit()

        ranked = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="Kubernetes")
        )
        assert [item.opportunity_id for item in ranked.items] == [
            title_match.id,
            description_match.id,
        ]
