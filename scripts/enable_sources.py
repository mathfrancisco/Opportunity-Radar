"""Probe and enable the researched public job sources."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.concurrency import HostSerializer, source_host_key
from opportunity_radar.acquisition.forbidden import forbidden_platform_in
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.probing import (
    PROBE_TYPES,
    PUBLIC_ENDPOINT_REFERENCES,
    ProbeOutcome,
    probe_request,
    run_probe,
)
from opportunity_radar.acquisition.registry import build_collector_registry
from opportunity_radar.acquisition.service import AcquisitionService
from opportunity_radar.companies.models import CompanySource  # noqa: F401
from opportunity_radar.platform.database import create_database_engine

RESEARCHED_TYPES = PROBE_TYPES

#: How many sources may be probed at once. Different providers/tenants run concurrently;
#: same-host work still serializes at 1 request/second (`HostSerializer`).
DEFAULT_PROBE_CONCURRENCY = 8


@dataclass(frozen=True, slots=True)
class ProbeResult:
    source_id: str
    source_name: str
    source_type: str
    ok: bool
    detail: str
    items_seen: int = 0
    http_requests: int = 0
    error_code: str | None = None
    outcome: ProbeOutcome | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "ok": self.ok,
            "detail": self.detail,
            "items_seen": self.items_seen,
            "http_requests": self.http_requests,
            "error_code": self.error_code,
        }


def _registry() -> CollectorRegistry:
    return build_collector_registry(
        greenhouse_base_url=os.environ.get(
            "GREENHOUSE_BASE_URL", "https://boards-api.greenhouse.io"
        )
    )


async def _probe(
    source: SourceDefinitionModel,
    registry: CollectorRegistry,
    *,
    max_items: int,
) -> ProbeResult:
    """The domain's probe, the same one the interface runs, reported for this script."""
    outcome = await run_probe(
        source.source_type,
        dict(source.configuration or {}),
        registry,
        max_items=max_items,
    )
    return ProbeResult(
        source_id=str(source.id),
        source_name=source.name,
        source_type=source.source_type,
        ok=outcome.ok,
        detail=outcome.detail,
        items_seen=outcome.items_seen,
        http_requests=outcome.http_requests,
        error_code=outcome.error_code,
        outcome=outcome,
    )


def _probe_candidate(source: SourceDefinitionModel, *, include_remotive: bool) -> bool:
    """A configured public endpoint can be probed before it is homologated."""
    if source.enabled or source.source_type not in RESEARCHED_TYPES:
        return False
    # F48-19: a source that touches a forbidden platform is never probed or enabled.
    if forbidden_platform_in(source.configuration or {}) is not None:
        return False
    if source.source_type == "remotive":
        return include_remotive
    try:
        probe_request(source.source_type, dict(source.configuration or {}), max_items=1)
    except ValueError:
        return False
    return True


def _homologation_audit(
    result: ProbeResult, reviewed_at: datetime, *, probe_id: str | None = None
) -> dict[str, Any]:
    """Keep the operator-approved gate and its technical proof with the source."""
    return {
        "public_endpoint_reference": PUBLIC_ENDPOINT_REFERENCES[result.source_type],
        "terms_review": "operator-confirmed via --accept-terms",
        "reviewed_at": reviewed_at.isoformat(),
        "collector_local_test": {
            "status": "passed",
            "items_seen": result.items_seen,
            "http_requests": result.http_requests,
            **({"probe_id": probe_id} if probe_id is not None else {}),
        },
    }


