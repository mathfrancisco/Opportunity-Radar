"""Run every enabled source and preserve a JSON summary for operators."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.concurrency import HostSerializer, source_host_key
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    CollectionMode,
    CollectionRequest,
)
from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import (
    AcquisitionService,
    active_profile_target_role_families,
)
from opportunity_radar.companies.models import CompanySource  # noqa: F401
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.profile.domain import ProfileNotFoundError
from opportunity_radar.profile.service import ProfileService

#: Sources collected at once, default 1 (current sequential behavior unchanged). Same-
#: host work still serializes at 1 request/second regardless of this setting.
DEFAULT_COLLECT_CONCURRENCY = 1


NO_ACTIVE_PROFILE = "no_active_profile"


def active_profile_accepted_seniorities(session: Session) -> tuple[str, ...] | None:
    """The active profile's `accepted_seniorities` without `UNKNOWN` (F52-09).

    `None` when there is no active profile or it names no level: the report then says it
    cannot tell, instead of counting everything or nothing as the accepted level.
    """
    try:
        profile = ProfileService(session).get_active()
    except ProfileNotFoundError:
        return None
    accepted = tuple(
        level
        for level in profile.snapshot.preferences.accepted_seniorities
        if level != "UNKNOWN"
    )
    return accepted or None


def level_counts_by_run(
    session: Session, run_ids: Sequence[UUID], accepted: Sequence[str]
) -> dict[UUID, dict[str, int]]:
    """Per run: postings its raw items normalized into, and how many have an accepted level.

    A posting counts once per run. Raw items the normalizer has not reached yet are not in
    either number (normalization runs after collection), so a fresh run can read low until
    the worker catches up.
    """
    counts = {run_id: {"postings": 0, "accepted_level": 0} for run_id in run_ids}
    if not run_ids:
        return counts
    rows = session.execute(
        select(
            RawItemModel.source_run_id,
            OpportunityModel.seniority,
            func.count(distinct(OpportunityModel.id)),
        )
        .join(SourceOccurrenceModel, SourceOccurrenceModel.raw_item_id == RawItemModel.id)
        .join(OpportunityModel, OpportunityModel.id == SourceOccurrenceModel.opportunity_id)
        .where(RawItemModel.source_run_id.in_(list(run_ids)))
        .group_by(RawItemModel.source_run_id, OpportunityModel.seniority)
    ).all()
    for run_id, seniority, total in rows:
        counts[run_id]["postings"] += total
        if seniority in accepted:
            counts[run_id]["accepted_level"] += total
    return counts


def add_level_column(
    session: Session, runs: list[dict[str, Any]], accepted: tuple[str, ...] | None
) -> dict[str, Any]:
    """Put an `accepted_level` entry on every run that has a `run_id`; return the summary.

    No active profile: every entry says `no_active_profile` and nothing is counted. The
    summary is the total over the runs of this execution.
    """
    run_ids = [UUID(item["run_id"]) for item in runs if item.get("run_id")]
    if accepted is None:
        for item in runs:
            item["accepted_level"] = {"status": NO_ACTIVE_PROFILE}
        return {"status": NO_ACTIVE_PROFILE}
    counts = level_counts_by_run(session, run_ids, accepted)
    total = {"postings": 0, "accepted_level": 0}
    for item in runs:
        if not item.get("run_id"):
            item["accepted_level"] = {"status": "no_run"}
            continue
        found = counts[UUID(item["run_id"])]
        item["accepted_level"] = {"status": "ok", **found}
        total["postings"] += found["postings"]
        total["accepted_level"] += found["accepted_level"]
    return {"status": "ok", "accepted_seniorities": list(accepted), **total}


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


def _registry(settings: Settings) -> CollectorRegistry:
    # AcquisitionService's own default registry only knows the five original collectors
    # (manual/ashby/lever/greenhouse/remotive) — every collector added since (workday,
    # teamtailor, workable, factorial, tavily_search) is registered by
    # `build_collector_registry`, the same one the worker uses (worker.py's
    # `collection_service_factory`). Without this, `make collect` could resolve a
    # homologated Workday/Teamtailor/Workable/Factorial source's own collector code
    # correctly in a probe but fail every real run here with "collector is not
    # registered" (found live against a real Teamtailor source during F20 homologation).
    return build_collector_registry(
        greenhouse_base_url=settings.greenhouse_base_url,
        tavily_api_key=settings.tavily_api_key,
        tavily_base_url=settings.tavily_base_url,
        tavily_search_depth=settings.tavily_search_depth,
        tavily_credit_budget_per_run=settings.tavily_credit_budget_per_run,
    )


async def _collect_one(
    engine: Engine,
    source: SourceDefinitionModel,
    *,
    mode: CollectionMode,
    keywords: tuple[str, ...],
    max_items: int | None,
    correlation_id: str | None,
    settings: Settings,
) -> dict[str, Any]:
    """One source, its own `Session` (never shared across concurrent tasks) and its own
    registry instance. Any failure — not only `AcquisitionError` — is caught here and
    reported as `ERROR`, so one bad source never sinks the batch."""
    try:
        with Session(engine) as session:
            service = AcquisitionService(
                session,
                registry=_registry(settings),
                target_role_families=active_profile_target_role_families(session),
                target_area_floor=settings.collection_target_area_floor,
            )
            collector = service.registry.resolve(source.source_type)
            supported_keywords = keywords if collector.capabilities.keyword_search else ()
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
            return {
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
    except AcquisitionError as error:
        return {
            "source_id": str(source.id),
            "source_name": source.name,
            "source_type": source.source_type,
            "status": "ERROR",
            "error_code": error.code.value,
            "error_summary": error.summary,
        }
    except Exception as error:  # noqa: BLE001 - one source's failure never sinks the batch
        return {
            "source_id": str(source.id),
            "source_name": source.name,
            "source_type": source.source_type,
            "status": "ERROR",
            "error_code": "UNKNOWN_ERROR",
            "error_summary": str(error),
        }


async def _collect(
    engine: Engine,
    sources: list[SourceDefinitionModel],
    *,
    mode: CollectionMode,
    keywords: tuple[str, ...],
    max_items: int | None,
    correlation_id: str | None,
    settings: Settings,
    concurrency: int = DEFAULT_COLLECT_CONCURRENCY,
) -> list[dict[str, Any]]:
    """Collect every source concurrently, up to `concurrency` at once (default 1: the
    original sequential behavior). Two sources on the same provider host
    (`source_host_key`) still serialize behind that host's own lock at 1 request/second.
    `asyncio.gather` preserves `sources`' order in the result regardless of completion
    order, so the report's shape and ordering are unchanged from the sequential run."""
    host_serializer = HostSerializer(min_interval_seconds=1.0)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(source: SourceDefinitionModel) -> dict[str, Any]:
        host = source_host_key(source.source_type, source.configuration)
        async with semaphore, host_serializer.lock_for(host):
            await host_serializer.wait_turn(host)
            return await _collect_one(
                engine,
                source,
                mode=mode,
                keywords=keywords,
                max_items=max_items,
                correlation_id=correlation_id,
                settings=settings,
            )

    return list(await asyncio.gather(*(run_one(source) for source in sources)))


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
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_COLLECT_CONCURRENCY,
        help="Sources collected at once; same-host work still serializes at 1 "
        f"request/second (default: {DEFAULT_COLLECT_CONCURRENCY}, current behavior).",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    try:
        source_ids = tuple(UUID(value) for value in args.source_id)
    except ValueError as error:
        parser.error(f"--source-id must contain UUIDs: {error}")
    mode = CollectionMode(args.mode)
    engine = create_database_engine(database_url)
    with Session(engine) as session:
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
    settings = Settings()  # type: ignore[call-arg]  # values come from the environment
    report = asyncio.run(
        _collect(
            engine,
            sources,
            mode=mode,
            keywords=_split(args.keywords),
            max_items=args.max_items,
            correlation_id=args.correlation_id,
            settings=settings,
            concurrency=args.concurrency,
        )
    )
    failures = [
        item
        for item in report
        if item.get("status") in {"FAILED", "PARTIAL", "ERROR"}
    ]
    try:
        with Session(engine) as session:
            level = add_level_column(
                session, report, active_profile_accepted_seniorities(session)
            )
    except Exception as error:  # noqa: BLE001 - the level column never fails the run
        level = {"status": "unavailable", "error_summary": str(error)}
    print(
        json.dumps(
            {
                "status": "partial" if failures else "completed",
                "accepted_level": level,
                "runs": report,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
