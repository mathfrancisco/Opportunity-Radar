"""Seniority, salary range and source filters for the Inbox (card F17-03 gap-close).

One DB integration test per filter, plus a no-duplicate test for source: an opportunity
with several occurrences from a matching source must appear once, not once per occurrence
(SPEC 37, "Contrato de consulta": "fonte filtra ocorrências, não duplica a oportunidade").
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
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
from opportunity_radar.dashboard.queries import (
    InboxQuery,
    InvalidInboxQueryError,
)
from opportunity_radar.dashboard.queries import list_opportunity_inbox as _list_opportunity_inbox
from opportunity_radar.opportunities.domain import CompensationPeriod
from opportunity_radar.opportunities.models import (
    OpportunityCompensationModel,
    OpportunityModel,
    SourceOccurrenceModel,
)
from opportunity_radar.platform.database import create_database_engine

from .test_queries import _company, _opportunity

OWNER_SUB = "user-search-filters"


def list_opportunity_inbox(session: Session, query: InboxQuery):
    return _list_opportunity_inbox(session, query, owner_sub=OWNER_SUB)

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


def _source(session: Session, *, name: str | None = None) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        id=uuid4(),
        source_type="greenhouse",
        name=name or f"search-filters {uuid4().hex[:8]}",
        enabled=True,
        configuration={},
        rate_limit_policy={},
        evidence_status="confirmed",
    )
    session.add(source)
    session.flush()
    return source


def _run(session: Session, source: SourceDefinitionModel) -> SourceRunModel:
    run = SourceRunModel(
        id=uuid4(),
        source_definition_id=source.id,
        execution_trigger="SCHEDULED",
        status="SUCCEEDED",
        started_at=NOW,
        finished_at=NOW,
    )
    session.add(run)
    session.flush()
    return run


def _occurrence(
    session: Session,
    opportunity: OpportunityModel,
    source: SourceDefinitionModel,
) -> SourceOccurrenceModel:
    marker = uuid4().hex[:12]
    run = _run(session, source)
    raw_item = RawItemModel(
        id=uuid4(),
        source_run_id=run.id,
        source_definition_id=source.id,
        external_id=marker,
        identity_key=f"external:{marker}",
        payload_hash=uuid4().hex + uuid4().hex,
        item_metadata={},
    )
    raw_item.payload_record = RawItemPayloadModel(payload={"title": "Probe"})
    session.add(raw_item)
    session.flush()
    occurrence = SourceOccurrenceModel(
        opportunity_id=opportunity.id,
        raw_item_id=raw_item.id,
        source_definition_id=source.id,
        external_id=marker,
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(occurrence)
    session.flush()
    return occurrence


def _compensation(
    session: Session,
    opportunity: OpportunityModel,
    occurrence: SourceOccurrenceModel,
    *,
    amount_min: Decimal | None,
    amount_max: Decimal | None,
    currency: str | None = None,
    period: str = "UNKNOWN",
) -> None:
    session.add(
        OpportunityCompensationModel(
            opportunity_id=opportunity.id,
            source_occurrence_id=occurrence.id,
            raw_item_id=occurrence.raw_item_id,
            amount_min=amount_min,
            amount_max=amount_max,
            currency=currency,
            period=period,
            normalizer_version="v3",
        )
    )
    session.flush()


def test_seniority_filter_narrows_the_inbox() -> None:
    with _session() as session:
        company = _company(session, "normal")
        senior = _opportunity(
            session, company, title="Senior Role", published_at=NOW, seniority="SENIOR"
        )
        _opportunity(
            session, company, title="Junior Role", published_at=NOW, seniority="JUNIOR"
        )
        session.commit()

        filtered = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, seniorities=("SENIOR",))
        )
        assert [item.opportunity_id for item in filtered.items] == [senior.id]


def test_salary_range_filter_matches_overlapping_compensation() -> None:
    with _session() as session:
        company = _company(session, "normal")
        source = _source(session)
        in_range = _opportunity(session, company, title="In Range", published_at=NOW)
        out_of_range = _opportunity(session, company, title="Out of Range", published_at=NOW)
        _compensation(
            session,
            in_range,
            _occurrence(session, in_range, source),
            amount_min=Decimal("8000"),
            amount_max=Decimal("12000"),
            currency="BRL",
            period="MONTH",
        )
        _compensation(
            session,
            out_of_range,
            _occurrence(session, out_of_range, source),
            amount_min=Decimal("2000"),
            amount_max=Decimal("3000"),
            currency="BRL",
            period="MONTH",
        )
        session.commit()

        filtered = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                salary_min=Decimal("6000"),
                salary_max=Decimal("15000"),
                salary_currency="BRL",
                salary_period=CompensationPeriod.MONTH,
            ),
        )
        assert [item.opportunity_id for item in filtered.items] == [in_range.id]


def test_source_filter_matches_occurrences() -> None:
    with _session() as session:
        company = _company(session, "normal")
        matching_source = _source(session)
        other_source = _source(session)
        matching = _opportunity(session, company, title="From Source", published_at=NOW)
        not_matching = _opportunity(session, company, title="Other Source", published_at=NOW)
        _occurrence(session, matching, matching_source)
        _occurrence(session, not_matching, other_source)
        session.commit()

        filtered = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id, source_definition_ids=(matching_source.id,)
            ),
        )
        assert [item.opportunity_id for item in filtered.items] == [matching.id]


def test_source_filter_does_not_duplicate_a_multi_source_opportunity() -> None:
    with _session() as session:
        company = _company(session, "normal")
        source_a = _source(session)
        source_b = _source(session)
        opportunity = _opportunity(
            session, company, title="Multi Source", published_at=NOW
        )
        _occurrence(session, opportunity, source_a)
        _occurrence(session, opportunity, source_b)
        session.commit()

        filtered = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                source_definition_ids=(source_a.id, source_b.id),
            ),
        )
        assert [item.opportunity_id for item in filtered.items] == [opportunity.id]
        assert filtered.total == 1


def _seed_salary_cases(session: Session) -> tuple[Company, dict[str, OpportunityModel]]:
    company = _company(session, "normal")
    source = _source(session)
    cases: dict[str, tuple[str | None, str, Decimal, Decimal] | None] = {
        "brl_month_in_range": ("BRL", "MONTH", Decimal("6000"), Decimal("8000")),
        "brl_month_below": ("BRL", "MONTH", Decimal("3000"), Decimal("4000")),
        "usd_year": ("USD", "YEAR", Decimal("6000"), Decimal("8000")),
        "brl_unknown_period": ("BRL", "UNKNOWN", Decimal("6000"), Decimal("8000")),
        "null_currency_month": (None, "MONTH", Decimal("6000"), Decimal("8000")),
        "no_row": None,
    }
    found: dict[str, OpportunityModel] = {}
    for name, spec in cases.items():
        opportunity = _opportunity(session, company, title=name, published_at=NOW)
        found[name] = opportunity
        if spec is not None:
            currency, period, low, high = spec
            _compensation(
                session,
                opportunity,
                _occurrence(session, opportunity, source),
                amount_min=low,
                amount_max=high,
                currency=currency,
                period=period,
            )
    session.commit()
    return company, found


def test_salary_filter_compares_only_within_the_same_unit_and_marks_unknown() -> None:
    with _session() as session:
        company, found = _seed_salary_cases(session)

        page = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                salary_min=Decimal("5000"),
                salary_currency="BRL",
                salary_period=CompensationPeriod.MONTH,
            ),
        )

        by_title = {item.title: item.salary_match for item in page.items}
        assert by_title == {
            "brl_month_in_range": "matched",
            "brl_unknown_period": "unknown",
            "null_currency_month": "unknown",
            "no_row": "unknown",
        }
        assert found["usd_year"].id not in {item.opportunity_id for item in page.items}
        assert page.total == 4


def test_salary_max_bound_uses_the_same_unit_rule() -> None:
    with _session() as session:
        company, _ = _seed_salary_cases(session)

        page = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                salary_max=Decimal("5000"),
                salary_currency="BRL",
                salary_period=CompensationPeriod.MONTH,
            ),
        )

        assert {item.title: item.salary_match for item in page.items} == {
            "brl_month_below": "matched",
            "brl_unknown_period": "unknown",
            "null_currency_month": "unknown",
            "no_row": "unknown",
        }


def test_salary_match_is_none_without_a_salary_filter() -> None:
    with _session() as session:
        company, _ = _seed_salary_cases(session)

        page = list_opportunity_inbox(session, InboxQuery(company_id=company.id))

        assert len(page.items) == 6
        assert {item.salary_match for item in page.items} == {None}


def test_one_comparable_row_in_range_makes_a_multi_row_posting_matched() -> None:
    with _session() as session:
        company = _company(session, "normal")
        source = _source(session)
        opportunity = _opportunity(session, company, title="two rows", published_at=NOW)
        for low, high, currency in (
            (Decimal("1000"), Decimal("2000"), "BRL"),
            (Decimal("6000"), Decimal("8000"), "BRL"),
        ):
            _compensation(
                session,
                opportunity,
                _occurrence(session, opportunity, source),
                amount_min=low,
                amount_max=high,
                currency=currency,
                period="MONTH",
            )
        session.commit()

        page = list_opportunity_inbox(
            session,
            InboxQuery(
                company_id=company.id,
                salary_min=Decimal("5000"),
                salary_currency="BRL",
                salary_period=CompensationPeriod.MONTH,
            ),
        )

        assert [(item.title, item.salary_match) for item in page.items] == [
            ("two rows", "matched")
        ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"salary_min": Decimal("1")},
        {"salary_max": Decimal("1")},
        {"salary_min": Decimal("1"), "salary_currency": "BRL"},
        {"salary_min": Decimal("1"), "salary_period": CompensationPeriod.MONTH},
        {
            "salary_min": Decimal("1"),
            "salary_currency": "reais",
            "salary_period": CompensationPeriod.MONTH,
        },
        {
            "salary_min": Decimal("1"),
            "salary_currency": "BRL",
            "salary_period": CompensationPeriod.UNKNOWN,
        },
    ],
)
def test_inbox_query_rejects_a_salary_bound_without_a_valid_unit(kwargs: dict) -> None:
    with pytest.raises(InvalidInboxQueryError):
        InboxQuery(**kwargs)


def test_inbox_query_ignores_unit_without_a_salary_bound() -> None:
    query = InboxQuery(salary_currency="BRL", salary_period=CompensationPeriod.MONTH)
    assert query.salary_min is None and query.salary_max is None
