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

from opportunity_radar.acquisition.ashby import AshbyCollector
from opportunity_radar.acquisition.collectors import CollectorRegistry, ManualCollector
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    CollectedItem,
    CollectionRequest,
)
from opportunity_radar.acquisition.greenhouse import GreenhouseCollector
from opportunity_radar.acquisition.lever import LeverCollector
from opportunity_radar.acquisition.models import SourceDefinitionModel
from opportunity_radar.acquisition.remotive import RemotiveCollector
from opportunity_radar.companies.models import CompanySource  # noqa: F401
from opportunity_radar.platform.database import create_database_engine

RESEARCHED_TYPES = ("ashby", "lever", "greenhouse", "remotive")
PUBLIC_ENDPOINT_REFERENCES = {
    "ashby": "https://developers.ashbyhq.com/docs/public-job-posting-api",
    "greenhouse": "https://docs.greenhouse.io/job-board.html",
    "lever": "https://github.com/lever/postings-api",
    "remotive": "https://remotive.com/api-documentation",
}


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
    return CollectorRegistry(
        (
            ManualCollector(),
            AshbyCollector(),
            LeverCollector(),
            GreenhouseCollector(),
            RemotiveCollector(),
        )
    )


def _request(source: SourceDefinitionModel, *, max_items: int) -> CollectionRequest:
    configuration = source.configuration
    common: dict[str, Any] = {"max_items": max_items}
    if source.source_type == "ashby":
        common["company_reference"] = _required(configuration, "board_identifier")
        common["company_name"] = configuration.get("company_name")
    elif source.source_type == "lever":
        common["company_reference"] = _required(configuration, "site_identifier")
        common["company_name"] = configuration.get("company_name")
        common["api_region"] = configuration.get("api_region", "global")
    elif source.source_type == "greenhouse":
        common["company_reference"] = _required(configuration, "board_token")
        common["company_name"] = configuration.get("company_name")
    return CollectionRequest(**common)


def _required(configuration: dict[str, Any], key: str) -> str:
    value = configuration.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"configuration requires {key}")
    return value.strip()


async def _probe(
    source: SourceDefinitionModel,
    registry: CollectorRegistry,
    *,
    max_items: int,
) -> ProbeResult:
    telemetry_request: CollectionRequest | None = None
    try:
        telemetry_request = _request(source, max_items=max_items)
        collector = registry.resolve(source.source_type)
        items_seen = 0
        async for item in collector.discover(telemetry_request):
            if not isinstance(item, CollectedItem):
                raise TypeError("collector emitted an invalid item")
            items_seen += 1
            if items_seen >= max_items:
                break
        return ProbeResult(
            source_id=str(source.id),
            source_name=source.name,
            source_type=source.source_type,
            ok=True,
            detail="public endpoint responded and the collector parsed its schema",
            items_seen=items_seen,
            http_requests=telemetry_request.telemetry.http_requests,
        )
    except AcquisitionError as error:
        return ProbeResult(
            source_id=str(source.id),
            source_name=source.name,
            source_type=source.source_type,
            ok=False,
            detail=error.summary,
            error_code=error.code.value,
            http_requests=(
                telemetry_request.telemetry.http_requests if telemetry_request else 0
            ),
        )
    except (TypeError, ValueError) as error:
        return ProbeResult(
            source_id=str(source.id),
            source_name=source.name,
            source_type=source.source_type,
            ok=False,
            detail=str(error),
            error_code="INVALID_CONFIGURATION",
            http_requests=(
                telemetry_request.telemetry.http_requests if telemetry_request else 0
            ),
        )
    except Exception as error:
        return ProbeResult(
            source_id=str(source.id),
            source_name=source.name,
            source_type=source.source_type,
            ok=False,
            detail=str(error),
            error_code="UNKNOWN_EXTERNAL_ERROR",
            http_requests=(
                telemetry_request.telemetry.http_requests if telemetry_request else 0
            ),
        )


def _probe_candidate(source: SourceDefinitionModel, *, include_remotive: bool) -> bool:
    """A configured public endpoint can be probed before it is homologated."""
    if source.enabled or source.source_type not in RESEARCHED_TYPES:
        return False
    if source.source_type == "remotive":
        return include_remotive
    try:
        _request(source, max_items=1)
    except ValueError:
        return False
    return True


def _homologation_audit(result: ProbeResult, reviewed_at: datetime) -> dict[str, Any]:
    """Keep the operator-approved gate and its technical proof with the source."""
    return {
        "public_endpoint_reference": PUBLIC_ENDPOINT_REFERENCES[result.source_type],
        "terms_review": "operator-confirmed via --accept-terms",
        "reviewed_at": reviewed_at.isoformat(),
        "collector_local_test": {
            "status": "passed",
            "items_seen": result.items_seen,
            "http_requests": result.http_requests,
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
    results = asyncio.run(
        _probe_all(candidates, registry, max_items=max_items)
    )
    if probe_only:
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
            "homologation_audit": _homologation_audit(result, reviewed_at),
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
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for source in sources:
        results.append(await _probe(source, registry, max_items=max_items))
    return results


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
            )
        except ValueError as error:
            parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["status"] in {"dry_run", "probe_completed", "completed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
