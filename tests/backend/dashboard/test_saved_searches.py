"""Saved search CRUD and novelty counts use the dashboard inbox query."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel, SourceRunModel
from opportunity_radar.companies.models import Company
from opportunity_radar.dashboard import saved_searches as saved_search_service
from opportunity_radar.dashboard.models import SavedSearchModel
from opportunity_radar.dashboard.queries import InboxQuery, list_opportunity_inbox
from opportunity_radar.dashboard.saved_searches import (
    InvalidSavedSearchFiltersError,
    SavedSearchNotFoundError,
    create_saved_search,
    delete_saved_search,
    list_saved_search_summaries,
    list_saved_searches,
    new_count,
    open_saved_search,
    rename_saved_search,
)
from opportunity_radar.matching.models import MatchAssessmentModel
from opportunity_radar.matching.service import RULES_VERSION
from opportunity_radar.opportunities.domain import SKILL_TAXONOMY_VERSION, CompensationPeriod
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import EmploymentPreference, ProfileSnapshot
from opportunity_radar.profile.service import ProfileService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

OWNER_A = "user-saved-search-a"
OWNER_B = "user-saved-search-b"


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
    role_family: str = "UNKNOWN",
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
        role_family=role_family,
        version=1,
        created_at=created_at,
    )
    session.add(opportunity)
    session.flush()
    return opportunity


def _posting_occurrence(
    session: Session, opportunity: OpportunityModel, source: SourceDefinitionModel
) -> None:
    """Give sibling opportunities the same first source for Inbox group deduplication."""
    run = SourceRunModel(
        source_definition_id=source.id,
        execution_trigger="ON_DEMAND",
        status="SUCCEEDED",
    )
    session.add(run)
    session.flush()
    marker = uuid4().hex
    raw_item = RawItemModel(
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=marker,
        identity_key=f"external:{marker}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    session.add(raw_item)
    session.flush()
    session.add(
        SourceOccurrenceModel(
            opportunity_id=opportunity.id,
            raw_item_id=raw_item.id,
            source_definition_id=source.id,
            external_id=marker,
            first_seen_at=opportunity.created_at,
            last_seen_at=opportunity.created_at,
        )
    )
    session.flush()


def _assessment(
    session: Session,
    opportunity: OpportunityModel,
    *,
    owner_sub: str,
    profile_version_id: UUID,
    verdict: str,
) -> None:
    session.add(
        MatchAssessmentModel(
            owner_sub=owner_sub,
            opportunity_id=opportunity.id,
            opportunity_version=opportunity.version,
            profile_version_id=profile_version_id,
            input_hash=uuid4().hex + uuid4().hex,
            rules_version=RULES_VERSION,
            taxonomy_version=SKILL_TAXONOMY_VERSION,
            opportunity_snapshot={"work_mode": opportunity.work_mode},
            profile_snapshot={"skills": []},
            eligibility="ELIGIBLE",
            eligibility_details=[],
            verdict=verdict,
            score=Decimal("75"),
            confidence=Decimal("0.9"),
            assessed_at=datetime.now(UTC),
        )
    )
    session.flush()


def test_create_list_rename_delete_saved_search() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        saved = create_saved_search(
            session,
            name="Busca original",
            term="backend",
            filters={"work_mode": "REMOTE"},
            owner_sub=OWNER_A,
        )

        listed = list_saved_searches(session, owner_sub=OWNER_A)

        assert saved in listed
        assert saved.name == "Busca original"
        assert saved.term == "backend"
        assert saved.filters == {"work_mode": "REMOTE"}

        renamed = rename_saved_search(session, saved.id, name="Busca renomeada", owner_sub=OWNER_A)
        assert renamed.name == "Busca renomeada"

        delete_saved_search(session, saved.id, owner_sub=OWNER_A)
        assert all(item.id != saved.id for item in list_saved_searches(session, owner_sub=OWNER_A))


@pytest.mark.parametrize(
    "filters",
    [
        {"order": 42},
        {"salary_min": "abc"},
        {"seniority": 5},
        {"company_id": "not-a-uuid"},
        {"published_after": "ontem"},
        {"applied": "talvez"},
    ],
)
def test_create_saved_search_rejects_invalid_filters(filters: dict[str, object]) -> None:
    owner_sub = f"test-f4-{uuid4().hex}"
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        with pytest.raises(InvalidSavedSearchFiltersError):
            create_saved_search(
                session, name="x", term=None, filters=filters, owner_sub=owner_sub
            )

        stored = session.scalar(
            select(func.count())
            .select_from(SavedSearchModel)
            .where(SavedSearchModel.owner_sub == owner_sub)
        )
        assert stored == 0


def test_open_saved_search_updates_last_opened_at() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    reference = datetime.now(UTC) - timedelta(days=1)
    with Session(engine) as session:
        saved = create_saved_search(
            session, name="Busca", term=None, filters={}, owner_sub=OWNER_A
        )
        model = session.get(SavedSearchModel, saved.id)
        assert model is not None
        model.last_opened_at = reference - timedelta(days=1)
        session.flush()

        opened = open_saved_search(session, saved.id, owner_sub=OWNER_A)

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
            # `all_areas: True` is required so `new_count` matches `InboxQuery` below,
            # which applies no role-family filter at all: without it, `new_count` falls
            # back to the *active profile's* `target_role_families` (F17-06) — a row this
            # shared, never-truncated integration database has no fixture for, so whatever
            # another test (e.g. test_profile_preservation.py) last activated and left
            # behind silently narrows this query and drops both fixtures (F20 sanity pass).
            filters={
                "company_id": str(company.id),
                "work_mode": "REMOTE",
                "all_areas": True,
            },
            owner_sub=OWNER_A,
        )

        inbox = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, work_mode="REMOTE"), owner_sub=OWNER_A
        )

        assert new_count(session, saved, owner_sub=OWNER_A) == inbox.total == 1


def test_new_count_threads_each_authenticated_owner_to_the_inbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owners: list[str] = []

    def count_for_owner(*_: object, owner_sub: str) -> int:
        owners.append(owner_sub)
        return 1

    monkeypatch.setattr(saved_search_service, "count_opportunity_inbox", count_for_owner)
    with Session(engine) as session:
        saved_a = create_saved_search(
            session, name="A", term=None, filters={"all_areas": True}, owner_sub=OWNER_A
        )
        saved_b = create_saved_search(
            session, name="B", term=None, filters={"all_areas": True}, owner_sub=OWNER_B
        )

        assert new_count(session, saved_a, owner_sub=OWNER_A) == 1
        assert new_count(session, saved_b, owner_sub=OWNER_B) == 1
        assert owners == [OWNER_A, OWNER_B]


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
            # Without `all_areas`, `new_count` falls back to the shared, never-truncated
            # database's active profile's `target_role_families` (F17-06), which another
            # test may have left non-empty; these fixtures carry no role_family, so that
            # silently drops all three (F20 sanity pass).
            filters={"company_id": str(company.id), "all_areas": True},
            owner_sub=OWNER_A,
        )
        model = session.get(SavedSearchModel, saved.id)
        assert model is not None
        model.last_opened_at = reference
        session.flush()
        saved = next(
            item for item in list_saved_searches(session, owner_sub=OWNER_A) if item.id == saved.id
        )

        assert new_count(session, saved, owner_sub=OWNER_A) == 1


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
            # `all_areas` keeps this scoped to the unknown-key warning under test, same
            # reasoning as the other `new_count` tests in this file.
            filters={
                "company_id": str(company.id),
                "renamed_filter": "legacy-value",
                "all_areas": True,
            },
            owner_sub=OWNER_A,
        )

        with caplog.at_level("WARNING"):
            count = new_count(session, saved, owner_sub=OWNER_A)

        assert count == 1
        assert "renamed_filter" in caplog.text


def test_saved_searches_are_private_to_the_authenticated_owner() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        saved = create_saved_search(
            session, name="Busca A", term=None, filters={}, owner_sub=OWNER_A
        )

        assert saved.id in {item.id for item in list_saved_searches(session, owner_sub=OWNER_A)}
        assert saved.id not in {item.id for item in list_saved_searches(session, owner_sub=OWNER_B)}


def test_saved_search_mutations_reject_a_foreign_id_without_changing_owner_row() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        saved = create_saved_search(
            session, name="Busca A", term=None, filters={}, owner_sub=OWNER_A
        )
        original = session.get(SavedSearchModel, saved.id)
        assert original is not None
        original_opened_at = original.last_opened_at

        with pytest.raises(SavedSearchNotFoundError):
            rename_saved_search(session, saved.id, name="Busca B", owner_sub=OWNER_B)
        with pytest.raises(SavedSearchNotFoundError):
            open_saved_search(session, saved.id, owner_sub=OWNER_B)
        with pytest.raises(SavedSearchNotFoundError):
            delete_saved_search(session, saved.id, owner_sub=OWNER_B)

        preserved = session.get(SavedSearchModel, saved.id)
        assert preserved is not None
        assert preserved.owner_sub == OWNER_A
        assert preserved.name == "Busca A"
        assert preserved.last_opened_at == original_opened_at


@pytest.mark.parametrize("saved_search_count", [0, 1, 20])
def test_saved_search_summary_matches_an_independent_legacy_inbox_total(
    saved_search_count: int,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = f"{OWNER_A}-summary-{uuid4().hex}"
    reference = datetime.now(UTC)
    with Session(engine) as session:
        company = _company(session)
        source = SourceDefinitionModel(
            source_type="TEST",
            name=f"Saved search grouping {uuid4().hex}",
        )
        session.add(source)
        session.flush()
        _opportunity(
            session,
            company,
            title="Summary before cutoff",
            created_at=reference - timedelta(seconds=1),
            role_family="DATA",
        )
        included = _opportunity(
            session,
            company,
            title="Summary after cutoff",
            created_at=reference + timedelta(seconds=1),
            role_family="DATA",
        )
        duplicate = _opportunity(
            session,
            company,
            title="Summary after cutoff",
            created_at=reference + timedelta(seconds=2),
            role_family="DATA",
        )
        _posting_occurrence(session, included, source)
        _posting_occurrence(session, duplicate, source)
        _opportunity(
            session,
            company,
            title="Summary outside area",
            created_at=reference + timedelta(seconds=1),
            role_family="SALES",
        )
        session.flush()
        filters = {
            "company_id": str(company.id),
            "work_mode": "REMOTE",
            "seniority": "SENIOR",
            "area": "DATA",
            "order": "priority",
        }
        saved = tuple(
            create_saved_search(
                session,
                name=f"Summary {index}",
                term=None,
                filters=filters,
                owner_sub=owner_sub,
            )
            for index in range(saved_search_count)
        )
        for item in saved:
            model = session.get(SavedSearchModel, item.id)
            assert model is not None
            model.last_opened_at = reference
        session.flush()

        # This is the legacy public Inbox read, deliberately independent of `new_count`.
        # Its total covers the same filters, explicit profile, cutoff and posting-group
        # deduplication that a saved-search summary must preserve.
        legacy_total = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                work_mode="REMOTE",
                role_families=("DATA",),
                seniorities=("SENIOR",),
                created_after=reference,
            ),
            owner_sub=owner_sub,
        ).total

        assert legacy_total == 1
        summaries = list_saved_search_summaries(session, owner_sub=owner_sub)

        assert {item.saved_search.id for item in summaries} == {item.id for item in saved}
        assert [item.new_count for item in summaries] == [legacy_total] * saved_search_count


def test_saved_search_summary_preserves_created_at_descending_id_ascending_order() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    reference = datetime.now(UTC)
    owner_sub = f"{OWNER_A}-summary-order-{uuid4().hex}"
    with Session(engine) as session:
        older = create_saved_search(
            session, name="Older", term=None, filters={"all_areas": True}, owner_sub=owner_sub
        )
        first_tie = create_saved_search(
            session,
            name="First tie",
            term=None,
            filters={"all_areas": True},
            owner_sub=owner_sub,
        )
        second_tie = create_saved_search(
            session,
            name="Second tie",
            term=None,
            filters={"all_areas": True},
            owner_sub=owner_sub,
        )
        for search_id, created_at in (
            (older.id, reference - timedelta(seconds=1)),
            (first_tie.id, reference),
            (second_tie.id, reference),
        ):
            model = session.get(SavedSearchModel, search_id)
            assert model is not None
            model.created_at = created_at
        session.commit()

        summaries = list_saved_search_summaries(session, owner_sub=owner_sub)

        expected_ties = sorted((first_tie.id, second_tie.id))
        assert [item.saved_search.id for item in summaries] == [*expected_ties, older.id]


def test_saved_search_summary_is_empty_and_does_not_leak_another_owner() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_a = f"{OWNER_A}-summary-empty-{uuid4().hex}"
    owner_b = f"{OWNER_B}-summary-private-{uuid4().hex}"
    with Session(engine) as session:
        create_saved_search(
            session, name="Private", term=None, filters={"all_areas": True}, owner_sub=owner_b
        )

        assert list_saved_search_summaries(session, owner_sub=owner_a) == ()
        assert [
            item.saved_search.name
            for item in list_saved_search_summaries(session, owner_sub=owner_b)
        ] == ["Private"]


def test_saved_search_summary_isolates_invalid_legacy_filters_per_owner() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = f"{OWNER_A}-invalid-summary-{uuid4().hex}"
    with Session(engine) as session:
        company = _company(session)
        _opportunity(
            session,
            company,
            title="Valid summary alongside invalid legacy filters",
            created_at=datetime.now(UTC),
        )
        valid = create_saved_search(
            session,
            name="Valid",
            term=None,
            filters={"company_id": str(company.id), "all_areas": True},
            owner_sub=owner_sub,
        )
        invalid_filters = (
            ("Invalid legacy order", {"order": "not-an-inbox-order", "all_areas": True}),
            ("Object search", {"search": {"query": "backend"}, "all_areas": True}),
            ("List search", {"search": ["backend"], "all_areas": True}),
            ("Non-string verdict", {"verdict": ["RECOMMENDED", 1], "all_areas": True}),
            ("Non-string seniority", {"seniority": ["SENIOR", None], "all_areas": True}),
            ("List published after", {"published_after": ["2026-01-01"], "all_areas": True}),
            (
                "Object published after",
                {"published_after": {"date": "2026-01-01"}, "all_areas": True},
            ),
            ("Object applied", {"applied": {"value": True}, "all_areas": True}),
            ("List applied", {"applied": [True], "all_areas": True}),
            ("Object only assessed", {"only_assessed": {"value": True}, "all_areas": True}),
            ("Object work mode", {"work_mode": {"value": "remote"}, "all_areas": True}),
            ("Object all areas", {"all_areas": {"value": True}}),
            ("Empty list score", {"minimum_score": [], "all_areas": True}),
            ("Object salary", {"salary_min": {}, "all_areas": True}),
            ("NaN score", {"minimum_score": "NaN", "all_areas": True}),
            ("Infinite salary", {"salary_max": "Infinity", "all_areas": True}),
        )
        # Legacy rows predate create-time validation, so they are seeded directly.
        invalid_models = [
            SavedSearchModel(owner_sub=owner_sub, name=name, term=None, filters=filters)
            for name, filters in invalid_filters
        ]
        session.add_all(invalid_models)
        session.commit()
        invalid = [
            next(
                item
                for item in list_saved_searches(session, owner_sub=owner_sub)
                if item.id == model.id
            )
            for model in invalid_models
        ]

        summaries = {
            item.saved_search.id: item
            for item in list_saved_search_summaries(session, owner_sub=owner_sub)
        }

        assert summaries[valid.id].new_count == 1
        assert summaries[valid.id].count_error is None
        for saved_search in invalid:
            assert summaries[saved_search.id].new_count is None
            assert summaries[saved_search.id].count_error == "invalid_filters"


@pytest.mark.skipif(
    os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1"
    or not os.environ.get("DATABASE_URL", "").split("?", 1)[0].endswith("_test"),
    reason="summary SQL query counting requires the isolated _test database",
)
@pytest.mark.parametrize("saved_search_count", [0, 1, 20])
def test_saved_search_summary_records_one_list_and_one_batched_count_query(
    saved_search_count: int,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = f"{OWNER_A}-summary-query-count-{uuid4().hex}"
    with Session(engine) as session:
        for index in range(saved_search_count):
            create_saved_search(
                session,
                name=f"Query count {index}",
                term=None,
                filters={"all_areas": True},
                owner_sub=owner_sub,
            )
        statements: list[str] = []

        def record(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            started_at = perf_counter()
            summaries = list_saved_search_summaries(session, owner_sub=owner_sub)
            elapsed_seconds = perf_counter() - started_at
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert len(summaries) == saved_search_count
        assert elapsed_seconds >= 0
        assert len(statements) == (1 if not summaries else 2)
        print(
            "summary_sql_measure "
            f"saved_searches={saved_search_count} statements={len(statements)} "
            f"elapsed_seconds={elapsed_seconds:.6f}"
        )


@pytest.mark.skipif(
    os.environ.get("DATABASE_INTEGRATION_ISOLATED") != "1"
    or not os.environ.get("DATABASE_URL", "").split("?", 1)[0].endswith("_test"),
    reason="summary SQL query counting requires the isolated _test database",
)
@pytest.mark.parametrize("saved_search_count", [0, 1, 20])
def test_saved_search_summary_measures_active_profile_fallback_query(
    saved_search_count: int,
) -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = f"{OWNER_A}-summary-profile-fallback-{uuid4().hex}"
    with Session(engine) as session:
        ProfileService(session, owner_sub).create_active_version(
            ProfileSnapshot(
                skills=(),
                experiences=(),
                projects=(),
                preferences=EmploymentPreference(target_role_families=("DATA",)),
            ),
            expected_profile_version=0,
        )
        for index in range(saved_search_count):
            create_saved_search(
                session,
                name=f"Fallback {index}",
                term=None,
                filters={},
                owner_sub=owner_sub,
            )
        statements: list[str] = []

        def record(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: object,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            summaries = list_saved_search_summaries(session, owner_sub=owner_sub)
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert len(summaries) == saved_search_count
        assert len(statements) == (1 if not summaries else 4)
        print(
            "summary_profile_fallback_sql "
            f"saved_searches={saved_search_count} statements={len(statements)}"
        )


def test_saved_search_summary_keeps_assessments_scoped_to_each_profile_and_owner() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = f"{OWNER_A}-summary-profiles-{uuid4().hex}"
    foreign_owner_sub = f"{OWNER_B}-summary-profiles-{uuid4().hex}"
    with Session(engine) as session:
        service = ProfileService(session, owner_sub)
        first = service.create_active_version(
            ProfileSnapshot(
                skills=(), experiences=(), projects=(), preferences=EmploymentPreference()
            ),
            expected_profile_version=0,
        )
        second = service.create_active_version(
            ProfileSnapshot(
                skills=(), experiences=(), projects=(), preferences=EmploymentPreference()
            ),
            expected_profile_version=1,
        )
        foreign = ProfileService(session, foreign_owner_sub).create_active_version(
            ProfileSnapshot(
                skills=(), experiences=(), projects=(), preferences=EmploymentPreference()
            ),
            expected_profile_version=0,
        )
        company = _company(session)
        opportunity = _opportunity(
            session,
            company,
            title="Profile cohort summary",
            created_at=datetime.now(UTC),
        )
        _assessment(
            session,
            opportunity,
            owner_sub=owner_sub,
            profile_version_id=first.id,
            verdict="RECOMMENDED",
        )
        _assessment(
            session,
            opportunity,
            owner_sub=owner_sub,
            profile_version_id=second.id,
            verdict="LOW_MATCH",
        )
        _assessment(
            session,
            opportunity,
            owner_sub=foreign_owner_sub,
            profile_version_id=foreign.id,
            verdict="RECOMMENDED",
        )
        saved = tuple(
            create_saved_search(
                session,
                name=name,
                term=None,
                filters={
                    "all_areas": True,
                    "profile_version_id": str(profile_version_id),
                    "verdict": "RECOMMENDED",
                },
                owner_sub=owner_sub,
            )
            for name, profile_version_id in (
                ("First profile", first.id),
                ("Second profile", second.id),
                ("Foreign profile", foreign.id),
            )
        )

        expected = {item.id: new_count(session, item, owner_sub=owner_sub) for item in saved}
        summaries = {
            item.saved_search.id: item
            for item in list_saved_search_summaries(session, owner_sub=owner_sub)
        }

        assert expected == {saved[0].id: 1, saved[1].id: 0, saved[2].id: 0}
        assert {
            saved_search_id: item.new_count for saved_search_id, item in summaries.items()
        } == expected


def _query_for(filters: dict[str, object]) -> InboxQuery:
    saved = saved_search_service.SavedSearch(
        id=uuid4(),
        name="",
        term=None,
        filters=filters,
        last_opened_at=None,
        created_at=datetime.now(UTC),
    )
    return saved_search_service._saved_search_inbox_query(saved)[0]


@pytest.mark.parametrize(
    ("filters", "only_recent", "window", "open_at_source"),
    [
        ({}, True, 30, False),
        ({"only_recent": True}, True, 30, False),
        ({"only_recent": "true"}, True, 30, False),
        ({"only_recent": False}, False, 30, False),
        ({"only_recent": "false"}, False, 30, False),
        ({"lens": ""}, True, 30, False),
        ({"lens": "novas"}, True, 14, False),
        ({"lens": "abertas"}, True, 30, True),
        ({"recency_window_days": 7}, True, 7, False),
        ({"recency_window_days": "90"}, True, 90, False),
        ({"recency_window_days": 365}, True, 365, False),
        ({"recency_window_days": 90, "lens": "novas"}, True, 14, False),
        ({"open_at_source": "true"}, True, 30, True),
    ],
)
def test_saved_search_recency_keys_map_to_inbox_query(
    filters: dict[str, object], only_recent: bool, window: int, open_at_source: bool
) -> None:
    query = _query_for(filters)

    assert query.only_recent is only_recent
    assert query.recency_window_days == window
    assert query.open_at_source is open_at_source


@pytest.mark.parametrize(
    "filters",
    [
        {"lens": "recentes"},
        {"lens": 5},
        {"recency_window_days": 0},
        {"recency_window_days": 366},
        {"recency_window_days": "abc"},
        {"recency_window_days": True},
        {"only_recent": "maybe"},
        {"only_startups": "yes"},
    ],
)
def test_saved_search_invalid_recency_keys_are_rejected(filters: dict[str, object]) -> None:
    with pytest.raises(InvalidSavedSearchFiltersError):
        saved_search_service.validate_saved_search_filters(filters)


@pytest.mark.parametrize(
    "filters",
    [
        {"salary_min": "5000"},
        {"salary_max": "5000"},
        {"salary_min": "5000", "salary_currency": "BRL"},
        {"salary_min": "5000", "salary_period": "MONTH"},
        {"salary_min": "5000", "salary_currency": "reais", "salary_period": "MONTH"},
        {"salary_min": "5000", "salary_currency": "BRL", "salary_period": "UNKNOWN"},
        {"salary_min": "5000", "salary_currency": "BRL", "salary_period": "FORTNIGHT"},
    ],
)
def test_create_saved_search_requires_a_complete_salary_unit(
    filters: dict[str, object],
) -> None:
    with pytest.raises(InvalidSavedSearchFiltersError):
        saved_search_service.validate_saved_search_filters(filters)


def test_create_saved_search_accepts_salary_unit_and_ignores_it_without_a_bound() -> None:
    saved_search_service.validate_saved_search_filters(
        {"salary_min": "5000", "salary_currency": "USD", "salary_period": "YEAR"}
    )
    saved_search_service.validate_saved_search_filters(
        {"salary_currency": "USD", "salary_period": "YEAR"}
    )


def test_saved_search_salary_unit_maps_to_inbox_query() -> None:
    query = _query_for(
        {"salary_min": "5000", "salary_currency": "USD", "salary_period": "YEAR"}
    )

    assert (query.salary_currency, query.salary_period) == ("USD", CompensationPeriod.YEAR)


def test_legacy_saved_search_salary_defaults_to_brl_month_when_read() -> None:
    query = _query_for({"salary_min": "5000"})

    assert query.salary_currency == "BRL"
    assert query.salary_period == CompensationPeriod.MONTH


def test_legacy_saved_search_summary_notes_the_defaulted_salary_unit() -> None:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    owner_sub = f"{OWNER_A}-salary-unit-{uuid4().hex}"
    with Session(engine) as session:
        # Legacy rows predate create-time validation, so they are seeded directly.
        models = {
            "legacy": SavedSearchModel(
                owner_sub=owner_sub,
                name="legacy",
                filters={"salary_min": "5000", "all_areas": True},
            ),
            "complete": SavedSearchModel(
                owner_sub=owner_sub,
                name="complete",
                filters={
                    "salary_min": "5000",
                    "salary_currency": "USD",
                    "salary_period": "YEAR",
                    "all_areas": True,
                },
            ),
            "no_salary": SavedSearchModel(
                owner_sub=owner_sub, name="no_salary", filters={"all_areas": True}
            ),
            "bad_unit": SavedSearchModel(
                owner_sub=owner_sub,
                name="bad_unit",
                filters={"salary_min": "5000", "salary_currency": "reais", "all_areas": True},
            ),
        }
        session.add_all(models.values())
        session.commit()

        by_name = {
            item.saved_search.name: item
            for item in list_saved_search_summaries(session, owner_sub=owner_sub)
        }

        assert by_name["legacy"].count_note == "salary_unit_defaulted"
        assert by_name["legacy"].count_error is None
        assert by_name["legacy"].new_count is not None
        assert by_name["complete"].count_note is None
        assert by_name["no_salary"].count_note is None
        assert by_name["bad_unit"].count_error == "invalid_filters"
        assert by_name["bad_unit"].count_note is None
