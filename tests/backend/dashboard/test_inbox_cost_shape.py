"""Card F50-10: the structure that keeps `/inbox` cheap at 25k postings.

Measured on a copy of the real database, the Inbox spent its time in per-row work the page
never needed: a correlated taxonomy subquery per pointer row, a correlated "first source"
subquery per posting in every window, wide rows sorted by every window, and lookups
(duplicates, startup evidence) run for every posting instead of the page. These tests pin
the shape of the plan and the statement count, not wall-clock time.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from opportunity_radar.dashboard import queries
from opportunity_radar.dashboard.queries import InboxQuery
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.opportunities.repository import posting_group_key
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.presentation.http.dependencies import get_session
from tests.backend.dashboard.test_coverage_funnel import (
    _company,
    _company_source,
    _source_definition,
)
from tests.backend.dashboard.test_coverage_funnel import (
    _opportunity as _opportunity_with_sources,
)
from tests.backend.dashboard.test_inbox_pointer import _Fixture

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

#: What a per-page lookup may read. Anything else under a SubPlan is per-row work.
_PAGE_LOOKUPS = {"duplicate_candidate", "company_startup_evidence"}


def _plan(session: Session, query: InboxQuery) -> dict[str, Any]:
    statement, page_position = queries._inbox_statement(query)
    compiled = (
        statement.order_by(page_position)
        .limit(50)
        .compile(
            dialect=session.get_bind().dialect,
            compile_kwargs={"render_postcompile": True},
        )
    )
    plan = (
        session.connection()
        .exec_driver_sql("EXPLAIN (FORMAT JSON) " + str(compiled), compiled.params)
        .scalar_one()
    )
    root: dict[str, Any] = plan[0]["Plan"]
    return root


def _relations(node: dict[str, Any]) -> set[str]:
    found = {node["Relation Name"]} if "Relation Name" in node else set()
    for child in node.get("Plans", []):
        found |= _relations(child)
    return found


def _subplan_relations(node: dict[str, Any], *, inside_subplan: bool = False) -> set[str]:
    """Relations read by correlated SubPlans (InitPlans run once and are not per-row)."""
    inside = inside_subplan or node.get("Parent Relationship") == "SubPlan"
    found = {node["Relation Name"]} if inside and "Relation Name" in node else set()
    for child in node.get("Plans", []):
        found |= _subplan_relations(child, inside_subplan=inside)
    return found


def _page_sort(node: dict[str, Any]) -> dict[str, Any] | None:
    if node["Node Type"] == "Sort" and any(
        "page_position" in key for key in node.get("Sort Key", [])
    ):
        return node
    for child in node.get("Plans", []):
        found = _page_sort(child)
        if found is not None:
            return found
    return None


@pytest.mark.parametrize("role_families", [(), ("UNKNOWN",)])
def test_inbox_plan_has_no_per_row_taxonomy_or_source_subquery(
    role_families: tuple[str, ...],
) -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        root = _plan(
            session,
            InboxQuery(
                company_id=fixture.company.id, role_families=role_families, only_recent=False
            ),
        )

        # The per-posting taxonomy version and first source are aggregated once and joined:
        # `opportunity_skill` and `source_occurrence` are read by joins, never by a SubPlan.
        assert {"opportunity_skill", "source_occurrence"} <= _relations(root)
        assert _subplan_relations(root) <= _PAGE_LOOKUPS
        session.rollback()


def test_inbox_page_lookups_run_after_the_sort_and_the_limit() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        root = _plan(
            session,
            InboxQuery(
                company_id=fixture.company.id, role_families=("UNKNOWN",), only_recent=False
            ),
        )

        page_sort = _page_sort(root)
        assert page_sort is not None
        # Nothing per-row (duplicates, startup evidence) sits below the sort: those lookups
        # are evaluated for the rows of the page only.
        assert _subplan_relations(page_sort) == set()
        assert _PAGE_LOOKUPS & _subplan_relations(root)
        session.rollback()


def test_the_joined_group_key_is_the_repository_group_key() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        company = _company(session, "group-key")
        sources = tuple(
            _source_definition(session, _company_source(session, company, f"gk{i}"), f"gk{i}")
            for i in range(2)
        )
        shared = _opportunity_with_sources(session, company, sources, tag="shared")
        single = _opportunity_with_sources(session, company, sources[1:], tag="single")
        alone = _opportunity_with_sources(session, company, (), tag="alone")
        nameless = _opportunity_with_sources(session, company, sources[:1], tag="nameless")
        nameless.canonical_company_id = None
        nameless.company_name = "Mixed CASE Co"
        session.flush()
        ids = [shared.id, single.id, alone.id, nameless.id]

        first_sources = queries._first_sources()
        joined = dict(
            session.execute(
                select(
                    OpportunityModel.id,
                    queries._posting_group_key(first_sources.c.first_source),
                )
                .outerjoin(first_sources, first_sources.c.opportunity_id == OpportunityModel.id)
                .where(OpportunityModel.id.in_(ids))
            ).all()
        )
        correlated = dict(
            session.execute(
                select(OpportunityModel.id, posting_group_key()).where(
                    OpportunityModel.id.in_(ids)
                )
            ).all()
        )

        assert joined == correlated
        assert len(set(joined.values())) == 4
        assert joined[alone.id].endswith(f"|id:{alone.id}")
        assert joined[nameless.id].startswith("name:mixed case co|")
        session.rollback()


def _inbox_statements(session: Session, **params: Any) -> list[str]:
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        del conn, cursor, args
        statements.append(statement)

    app = create_app(Settings(database_url=os.environ["DATABASE_URL"]))
    app.dependency_overrides[get_session] = lambda: session
    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        response = TestClient(app).get("/inbox", params=params)
    finally:
        event.remove(engine, "before_cursor_execute", record)
        app.dependency_overrides.pop(get_session)
    assert response.status_code == 200
    return statements


def test_inbox_request_runs_one_statement_for_the_list_and_totals() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        params = {"company_id": str(fixture.company.id), "only_recent": "false", "limit": 20}

        every_area = _inbox_statements(session, all_areas=True, **params)
        assert len(every_area) == 1
        assert "current_assessment" in every_area[0]

        # With the active profile's areas the handler may read the profile first, but the
        # list, its total and the "hidden by area" count are still one statement.
        profile_areas = _inbox_statements(session, **params)
        assert sum("current_assessment" in statement for statement in profile_areas) == 1
        session.rollback()