def activate_sources(
    session: Session,
    *,
    accept_terms: bool,
    include_remotive: bool,
    dry_run: bool,
    max_items: int,
    probe_only: bool = False,
    concurrency: int = DEFAULT_PROBE_CONCURRENCY,
) -> dict[str, Any]:
    if not accept_terms and not probe_only:
        raise ValueError(
            "pass --accept-terms after reviewing the public source terms before enabling"
        )
    sources = list(
        session.scalars(
            select(SourceDefinitionModel)
            .where(SourceDefinitionModel.enabled.is_(False))
            .order_by(SourceDefinitionModel.priority, SourceDefinitionModel.name)
        )
    )
    candidates = [
        source
        for source in sources
        if _probe_candidate(source, include_remotive=include_remotive)
    ]
    if dry_run:
        return {
            "status": "dry_run",
            "candidates": [
                {"id": str(source.id), "name": source.name, "source_type": source.source_type}
                for source in candidates
            ],
        }

    registry = _registry()
    probes_started_at = datetime.now(UTC)
    results = asyncio.run(
        _probe_all(candidates, registry, max_items=max_items, concurrency=concurrency)
    )
    # Every attempt joins the same history the interface writes, passed or failed.
    service = AcquisitionService(session, registry=registry)
    probe_ids: dict[str, str] = {}
    for source, result in zip(candidates, results, strict=True):
        if result.outcome is None:
            continue
        probe = service.record_script_probe(
            source,
            result.outcome,
            probes_started_at,
            evidence_recorded=result.ok and not probe_only,
        )
        probe_ids[str(source.id)] = str(probe.id)
    if probe_only:
        session.commit()
        return {
            "status": "probe_completed",
            "candidates": len(candidates),
            "probes": [result.as_dict() for result in results],
        }
    activated: list[str] = []
    for source, result in zip(candidates, results, strict=True):
        if not result.ok:
            continue
        reviewed_at = datetime.now(UTC)
        source.enabled = True
        source.evidence_status = "confirmed"
        source.reviewed_at = reviewed_at
        source.terms_reviewed = True
        source.collector_local_tested = True
        source.configuration = {
            **source.configuration,
            "homologation_audit": _homologation_audit(
                result, reviewed_at, probe_id=probe_ids.get(str(source.id))
            ),
        }
        source.version += 1
        activated.append(source.name)
    session.commit()
    return {
        "status": "completed",
        "candidates": len(candidates),
        "activated": activated,
        "probes": [result.as_dict() for result in results],
    }


async def _probe_all(
    sources: list[SourceDefinitionModel],
    registry: CollectorRegistry,
    *,
    max_items: int,
    concurrency: int = DEFAULT_PROBE_CONCURRENCY,
) -> list[ProbeResult]:
    """Probe every source concurrently, up to `concurrency` at once. Two sources on the
    same provider host (`source_host_key`) still serialize behind that host's own lock,
    at 1 request/second — `asyncio.gather` preserves `sources`' order in the result
    regardless of completion order, so callers may keep zipping it against `sources`."""
    host_serializer = HostSerializer(min_interval_seconds=1.0)
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_one(source: SourceDefinitionModel) -> ProbeResult:
        host = source_host_key(source.source_type, source.configuration)
        async with semaphore, host_serializer.lock_for(host):
            await host_serializer.wait_turn(host)
            return await _probe(source, registry, max_items=max_items)

    return list(await asyncio.gather(*(run_one(source) for source in sources)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--accept-terms",
        action="store_true",
        help="confirm that the public source terms were reviewed",
    )
    parser.add_argument(
        "--exclude-remotive",
        action="store_true",
        help="leave the public Remotive feed disabled",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="test public endpoints without recording terms or enabling sources",
    )
    parser.add_argument("--max-items", type=int, default=1, choices=range(1, 11))
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_PROBE_CONCURRENCY,
        help="Sources probed at once; same-host work still serializes at 1 "
        f"request/second (default: {DEFAULT_PROBE_CONCURRENCY}).",
    )
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required.")
    with Session(create_database_engine(database_url)) as session:
        try:
            report = activate_sources(
                session,
                accept_terms=args.accept_terms,
                include_remotive=not args.exclude_remotive,
                dry_run=args.dry_run,
                max_items=args.max_items,
                probe_only=args.probe_only,
                concurrency=args.concurrency,
            )
        except ValueError as error:
            parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["status"] in {"dry_run", "probe_completed", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
