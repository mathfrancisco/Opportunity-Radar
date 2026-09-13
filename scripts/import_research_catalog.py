"""Import the researched Markdown catalog; it replaces Notion in the normal MVP flow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.companies.domain import (
    AmbiguousCompanyIdentityError,
    CompanyCandidate,
    CompanySourceCandidate,
)
from opportunity_radar.companies.models import (
    Company,
    CompanyImportBatch,
    CompanyImportIssue,
    CompanySource,
)
from opportunity_radar.companies.repository import CompanyRepository
from opportunity_radar.companies.service import CompanyService
from opportunity_radar.platform.database import create_database_engine

DEFAULT_INPUTS = (
    Path("docs/pesquisas/auditoria-186-empresas.md"),
    Path("docs/pesquisas/empresas-adicionais.md"),
)
LINK = re.compile(r"\[([^]]+)\]\((https?://[^)]+)\)")
BACKLOG_STATES = ("página dinâmica", "redirecionamento", "acesso pendente")
RESEARCHED_AT = datetime(2026, 9, 11, tzinfo=UTC)
RESEARCH_IMPORT_LOCK = "opportunity_radar.research_catalog"
RESEARCH_ALIASES = {
    "Databricks": ("Neon",),
    "Neon": ("Databricks",),
    "receeve": ("InDebted",),
    "InDebted": ("receeve",),
    "Timescale": ("Tiger Data",),
    "TravelPerk": ("Perk",),
    "Doist": ("Todoist",),
}
PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2}
VERIFICATION_RANK = {
    "backlog": 0,
    "research_recorded": 1,
    "careers_confirmed": 2,
    "ats_identified": 3,
    "api_json_confirmed": 4,
}


def register_researched_collectors(session: Session, *, dry_run: bool) -> int:
    """Materialize researched API and ATS boards as disabled definitions."""
    runnable_sources = session.scalars(
        select(CompanySource)
        .join(CompanySource.company)
        .where(
            or_(
                and_(
                    CompanySource.verification_status == "api_json_confirmed",
                    CompanySource.source_type.in_(
                        ("ashby", "lever", "greenhouse")
                    ),
                ),
                and_(
                    CompanySource.verification_status == "ats_identified",
                    CompanySource.source_type == "greenhouse",
                ),
            ),
            CompanySource.external_key.is_not(None),
        )
        .order_by(Company.canonical_name)
    ).all()
    existing_definitions = {
        (company_source_id, source_type)
        for company_source_id, source_type in session.execute(
            select(
                SourceDefinitionModel.company_source_id,
                SourceDefinitionModel.source_type,
            ).where(SourceDefinitionModel.company_source_id.is_not(None))
        )
    }
    missing = [
        source
        for source in runnable_sources
        if (source.id, source.source_type) not in existing_definitions
    ]
    if dry_run:
        return len(missing)
    for source in missing:
        identifier_key = {
            "ashby": "board_identifier",
            "lever": "site_identifier",
            "greenhouse": "board_token",
        }[source.source_type]
        configuration = {
            "company_name": source.company.canonical_name,
            identifier_key: source.external_key,
        }
        if source.source_type == "lever":
            configuration["api_region"] = (
                "eu"
                if urlparse(source.endpoint).hostname == "api.eu.lever.co"
                else "global"
            )
        session.add(
            SourceDefinitionModel(
                source_type=source.source_type,
                name=f"{source.company.canonical_name} jobs",
                company_source_id=source.id,
                enabled=False,
                priority=(
                    25
                    if source.verification_status == "api_json_confirmed"
                    else 50
                ),
                rate_limit_policy={
                    "max_retries": 2,
                    "requests_per_second": 0.2,
                    "max_retry_delay_seconds": 30,
                },
                configuration=configuration,
                evidence_status=(
                    "confirmed"
                    if source.verification_status == "api_json_confirmed"
                    else "ats_identified"
                ),
                reviewed_at=source.last_verified_at,
                terms_reviewed=False,
                collector_local_tested=False,
            )
        )
    session.flush()
    return len(missing)


@dataclass(frozen=True, slots=True)
class ResearchRow:
    name: str
    situation: str
    ats: str | None
    consulted_url: str
    evidence: str
    links: tuple[tuple[str, str], ...]

    @property
    def is_backlog(self) -> bool:
        normalized = self.situation.casefold()
        return any(state in normalized for state in BACKLOG_STATES)

    @property
    def source_priority(self) -> str:
        normalized = self.situation.casefold()
        if "api json" in normalized:
            return "high"
        if "ats identificado" in normalized:
            return "normal"
        return "low"

    @property
    def source_status(self) -> str:
        if self.is_backlog:
            return "backlog"
        return {
            "api json confirmada": "api_json_confirmed",
            "ats identificado": "ats_identified",
            "página de carreiras": "careers_confirmed",
        }.get(self.situation.casefold(), "research_recorded")

    def source_candidates(self) -> tuple[CompanySourceCandidate, ...]:
        candidates: list[CompanySourceCandidate] = []
        json_urls = [url for label, url in self.links if label.casefold() == "json"]
        board_urls = [url for label, url in self.links if label.casefold() == "board"]
        if self.ats:
            source_type = self.ats.casefold().replace(" ", "_")
            candidates.extend(
                CompanySourceCandidate(source_type, url)
                for url in json_urls or board_urls or [self.consulted_url]
            )
        else:
            candidates.extend(
                CompanySourceCandidate("api_json", url) for url in json_urls
            )
        candidates.append(CompanySourceCandidate("careers", self.consulted_url))
        return tuple(dict.fromkeys(candidates))

    def as_candidate(self) -> CompanyCandidate:
        return CompanyCandidate(
            name=self.name,
            domain=None,
            aliases=RESEARCH_ALIASES.get(self.name, ()),
            sources=self.source_candidates(),
            priority=self.source_priority,
        )


def _cell_links(value: str) -> tuple[tuple[str, str], ...]:
    return tuple((label.strip(), url.strip()) for label, url in LINK.findall(value))


def _clean_ats(value: str) -> str | None:
    cleaned = value.strip()
    return None if cleaned in {"", "—", "-"} else cleaned


def read_research_rows(path: Path) -> Iterator[ResearchRow]:
    """Yield only five-column company rows from the research Markdown tables."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in {"Empresa", "---"}:
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        source_links = _cell_links(cells[3])
        if not source_links:
            continue
        evidence_links = _cell_links(cells[4])
        yield ResearchRow(
            name=cells[0],
            situation=cells[1],
            ats=_clean_ats(cells[2]),
            consulted_url=source_links[0][1],
            evidence=cells[4],
            links=source_links + evidence_links,
        )


