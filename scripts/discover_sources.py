"""Propose inert ATS sources from the researched company catalog."""

from __future__ import annotations

import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.discovery import external_key_from_confirmed_ats_url
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.platform.database import create_database_engine


def backfill_discovered_external_keys(session: Session) -> list[dict[str, str]]:
    """Fill keys already proven by ATS discovery without another network request.

    Older `ats_identified` rows kept the confirmed board/API URL but predated the
    proposal identifier.  Only discovery records with an exact, supported URL receive a
    key; ambiguous evidence remains inert for human review.
    """
    updated: list[dict[str, str]] = []
    sources = session.scalars(
        select(CompanySource)
        .where(
            CompanySource.verification_method == "discovery",
            CompanySource.verification_status == "ats_identified",
            CompanySource.external_key.is_(None),
        )
        .order_by(CompanySource.id)
    ).all()
    for source in sources:
        external_key = external_key_from_confirmed_ats_url(
            source.source_type, source.endpoint
        )
        if external_key is None:
            continue
        duplicate = session.scalar(
            select(CompanySource.id).where(
                CompanySource.company_id == source.company_id,
                CompanySource.source_type == source.source_type,
                CompanySource.external_key == external_key,
                CompanySource.id != source.id,
            )
        )
        if duplicate is not None:
            continue
        source.external_key = external_key
        updated.append({"company_source_id": str(source.id), "external_key": external_key})
    if updated:
        session.commit()
    return updated


def discover_sources(session: Session) -> dict[str, list[dict[str, str]]]:
    service = AcquisitionService(
        session,
        registry=build_collector_registry(
            greenhouse_base_url=os.environ.get(
                "GREENHOUSE_BASE_URL", "https://boards-api.greenhouse.io"
            )
        ),
    )
    report: dict[str, list[dict[str, str]]] = {
        "backfilled": backfill_discovered_external_keys(session),
        "proposals": [],
        "not_detected": [],
    }
    for company in session.scalars(select(Company).order_by(Company.canonical_name)):
        proposal, result = service.propose_company_source(company.id)
        if proposal is None:
            report["not_detected"].append({"company": company.canonical_name})
            continue
        report["proposals"].append(
            {
                "company": company.canonical_name,
                "source_id": str(proposal.id),
                "result": result,
                "source_type": proposal.source_type,
            }
        )
    return report


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        print(json.dumps(discover_sources(session), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
