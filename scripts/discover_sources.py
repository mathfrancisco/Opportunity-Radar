"""Propose inert ATS sources from the researched company catalog."""

from __future__ import annotations

import json
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import Company
from opportunity_radar.platform.database import create_database_engine


def discover_sources(session: Session) -> dict[str, list[dict[str, str]]]:
    service = AcquisitionService(session)
    report: dict[str, list[dict[str, str]]] = {"proposals": [], "not_detected": []}
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