def input_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_evidence(row: ResearchRow) -> str:
    evidence = re.sub(r"\s+", " ", row.evidence).strip()
    value = f"ats={row.ats or 'unknown'}; situation={row.situation}; evidence={evidence}"
    return value


def _source_status(row: ResearchRow, source: CompanySource) -> str:
    if row.is_backlog:
        return "backlog"
    json_urls = {url for label, url in row.links if label.casefold() == "json"}
    if source.endpoint in json_urls:
        return "api_json_confirmed"
    if source.source_type == "careers":
        return "careers_confirmed"
    return "ats_identified"


def _source_external_key(row: ResearchRow, source: CompanySource) -> str | None:
    identified_urls = {
        url
        for label, url in row.links
        if label.casefold() in {"json", "board"}
    }
    if source.endpoint not in identified_urls:
        return None
    return source.endpoint.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0] or None


def _record_source_metadata(
    company_sources: Iterable[CompanySource], row: ResearchRow
) -> None:
    identities = {
        (candidate.source_type, candidate.endpoint)
        for candidate in row.source_candidates()
    }
    for source in company_sources:
        if (source.source_type, source.endpoint) not in identities:
            continue
        source.verification_status = _source_status(row, source)
        source.verification_method = "research_markdown"
        source.external_key = _source_external_key(row, source)
        source.evidence_note = _source_evidence(row)
        source.last_verified_at = RESEARCHED_AT
        if source.verification_status == "api_json_confirmed":
            source.confidence = Decimal("1.000")
        elif source.verification_status == "ats_identified":
            source.confidence = Decimal("0.800")
        elif source.verification_status == "careers_confirmed":
            source.confidence = Decimal("0.600")
        else:
            source.confidence = Decimal("0.300")


def _update_company_state(
    company: Company,
    row: ResearchRow,
    *,
    created: bool,
) -> None:
    if created or PRIORITY_RANK[row.source_priority] > PRIORITY_RANK.get(
        company.priority, -1
    ):
        company.priority = row.source_priority
    if created:
        company.radar_status = "backlog" if row.is_backlog else "active"
    elif not row.is_backlog:
        company.radar_status = "active"
    if created or VERIFICATION_RANK[row.source_status] > VERIFICATION_RANK.get(
        company.verification_state, -1
    ):
        company.verification_state = row.source_status


