"""F48-17: enabled sources without a company_source link get a Company and a CompanySource."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.platform.database import create_database_engine
from scripts.link_source_companies import link_sources

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_PREFIX = "f48-17:"


def _engine():
    return create_database_engine(os.environ["DATABASE_URL"])


@pytest.fixture(autouse=True)
def _cleanup() -> Iterator[None]:
    _purge()
    yield
    _purge()


def _purge() -> None:
    with Session(_engine()) as session:
        session.execute(
            delete(SourceDefinitionModel).where(SourceDefinitionModel.name.startswith(_PREFIX))
        )
        session.execute(delete(Company).where(Company.canonical_name.startswith(_PREFIX)))
        session.commit()


def _source(
    session: Session, source_type: str, configuration: dict[str, str]
) -> SourceDefinitionModel:
    source = SourceDefinitionModel(
        source_type=source_type,
        name=f"{_PREFIX}{uuid4().hex}",
        enabled=True,
        configuration=configuration,
        evidence_status="confirmed",
        terms_reviewed=True,
        collector_local_tested=True,
    )
    session.add(source)
    session.flush()
    return source


def _mine(session: Session, *sources: SourceDefinitionModel) -> list[dict]:
    names = {source.name for source in sources}
    return [row for row in link_sources(session, dry_run=True)["plan"] if row["source"] in names]


def test_dry_run_reports_and_writes_nothing() -> None:
    with Session(_engine()) as session:
        marker = uuid4().hex
        source = _source(
            session,
            "ashby",
            {"company_name": f"{_PREFIX}Acme {marker}", "board_identifier": "acme"},
        )

        report = link_sources(session, dry_run=True)
        plan = [row for row in report["plan"] if row["source"] == source.name]

        assert plan == [
            {
                "source": source.name,
                "source_type": "ashby",
                "company": f"{_PREFIX}Acme {marker}",
                "action": "create_company",
                "endpoint": "https://jobs.ashbyhq.com/acme",
            }
        ]
        assert report["dry_run"] is True
        assert source.company_source_id is None
        assert session.scalar(
            select(func.count()).select_from(Company).where(
                Company.canonical_name.startswith(_PREFIX)
            )
        ) == 0


def test_link_creates_company_and_company_source_and_is_idempotent() -> None:
    with Session(_engine()) as session:
        marker = uuid4().hex
        name = f"{_PREFIX}Acme {marker}"
        source = _source(session, "lever", {"company_name": name, "site_identifier": "acme"})

        link_sources(session, dry_run=False)

        company = session.scalar(select(Company).where(Company.canonical_name == name))
        assert company is not None
        record = session.get(CompanySource, source.company_source_id)
        assert record is not None
        assert (record.company_id, record.source_type, record.external_key) == (
            company.id,
            "lever",
            "acme",
        )
        assert _mine(session, source) == []
        second = link_sources(session, dry_run=False)
        assert all(row["source"] != source.name for row in second["plan"])


def test_link_reuses_an_existing_company_by_normalized_name() -> None:
    with Session(_engine()) as session:
        marker = uuid4().hex
        company = Company(
            canonical_name=f"{_PREFIX}Acme {marker}",
            normalized_name=f"{_PREFIX}acme {marker}",
        )
        session.add(company)
        session.flush()
        source = _source(
            session,
            "greenhouse",
            {"company_name": f"{_PREFIX.upper()}ACME  {marker}", "board_token": "acme"},
        )

        plan = _mine(session, source)
        link_sources(session, dry_run=False)

        assert plan[0]["action"] == "link_existing_company"
        record = session.get(CompanySource, source.company_source_id)
        assert record is not None and record.company_id == company.id
        assert session.scalar(
            select(func.count()).select_from(Company).where(
                Company.normalized_name == company.normalized_name
            )
        ) == 1


def test_research_importer_does_not_materialize_a_forbidden_platform_source() -> None:
    from scripts.import_research_catalog import register_researched_collectors

    with Session(_engine()) as session:
        marker = uuid4().hex
        company = Company(
            canonical_name=f"{_PREFIX}Gupy {marker}", normalized_name=f"{_PREFIX}gupy {marker}"
        )
        session.add(company)
        session.flush()
        before = register_researched_collectors(session, dry_run=True)
        session.add_all(
            [
                CompanySource(
                    company_id=company.id,
                    source_type="ashby",
                    endpoint="https://acme.gupy.io/ashby",
                    external_key="acme",
                    verification_status="ats_identified",
                ),
                CompanySource(
                    company_id=company.id,
                    source_type="lever",
                    endpoint="https://jobs.lever.co/acme",
                    external_key="acme",
                    verification_status="ats_identified",
                ),
            ]
        )
        session.flush()

        # Only the lever record is new work; the forbidden-host record is left as research.
        assert register_researched_collectors(session, dry_run=True) == before + 1


def test_sources_without_company_name_or_on_forbidden_platform_are_skipped() -> None:
    with Session(_engine()) as session:
        nameless = _source(session, "remotive", {})
        forbidden = _source(
            session,
            "ashby",
            {
                "company_name": f"{_PREFIX}Gupy tenant",
                "board_identifier": "x",
                "careers_url": "https://x.gupy.io/",
            },
        )

        report = link_sources(session, dry_run=False)

        skipped = {row["source"]: row["reason"] for row in report["skipped"]}
        assert skipped[nameless.name] == "no_company_name"
        assert skipped[forbidden.name] == "forbidden_platform"
        assert nameless.company_source_id is None and forbidden.company_source_id is None
