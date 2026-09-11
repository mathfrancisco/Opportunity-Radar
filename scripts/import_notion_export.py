"""Import a CSV or JSON Notion export into the local Company Radar catalog."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from opportunity_radar.companies.domain import (
    AmbiguousCompanyIdentityError,
    CompanyCandidate,
    CompanySourceCandidate,
    normalize_domain,
)
from opportunity_radar.companies.models import CompanyImportBatch, CompanyImportIssue
from opportunity_radar.companies.repository import CompanyRepository
from opportunity_radar.companies.service import CompanyService
from opportunity_radar.platform.database import create_database_engine

NAME_COLUMNS = ("name", "company", "company name", "empresa", "nome")
DOMAIN_COLUMNS = ("domain", "website", "site", "url", "company domain", "dominio", "domínio")
ALIAS_COLUMNS = ("aliases", "alias", "alternative names", "nome alternativo")
PRIORITY_COLUMNS = ("priority", "prioridade")
SOURCE_TYPE_COLUMNS = ("source type", "source_type", "ats", "tipo de fonte")
ENDPOINT_COLUMNS = ("career url", "careers url", "endpoint", "jobs url", "career page")


def _value(row: dict[str, Any], columns: tuple[str, ...]) -> str | None:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for column in columns:
        value = normalized.get(column)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _aliases(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(
        alias.strip()
        for alias in value.replace("\n", ";").replace("|", ";").split(";")
        if alias.strip()
    )


def read_rows(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as source:
            yield from csv.DictReader(source)
        return
    if path.suffix.casefold() == ".json":
        content = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(content, dict):
            content = content.get(
                "results",
                content.get("items", content.get("companies", [])),
            )
        if not isinstance(content, list) or not all(isinstance(row, dict) for row in content):
            raise ValueError(
                "JSON must be an array of objects or contain results, items, or companies."
            )
        yield from content
        return
    raise ValueError("Input must be a .csv or .json file.")


def candidate_from_row(row: dict[str, Any]) -> CompanyCandidate | None:
    name = _value(row, NAME_COLUMNS)
    if not name:
        return None
    domain = normalize_domain(_value(row, DOMAIN_COLUMNS))
    source_type = _value(row, SOURCE_TYPE_COLUMNS)
    endpoint = _value(row, ENDPOINT_COLUMNS)
    sources = (CompanySourceCandidate(source_type, endpoint),) if source_type and endpoint else ()
    return CompanyCandidate(
        name=name,
        domain=domain,
        aliases=_aliases(_value(row, ALIAS_COLUMNS)),
        sources=sources,
        priority=_value(row, PRIORITY_COLUMNS) or "normal",
    )


def input_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_companies(
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
        raise ValueError("An incomplete import exists for this file; rerun with --resume.")

    batch = None if dry_run else interrupted or CompanyImportBatch(
        file_hash=file_hash,
        source_filename=path.name,
    )
    if batch is not None:
        batch.status = "running"
        batch.report = None
        batch.issues.clear()
        session.add(batch)
        session.flush()
        session.commit()
    result: dict[str, Any] = {
        "status": "dry_run" if dry_run else "completed",
        "file": path.name,
        "file_hash": file_hash,
        "rows": 0,
        "created": 0,
        "reconciled": 0,
        "aliases_added": 0,
        "sources_added": 0,
        "issues": [],
    }
    service = CompanyService(repository)
    for number, row in enumerate(read_rows(path), start=2):
        result["rows"] += 1
        candidate = candidate_from_row(row)
        if candidate is None:
            issue = {
                "row": number,
                "code": "invalid_name",
                "message": "No recognized company name column/value.",
            }
            result["issues"].append(issue)
            if batch is not None:
                batch.issues.append(
                    CompanyImportIssue(
                        row_number=number,
                        code=issue["code"],
                        message=issue["message"],
                        raw_data=row,
                    )
                )
            continue
        try:
            reconciliation = service.reconcile(candidate)
        except AmbiguousCompanyIdentityError as error:
            issue = {"row": number, "code": "manual_review_required", "message": str(error)}
            result["issues"].append(issue)
            if batch is not None:
                batch.issues.append(
                    CompanyImportIssue(
                        row_number=number,
                        code=issue["code"],
                        message=issue["message"],
                        raw_data=row,
                    )
                )
            continue
        if reconciliation.issue:
            issue = {
                "row": number,
                "code": reconciliation.issue,
                "message": "Company name has no usable characters after normalization.",
            }
            result["issues"].append(issue)
            if batch is not None:
                batch.issues.append(
                    CompanyImportIssue(
                        row_number=number,
                        code=issue["code"],
                        message=issue["message"],
                        raw_data=row,
                    )
                )
            continue
        if reconciliation.created:
            result["created"] += 1
        else:
            result["reconciled"] += 1
        result["aliases_added"] += reconciliation.aliases_added
        result["sources_added"] += reconciliation.sources_added
    if dry_run:
        session.rollback()
        return result
    assert batch is not None
    result["batch_id"] = str(batch.id)
    batch.report = result
    batch.status = "completed"
    batch.completed_at = datetime.now(UTC)
    session.commit()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an incomplete batch and reconcile every row safely by identity.",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        report = import_companies(
            session,
            args.input,
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