def _record_issue(
    batch: CompanyImportBatch | None,
    result: dict[str, Any],
    *,
    row_number: int,
    code: str,
    message: str,
    row: ResearchRow,
) -> None:
    issue = {"row": row_number, "code": code, "message": message}
    result["issues"].append(issue)
    if batch is not None:
        batch.issues.append(
            CompanyImportIssue(
                row_number=row_number,
                code=code,
                message=message,
                raw_data={
                    "company": row.name,
                    "situation": row.situation,
                    "ats": row.ats,
                    "consulted_url": row.consulted_url,
                    "evidence": row.evidence,
                },
            )
        )


def import_research_file(
    session: Session,
    path: Path,
    *,
    dry_run: bool,
    resume: bool,
) -> dict[str, Any]:
    file_hash = input_hash(path)
    repository = CompanyRepository(session)
    existing = repository.completed_batch(file_hash)
    if existing is not None:
        return {
            **(existing.report or {}),
            "status": "already_completed",
            "batch_id": str(existing.id),
        }
    interrupted = repository.batch_by_hash(file_hash)
    if interrupted is not None and not resume and not dry_run:
        raise ValueError(
            "An incomplete import exists for this file; rerun with --resume."
        )

    batch = None if dry_run else interrupted or CompanyImportBatch(
        file_hash=file_hash, source_filename=path.name
    )
    if batch is not None:
        batch.status = "running"
        batch.report = None
        batch.issues.clear()
        session.add(batch)
        session.flush()

    result: dict[str, Any] = {
        "status": "dry_run" if dry_run else "completed",
        "file": path.name,
        "file_hash": file_hash,
        "rows": 0,
        "created": 0,
        "reconciled": 0,
        "sources_added": 0,
        "backlog": 0,
        "issues": [],
    }
    service = CompanyService(repository)
    for row_number, row in enumerate(read_research_rows(path), start=1):
        result["rows"] += 1
        try:
            reconciliation = service.reconcile(row.as_candidate())
        except AmbiguousCompanyIdentityError as error:
            _record_issue(
                batch,
                result,
                row_number=row_number,
                code="manual_review_required",
                message=str(error),
                row=row,
            )
            continue
        if reconciliation.issue or reconciliation.company is None:
            _record_issue(
                batch,
                result,
                row_number=row_number,
                code=reconciliation.issue or "invalid_company",
                message="Company name has no usable characters after normalization.",
                row=row,
            )
            continue
        company = reconciliation.company
        _update_company_state(company, row, created=reconciliation.created)
        _record_source_metadata(company.sources, row)
        if reconciliation.created:
            result["created"] += 1
        else:
            result["reconciled"] += 1
        result["sources_added"] += reconciliation.sources_added
        if row.is_backlog:
            result["backlog"] += 1

    if dry_run:
        return result
    assert batch is not None
    result["batch_id"] = str(batch.id)
    batch.report = result
    batch.status = "completed"
    batch.completed_at = datetime.now(UTC)
    session.flush()
    return result


def import_research_catalog(
    session: Session,
    paths: Iterable[Path],
    *,
    dry_run: bool,
    resume: bool,
) -> dict[str, Any]:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_name, 0))"),
        {"lock_name": RESEARCH_IMPORT_LOCK},
    )
    try:
        reports = [
            import_research_file(session, path, dry_run=dry_run, resume=resume)
            for path in paths
        ]
        applied_reports = [
            report for report in reports if report["status"] != "already_completed"
        ]
        status = "dry_run" if dry_run else "completed"
        if not dry_run and not applied_reports:
            status = "already_completed"
        result = {
            "status": status,
            "files": reports,
            "rows": sum(report["rows"] for report in reports),
            "created": sum(report["created"] for report in applied_reports),
            "reconciled": sum(
                report["reconciled"] for report in applied_reports
            ),
            "sources_added": sum(
                report["sources_added"] for report in applied_reports
            ),
            "backlog": sum(report["backlog"] for report in reports),
            "already_completed": len(reports) - len(applied_reports),
        }
        registered = register_researched_collectors(
            session, dry_run=dry_run
        )
        result["source_definitions_registered"] = registered
        if registered and result["status"] == "already_completed":
            result["status"] = "completed"
        if dry_run:
            session.rollback()
        else:
            session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        help="Research Markdown input; may be repeated. Defaults to both MVP research studies.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    paths = tuple(args.input or DEFAULT_INPUTS)
    with Session(create_database_engine(database_url)) as session:
        report = import_research_catalog(
            session,
            paths,
            dry_run=args.dry_run,
            resume=args.resume,
        )
    serialized = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
