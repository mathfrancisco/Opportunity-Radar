"""Owner-scoped relevance marks never leak through the shared opportunity catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from sqlalchemy.dialects import postgresql

from opportunity_radar.opportunities.repository import OpportunityRepository
from opportunity_radar.presentation.http import opportunities as http_opportunities
from opportunity_radar.presentation.http.auth import RequestIdentity

OPPORTUNITY_ID = UUID("10000000-0000-0000-0000-000000000001")
PROFILE_A = UUID("20000000-0000-0000-0000-000000000001")
PROFILE_B = UUID("20000000-0000-0000-0000-000000000002")
MARK_A = UUID("30000000-0000-0000-0000-000000000001")
MARK_B = UUID("30000000-0000-0000-0000-000000000002")
OWNER_A = "user_a_synthetic"
OWNER_B = "user_b_synthetic"
OWNER_C = "user_c_synthetic"
NOW = datetime(2026, 10, 8, tzinfo=UTC)


def _opportunity() -> SimpleNamespace:
    return SimpleNamespace(
        id=OPPORTUNITY_ID,
        fingerprint="a" * 64,
        fingerprint_version="v1",
        canonical_title="Scoped role",
        canonical_company_id=None,
        company_name="Example Corp",
        location_text="Remote",
        work_mode="REMOTE",
        seniority="MID",
        contract_type="FULL_TIME",
        description=None,
        lifecycle_status="OPEN",
        role_family="ENGINEERING",
        role_family_evidence=None,
        role_family_version=None,
        published_at=NOW,
        source_updated_at=None,
        first_seen_at=NOW,
        recency_basis="published",
        valid_through=None,
        recency_exempt_program=False,
        created_at=NOW,
        version=1,
        compensations=[],
        skills=[],
        occurrences=[],
        normalization_results=[],
    )


def _mark(*, owner_sub: str, mark_id: UUID, profile_id: UUID, note: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=mark_id,
        owner_sub=owner_sub,
        relevant=True,
        reason="AREA",
        note=note,
        profile_version_id=profile_id,
        marked_at=NOW,
    )


def test_current_relevance_query_requires_the_authenticated_owner() -> None:
    session = Mock()
    session.scalar.return_value = None

    OpportunityRepository(session).current_relevance_mark(OPPORTUNITY_ID, owner_sub=OWNER_A)

    statement = session.scalar.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "owner_sub" in str(compiled)
    assert OWNER_A in compiled.params.values()


def test_list_returns_only_the_callers_relevance_mark(monkeypatch) -> None:
    opportunity = _opportunity()
    marks = {
        OWNER_A: _mark(owner_sub=OWNER_A, mark_id=MARK_A, profile_id=PROFILE_A, note="A only"),
        OWNER_B: _mark(owner_sub=OWNER_B, mark_id=MARK_B, profile_id=PROFILE_B, note="B only"),
    }
    requested_owners: list[str] = []

    class Repository:
        def __init__(self, session) -> None:
            self.session = session

        def list(self, **kwargs):
            return [opportunity], 1

        def current_relevance_mark(self, opportunity_id, *, owner_sub: str):
            assert opportunity_id == OPPORTUNITY_ID
            requested_owners.append(owner_sub)
            return marks.get(owner_sub)

    monkeypatch.setattr(http_opportunities, "OpportunityRepository", Repository)

    response_a = http_opportunities.list_opportunities(
        page=1,
        page_size=50,
        only_recent=True,
        session=object(),
        identity=RequestIdentity(sub=OWNER_A, is_owner=False),
    )
    response_b = http_opportunities.list_opportunities(
        page=1,
        page_size=50,
        only_recent=True,
        session=object(),
        identity=RequestIdentity(sub=OWNER_B, is_owner=False),
    )

    assert response_a.items[0].relevance_mark is not None
    assert response_a.items[0].relevance_mark.note == "A only"
    assert response_a.items[0].relevance_mark.profile_version_id == PROFILE_A
    assert response_b.items[0].relevance_mark is not None
    assert response_b.items[0].relevance_mark.note == "B only"
    assert response_b.items[0].relevance_mark.profile_version_id == PROFILE_B
    assert requested_owners == [OWNER_A, OWNER_B]


def test_list_omits_another_users_relevance_mark(monkeypatch) -> None:
    opportunity = _opportunity()

    class Repository:
        def __init__(self, session) -> None:
            self.session = session

        def list(self, **kwargs):
            return [opportunity], 1

        def current_relevance_mark(self, opportunity_id, *, owner_sub: str):
            assert opportunity_id == OPPORTUNITY_ID
            assert owner_sub == OWNER_C
            return None

    monkeypatch.setattr(http_opportunities, "OpportunityRepository", Repository)

    response = http_opportunities.list_opportunities(
        page=1,
        page_size=50,
        only_recent=True,
        session=object(),
        identity=RequestIdentity(sub=OWNER_C, is_owner=False),
    )

    assert response.items[0].relevance_mark is None


def test_detail_uses_the_callers_owner_subject(monkeypatch) -> None:
    opportunity = _opportunity()
    own_mark = _mark(owner_sub=OWNER_A, mark_id=MARK_A, profile_id=PROFILE_A, note="A only")

    class Repository:
        def __init__(self, session) -> None:
            self.session = session

        def get(self, opportunity_id):
            assert opportunity_id == OPPORTUNITY_ID
            return opportunity

        def current_relevance_mark(self, opportunity_id, *, owner_sub: str):
            assert opportunity_id == OPPORTUNITY_ID
            assert owner_sub == OWNER_A
            return own_mark

        def posting_group_siblings(self, item):
            assert item is opportunity
            return []

    monkeypatch.setattr(http_opportunities, "OpportunityRepository", Repository)

    response = http_opportunities.get_opportunity(
        OPPORTUNITY_ID,
        session=object(),
        identity=RequestIdentity(sub=OWNER_A, is_owner=False),
    )

    assert response.relevance_mark is not None
    assert response.relevance_mark.note == "A only"
    assert response.relevance_mark.profile_version_id == PROFILE_A
