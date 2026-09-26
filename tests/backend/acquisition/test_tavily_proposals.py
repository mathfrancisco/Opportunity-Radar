"""F20-46: Tavily ATS hints become only inert, auditable source proposals."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    CollectedItem,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel, SourceRunModel
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

_PREFIX = "f20-46:"


def _engine():
    return create_database_engine(os.environ["DATABASE_URL"])


@pytest.fixture(autouse=True)
def _cleanup() -> Iterator[None]:
    _purge()
    yield
    _purge()


def _purge() -> None:
    with Session(_engine()) as session:
        source_ids = list(
            session.scalars(
                select(SourceDefinitionModel.id).where(
                    or_(
                        SourceDefinitionModel.name.startswith(_PREFIX),
                        SourceDefinitionModel.configuration[
                            "company_name"
                        ].as_string().startswith(_PREFIX),
                    )
                )
            )
        )
        if source_ids:
            session.execute(
                delete(RawItemModel).where(RawItemModel.source_definition_id.in_(source_ids))
            )
            session.execute(
                delete(SourceRunModel).where(SourceRunModel.source_definition_id.in_(source_ids))
            )
            session.execute(
                delete(SourceDefinitionModel).where(SourceDefinitionModel.id.in_(source_ids))
            )
        session.execute(
            delete(Company).where(Company.canonical_name.startswith(_PREFIX))
        )
        session.commit()


def _company(session: Session) -> Company:
    marker = uuid4().hex
    company = Company(
        canonical_name=f"{_PREFIX}Acme {marker}",
        normalized_name=f"f20-46-acme-{marker}",
    )
    session.add(company)
    session.commit()
    return company


def _candidate(company: Company, url: str) -> CollectedItem:
    return CollectedItem(
        source_type="tavily_search",
        external_id=uuid4().hex,
        url=url,
        company_name=company.canonical_name,
        description="Acme is hiring backend engineers.",
        raw_payload={"url": url},
        metadata={
            "source_proposal_candidate": True,
            "query": "backend engineer remote brazil",
            "rank": 0,
            "score": 0.87,
        },
    )


def test_known_board_url_becomes_inert_proposal_with_auditable_evidence() -> None:
    with Session(_engine()) as session:
        company = _company(session)
        item = _candidate(company, "https://boards.greenhouse.io/acme/jobs/12345")

        report = AcquisitionService(session).propose_from_tavily_evidence((item,))

        assert report.outcomes[0].outcome == "created"
        proposal = session.get(SourceDefinitionModel, report.outcomes[0].proposal_id)
        assert proposal is not None
        assert proposal.evidence_status == "ats_identified"
        assert proposal.configuration == {
            "company_name": company.canonical_name,
            "board_token": "acme",
            "discovery_evidence": item.url,
            "discovery_via": "tavily_search",
            "discovery_query": "backend engineer remote brazil",
            "discovery_rank": 0,
            "discovery_score": 0.87,
            "discovery_excerpt": "Acme is hiring backend engineers.",
        }


def test_new_proposal_starts_terms_unreviewed_and_untested() -> None:
    with Session(_engine()) as session:
        company = _company(session)
        report = AcquisitionService(session).propose_from_tavily_evidence(
            (_candidate(company, "https://jobs.ashbyhq.com/acme"),)
        )

        proposal = session.get(SourceDefinitionModel, report.outcomes[0].proposal_id)
        assert proposal is not None
        assert proposal.enabled is False
        assert proposal.terms_reviewed is False
        assert proposal.collector_local_tested is False


def test_rerun_over_same_result_does_not_duplicate_proposal() -> None:
    with Session(_engine()) as session:
        company = _company(session)
        item = _candidate(company, "https://jobs.lever.co/acme/123")
        service = AcquisitionService(session)

        first = service.propose_from_tavily_evidence((item,))
        second = service.propose_from_tavily_evidence((item,))

        assert second.outcomes == (
            type(second.outcomes[0])(
                item.url or "", "already_proposed", first.outcomes[0].proposal_id
            ),
        )
        assert session.scalars(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.configuration["company_name"].as_string()
                == company.canonical_name
            )
        ).all().__len__() == 1


def test_url_outside_known_pattern_becomes_pending_not_malformed_proposal() -> None:
    with Session(_engine()) as session:
        company = _company(session)
        item = _candidate(company, "https://example.com/jobs/acme")

        report = AcquisitionService(session).propose_from_tavily_evidence((item,))

        assert report.outcomes == ((type(report.outcomes[0]))(item.url or "", "unmatched_pattern"),)
        assert not session.scalars(
            select(SourceDefinitionModel).where(SourceDefinitionModel.name.startswith(_PREFIX))
        ).all()


def test_proposal_records_tavily_as_origin_distinct_from_html_and_sitemap_discovery() -> None:
    with Session(_engine()) as session:
        company = _company(session)
        report = AcquisitionService(session).propose_from_tavily_evidence(
            (_candidate(company, "https://boards.greenhouse.io/acme/jobs/1"),)
        )

        proposal = session.get(SourceDefinitionModel, report.outcomes[0].proposal_id)
        assert proposal is not None
        assert proposal.configuration["discovery_via"] == "tavily_search"
        assert proposal.configuration["discovery_via"] not in {
            "html_discovery",
            "sitemap_discovery",
        }


def test_company_not_found_becomes_pending_outcome() -> None:
    item = CollectedItem(
        source_type="tavily_search",
        external_id="missing-company",
        url="https://boards.greenhouse.io/acme/jobs/1",
        company_name="No exact company",
        raw_payload={},
        metadata={"source_proposal_candidate": True},
    )
    with Session(_engine()) as session:
        report = AcquisitionService(session).propose_from_tavily_evidence((item,))

        assert report.outcomes == ((type(report.outcomes[0]))(item.url or "", "company_not_found"),)


class _TavilyCollector:
    source_type = "tavily_search"
    capabilities = CollectorCapabilities(keyword_search=True)

    def __init__(self, item: CollectedItem) -> None:
        self.item = item

    async def healthcheck(self, context: object = None) -> HealthResult:
        del context
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        del request
        yield self.item


def test_execute_creates_proposal_after_persisting_tavily_raw_evidence() -> None:
    with Session(_engine()) as session:
        company = _company(session)
        item = _candidate(company, "https://boards.greenhouse.io/acme/jobs/1")
        source = SourceDefinitionModel(
            source_type="tavily_search",
            name=f"{_PREFIX}search-{uuid4().hex}",
            enabled=True,
            configuration={},
            evidence_status="confirmed",
            terms_reviewed=True,
            collector_local_tested=True,
        )
        session.add(source)
        session.commit()
        service = AcquisitionService(
            session,
            registry=CollectorRegistry((_TavilyCollector(item), GreenhouseCollector())),
        )

        run = asyncio.run(service.execute(source.id, CollectionRequest()))

        assert run.items_persisted == 1
        assert session.scalar(
            select(RawItemModel.id).where(RawItemModel.source_definition_id == source.id)
        ) is not None
        proposal = session.scalar(
            select(SourceDefinitionModel).where(
                SourceDefinitionModel.configuration["company_name"].as_string()
                == company.canonical_name
            )
        )
        assert proposal is not None


def test_proposal_failure_keeps_raw_evidence_and_records_partial_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(_engine()) as session:
        company = _company(session)
        item = _candidate(company, "https://boards.greenhouse.io/acme/jobs/1")
        source = SourceDefinitionModel(
            source_type="tavily_search",
            name=f"{_PREFIX}failure-{uuid4().hex}",
            enabled=True,
            configuration={},
            evidence_status="confirmed",
            terms_reviewed=True,
            collector_local_tested=True,
        )
        session.add(source)
        session.commit()
        service = AcquisitionService(
            session, registry=CollectorRegistry((_TavilyCollector(item),))
        )

        def fail(_: object, *, commit: bool = True) -> object:
            del commit
            raise RuntimeError("proposal write failed")

        monkeypatch.setattr(service, "propose_from_tavily_evidence", fail)
        run = asyncio.run(service.execute(source.id, CollectionRequest()))

        assert run.status == "PARTIAL"
        assert session.scalar(
            select(RawItemModel.id).where(RawItemModel.source_definition_id == source.id)
        ) is not None
