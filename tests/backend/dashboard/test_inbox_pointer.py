"""Card F50-10: the Inbox reads the pointer table, in one statement, without match_assessment.

The old `_latest_assessments` (DISTINCT ON over the whole history) is kept here as the
reference the new read must agree with.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, literal, select, update
from sqlalchemy.orm import Session

from opportunity_radar.dashboard import queries
from opportunity_radar.dashboard.queries import (
    InboxOrder,
    InboxQuery,
)
from opportunity_radar.dashboard.queries import list_opportunity_inbox as _list_opportunity_inbox
from opportunity_radar.matching import currency
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.models import OpportunityModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.models import CareerProfileModel, ProfileVersionModel
from tests.backend.dashboard.test_queries import (
    TEST_OWNER_SUB,
    _assessment,
    _company,
    _opportunity,
    _profile_version,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)


def list_opportunity_inbox(session: Session, query: InboxQuery):
    return _list_opportunity_inbox(session, query, owner_sub=TEST_OWNER_SUB)


def _legacy_latest_assessments(
    profile_version_id: UUID | None, *, owner_sub: str | None = None
) -> Any:
    """`_latest_assessments` as it was before F50-10, verbatim."""
    current_profile_version_id = (
        literal(profile_version_id)
        if profile_version_id is not None
        else select(ProfileVersionModel.id)
        .join(CareerProfileModel)
        .where(
            CareerProfileModel.owner_sub == owner_sub,
            ProfileVersionModel.status == "ACTIVE",
        )
        .scalar_subquery()
        if owner_sub is not None
        else currency.active_profile_version_id()
    )
    taxonomy = currency.opportunity_taxonomy_versions()
    current = currency.is_current_assessment(
        MatchAssessmentModel.__table__,
        rules_version=RULES_VERSION,
        profile_version_id=current_profile_version_id,
        taxonomy_version=currency.with_taxonomy_fallback(taxonomy.c.taxonomy_version),
    )
    ranked = select(
        MatchAssessmentModel.id.label("assessment_id"),
        MatchAssessmentModel.opportunity_id.label("opportunity_id"),
        MatchAssessmentModel.opportunity_version.label("assessment_opportunity_version"),
        MatchAssessmentModel.profile_version_id.label("assessment_profile_version_id"),
        current_profile_version_id.label("current_profile_version_id"),
        MatchAssessmentModel.verdict.label("verdict"),
        MatchAssessmentModel.eligibility.label("eligibility"),
        MatchAssessmentModel.score.label("score"),
        MatchAssessmentModel.confidence.label("confidence"),
        MatchAssessmentModel.rules_version.label("rules_version"),
        (~current).label("is_stale"),
        MatchAssessmentModel.assessed_at.label("assessed_at"),
    )
    if profile_version_id is not None:
        ranked = ranked.where(MatchAssessmentModel.profile_version_id == profile_version_id)
    ranked = ranked.join(
        OpportunityModel, OpportunityModel.id == MatchAssessmentModel.opportunity_id
    )
    ranked = ranked.outerjoin(
        taxonomy, taxonomy.c.opportunity_id == MatchAssessmentModel.opportunity_id
    )
    if owner_sub is not None:
        ranked = ranked.where(MatchAssessmentModel.owner_sub == owner_sub)
    return (
        ranked.distinct(MatchAssessmentModel.opportunity_id)
        .order_by(
            MatchAssessmentModel.opportunity_id,
            current.desc(),
            MatchAssessmentModel.assessed_at.desc(),
            MatchAssessmentModel.id.desc(),
        )
        .subquery("latest_assessment")
    )


class _Fixture:
    """Six postings, two profile versions: current, stale and unassessed mixed."""

    def __init__(self, session: Session) -> None:
        self.old_profile = _profile_version(session)
        self.active = _profile_version(session)
        session.execute(update(ProfileVersionModel).values(status="ARCHIVED"))
        self.active.status = "ACTIVE"
        session.flush()
        self.company = _company(session, "normal")

        def posting(title: str, published_days_ago: int) -> OpportunityModel:
            return _opportunity(
                session,
                self.company,
                title=title,
                published_at=NOW - timedelta(days=published_days_ago),
            )

        def assess(
            opportunity: OpportunityModel, profile: ProfileVersionModel, score: str, hours: int
        ) -> None:
            _assessment(
                session,
                opportunity,
                profile.id,
                verdict="RECOMMENDED" if float(score) > 50 else "WATCHLIST",
                score=score,
                assessed_at=NOW - timedelta(hours=hours),
            )

        twice = posting("Assessed twice", 1)
        assess(twice, self.active, "30.0000", 5)
        assess(twice, self.active, "80.0000", 1)
        bumped = posting("Bumped", 2)
        assess(bumped, self.active, "60.0000", 2)
        bumped.version = 2
        crossed = posting("Crossed band", 10)
        _assessment(
            session,
            crossed,
            self.active.id,
            verdict="RECOMMENDED",
            score="70.0000",
            assessed_at=NOW - timedelta(days=9),
        )
        old_profile_only = posting("Old profile only", 3)
        assess(old_profile_only, self.old_profile, "55.0000", 3)
        both_profiles = posting("Both profiles", 4)
        assess(both_profiles, self.old_profile, "90.0000", 2)
        assess(both_profiles, self.active, "20.0000", 4)
        posting("Never assessed", 5)
        session.flush()


def _snapshot(session: Session, query: InboxQuery) -> tuple[list[tuple[Any, ...]], int, int]:
    page = list_opportunity_inbox(session, query)
    return (
        [
            (i.opportunity_id, i.assessment_id, i.is_stale, i.score, i.verdict)
            for i in page.items
        ],
        page.total,
        page.off_filter_count,
    )


def test_inbox_on_the_pointer_table_matches_the_old_latest_assessment_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        base = InboxQuery(company_id=fixture.company.id, only_recent=False)
        variants = [
            base,
            replace(base, profile_version_id=fixture.active.id),
            replace(base, profile_version_id=fixture.old_profile.id),
            replace(base, order=InboxOrder.SCORE),
            replace(base, order=InboxOrder.RECENCY, only_assessed=True),
            replace(base, role_families=("UNKNOWN",)),
            replace(base, role_families=("BACKEND",)),
            replace(base, limit=2, offset=2),
            replace(base, minimum_score=50),
        ]
        new = [_snapshot(session, query) for query in variants]
        with monkeypatch.context() as patch:
            patch.setattr(queries, "_latest_assessments", _legacy_latest_assessments)
            old = [_snapshot(session, query) for query in variants]
        assert new == old
        # The fixture is not vacuous: stale and current rows both come back.
        flags = {row[2] for row in new[0][0] if row[1] is not None}
        assert flags == {True, False}
        session.rollback()


def test_latest_assessment_subquery_matches_the_old_one_for_every_reader() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        ids = select(OpportunityModel.id).where(
            OpportunityModel.canonical_company_id == fixture.company.id
        )
        for profile_id in (None, fixture.active.id, fixture.old_profile.id):
            rows = []
            for build in (queries._latest_assessments, _legacy_latest_assessments):
                sub = build(profile_id)
                rows.append(
                    sorted(
                        session.execute(
                            select(*sub.c).where(sub.c.opportunity_id.in_(ids))
                        ).all(),
                        key=lambda row: str(row[1]),
                    )
                )
            assert rows[0] == rows[1], profile_id
            assert rows[0], profile_id
        session.rollback()


def _count_selects(session: Session, query: InboxQuery) -> int:
    statements: list[str] = []

    def record(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
        del conn, cursor, args
        statements.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        list_opportunity_inbox(session, query)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
    return len(statements)


def test_inbox_page_and_totals_come_from_a_single_select() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        base = InboxQuery(company_id=fixture.company.id, only_recent=False)
        assert _count_selects(session, base) == 1
        with_area = replace(base, role_families=("UNKNOWN",))
        assert _count_selects(session, with_area) == 1
        # A filter that hides every row leaves no page row to carry the totals.
        hidden = replace(base, role_families=("BACKEND",))
        page = list_opportunity_inbox(session, hidden)
        assert (page.items, page.total, page.off_filter_count) == ((), 0, 6)
        assert _count_selects(session, hidden) == 2
        session.rollback()


def test_inbox_query_does_not_touch_match_assessment() -> None:
    with Session(create_database_engine(os.environ["DATABASE_URL"])) as session:
        fixture = _Fixture(session)
        # `EXPLAIN` of the very statement the Inbox runs; no timing involved.
        statement, page_position = queries._inbox_statement(
            InboxQuery(company_id=fixture.company.id, role_families=("UNKNOWN",)),
            owner_sub=TEST_OWNER_SUB,
        )
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

        relations: set[str] = set()
        historical_assessment_ranks: list[dict[str, Any]] = []

        def walk(node: dict[str, Any]) -> None:
            if "Relation Name" in node:
                relations.add(node["Relation Name"])
            if node["Node Type"] in {"Sort", "Unique", "WindowAgg"} and "match_assessment" in str(
                node.get("Sort Key", ())
            ):
                historical_assessment_ranks.append(node)
            for child in node.get("Plans", []):
                walk(child)

        walk(plan[0]["Plan"])
        assert "current_assessment" in relations
        # Ownership requires a pointer-to-assessment lookup. It must not revive the old
        # per-posting ranking over the assessment history.
        assert "match_assessment" in relations
        assert historical_assessment_ranks == []
        session.rollback()
