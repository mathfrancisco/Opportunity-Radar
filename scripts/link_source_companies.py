"""Give every enabled source without a company_source link a Company and a CompanySource (F48-17).

Sources proposed by discovery (or imported by hand) can be enabled with no `company_source_id`,
so their items normalize with no canonical company. For each such source this script reads
`configuration.company_name`, links to the existing company with the same `normalized_name`
(never a fuzzy match) or creates it, then creates or reuses the `CompanySource` that carries
the board identifier and points the source at it.

Idempotent: a linked source is never touched. Sources with no company name (Remotive, Hacker
News) or that touch a forbidden platform (F48-19) are reported and skipped. `--dry-run`
reports the plan and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.forbidden import forbidden_platform_in
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.proposals import IDENTIFIER_KEYS
from opportunity_radar.companies.domain import normalize_name
from opportunity_radar.companies.models import Company, CompanySource
from opportunity_radar.platform.database import create_database_engine

_ENDPOINT_TEMPLATES = {
    "ashby": "https://jobs.ashbyhq.com/{key}",
    "greenhouse": "https://boards.greenhouse.io/{key}",
    "lever": "https://jobs.lever.co/{key}",
    "workable": "https://apply.workable.com/{key}",
    "teamtailor": "https://{key}",
}


def _identifier(source: SourceDefinitionModel) -> str | None:
    key = IDENTIFIER_KEYS.get(source.source_type)
    value = (source.configuration or {}).get(key) if key else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _endpoint(source: SourceDefinitionModel, identifier: str | None) -> str:
    configuration = source.configuration or {}
    for field in ("careers_url", "board_url", "url"):
        value = configuration.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    template = _ENDPOINT_TEMPLATES.get(source.source_type)
    if template is not None and identifier:
        return template.format(key=identifier)
    return f"{source.source_type}://{identifier or source.id}"


def link_sources(session: Session, *, dry_run: bool) -> dict[str, Any]:
    sources = session.scalars(
        select(SourceDefinitionModel)
        .where(
            SourceDefinitionModel.enabled.is_(True),
            SourceDefinitionModel.company_source_id.is_(None),
        )
        .order_by(SourceDefinitionModel.name)
    ).all()
    companies: dict[str, Company | None] = {}
    planned: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for source in sources:
        name = (source.configuration or {}).get("company_name")
        normalized = normalize_name(name) if isinstance(name, str) else ""
        if not normalized:
            skipped.append({"source": source.name, "reason": "no_company_name"})
            continue
        if forbidden_platform_in(source.configuration or {}) is not None:
            skipped.append({"source": source.name, "reason": "forbidden_platform"})
            continue
        if normalized not in companies:
            companies[normalized] = session.scalar(
                select(Company).where(Company.normalized_name == normalized)
            )
        company = companies[normalized]
        action = "link_existing_company" if company is not None else "create_company"
        if company is None and not dry_run:
            company = Company(canonical_name=str(name).strip(), normalized_name=normalized)
            session.add(company)
            session.flush()
            companies[normalized] = company
        identifier = _identifier(source)
        endpoint = _endpoint(source, identifier)
        planned.append(
            {
                "source": source.name,
                "source_type": source.source_type,
                "company": str(name).strip(),
                "action": action,
                "endpoint": endpoint,
            }
        )
        if dry_run or company is None:
            continue
        record = session.scalar(
            select(CompanySource).where(
                CompanySource.company_id == company.id,
                CompanySource.source_type == source.source_type,
                (CompanySource.external_key == identifier)
                if identifier
                else (CompanySource.endpoint == endpoint),
            )
        ) or session.scalar(
            select(CompanySource).where(
                CompanySource.company_id == company.id,
                CompanySource.source_type == source.source_type,
                CompanySource.endpoint == endpoint,
            )
        )
        if record is None:
            record = CompanySource(
                company_id=company.id,
                source_type=source.source_type,
                endpoint=endpoint,
                external_key=identifier,
                verification_status="ats_identified",
                verification_method="source_configuration",
                evidence_note=f"linked from enabled source '{source.name}' (F48-17)",
            )
            session.add(record)
            session.flush()
        source.company_source_id = record.id
        source.version += 1
    session.flush()
    return {
        "dry_run": dry_run,
        "sources_without_link": len(sources),
        "would_link" if dry_run else "linked": len(planned),
        "companies_created": (
            len({p["company"].casefold() for p in planned if p["action"] == "create_company"})
        ),
        "plan": planned,
        "skipped": skipped,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = link_sources(session, dry_run=args.dry_run)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
