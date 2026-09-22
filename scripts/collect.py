"""Run every enabled source and preserve a JSON summary for operators."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    CollectionMode,
    CollectionRequest,
)
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import CompanySource  # noqa: F401
from opportunity_radar.platform.database import create_database_engine


def _split(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _sources(
    session: Session,
    *,
    source_ids: tuple[UUID, ...],
    source_types: tuple[str, ...],
) -> list[SourceDefinitionModel]:
    sources = list(
        session.scalars(
            select(SourceDefinitionModel)
            .where(SourceDefinitionModel.enabled.is_(True))
            .order_by(SourceDefinitionModel.priority, SourceDefinitionModel.name)
        )
    )
    if source_ids:
        sources = [source for source in sources if source.id in source_ids]
    if source_types:
        normalized = {source_type.casefold() for source_type in source_types}
        sources = [
            source for source in sources if source.source_type.casefold() in normalized
        ]
    return sources


async def _collect(
    session: Session,
    sources: list[SourceDefinitionModel],
    *,
    mode: CollectionMode,
    keywords: tuple[str, ...],
    max_items: int | None,
    correlation_id: str | None,
) -> list[dict[str, Any]]:
    service = AcquisitionService(session)
    report: list[dict[str, Any]] = []
    for source in sources:
        try:
            collector = service.registry.resolve(source.source_type)
            supported_keywords = (
                keywords if collector.capabilities.keyword_search else ()
            )
            run = await service.execute(
                source.id,
                CollectionRequest(
                    source_definition_id=source.id,
                    mode=mode,
                    keywords=supported_keywords,
                    max_items=max_items,
                    correlation_id=correlation_id,
                ),
            )
            report.append(
                {
                    "source_id": str(source.id),
                    "source_name": source.name,
                    "source_type": source.source_type,
                    "run_id": str(run.id),
                    "status": run.status,
                    "items_seen": run.items_seen,
                    "items_persisted": run.items_persisted,
                    "items_skipped": run.items_skipped,
                    "items_invalid": run.items_invalid,
                    "http_requests": run.http_requests,
                    "retry_count": run.retry_count,
                    "error_code": run.error_code,
                    "error_summary": run.error_summary,
                    "keywords_skipped": bool(keywords and not supported_keywords),
                }
            )
        except AcquisitionError as error:
            report.append(
                {
                    "source_id": str(source.id),
                    "source_name": source.name,
                    "source_type": source.source_type,
                    "status": "ERROR",
                    "error_code": error.code.value,
                    "error_summary": error.summary,
                }
            )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--source-type", help="comma-separated source types")
    parser.add_argument("--keywords", help="comma-separated keywords for feed sources")
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in CollectionMode if mode is not CollectionMode.MANUAL],
        default=CollectionMode.DISCOVERY.value,
    )
    parser.add_argument("--max-items", type=int, choices=range(1, 10_001))
    parser.add_argument("--correlation-id", default="make-collect")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    try:
        source_ids = tuple(UUID(value) for value in args.source_id)
    except ValueError as error:
        parser.error(f"--source-id must contain UUIDs: {error}")
    mode = CollectionMode(args.mode)
    with Session(create_database_engine(database_url)) as session:
        sources = _sources(
            session,
            source_ids=source_ids,
            source_types=_split(args.source_type),
        )
        if not sources:
            print(
                json.dumps(
                    {
                        "status": "no_enabled_sources",
                        "hint": "run `make enable-sources TERMS_REVIEWED=1` first",
                        "runs": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2
        report = asyncio.run(
            _collect(
                session,
                sources,
                mode=mode,
                keywords=_split(args.keywords),
                max_items=args.max_items,
                correlation_id=args.correlation_id,
            )
        )
    failures = [
        item
        for item in report
        if item.get("status") in {"FAILED", "PARTIAL", "ERROR"}
    ]
    print(
        json.dumps(
            {"status": "partial" if failures else "completed", "runs": report},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
