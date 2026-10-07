"""Pilot and backfill of Workday job descriptions for one source (card F51-05).

    # what would be fetched and why each posting is in or out (no HTTP, writes nothing)
    python scripts/workday_detail_backfill.py --source-id <uuid>
    # fetch the details and write them; the manifest is written first and after every posting
    python scripts/workday_detail_backfill.py --source-id <uuid> --apply \
        --manifest data/backfill/<source>.json --max-requests 20
    # undo one manifest: only descriptions that still equal what it wrote
    python scripts/workday_detail_backfill.py --source-id <uuid> --apply --rollback \
        --manifest data/backfill/<source>.json

Refuses a source that is not a Workday source with `fetch_detail` on and a valid `detail_approval`
(owner, hostname, terms reference, decision), the same gate the collection run applies. Every
HTTP request goes through the host budget reservation and the persisted 429 cooldown of
`WorkdayCollector`; the run stops at the first cooldown, quota or cap, and a rerun with the same
manifest resumes. Only `opportunity.description` is written, and only while it is still empty:
a description present at apply time is a conflict and is left as it is. Presence, timestamps,
`updated_at`, the raw payload and the occurrences are not touched, and no source run is created,
so a backfill is never an inventory. Skills and seniority are recomputed from the written
description (the retag scripts read raw evidence, which a backfill does not touch); rollback
restores only the description.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.domain import CollectedItem, CollectionRequest
from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel
from opportunity_radar.acquisition.repository import AcquisitionRepository
from opportunity_radar.acquisition.service import (
    DEFAULT_HOST_CEILING_BY_SOURCE_TYPE,
    _budget_host_for_source,
    _collector_settings,
    _detail_settings,
    _source_network_policy,
    _workday_detail_approval,
    active_profile_target_role_families,
)
from opportunity_radar.acquisition.workday import _PARSER_VERSION, WorkdayCollector, _DetailRun
from opportunity_radar.companies.models import CompanySource  # noqa: F401
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel
from opportunity_radar.opportunities.service import recompute_from_stored_description
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine

MANIFEST_VERSION = "workday-backfill-manifest-v1"
#: A skip reason that ends the run: the budget, the cap or the cooldown will not clear by retrying.
_STOPPING_REASONS = frozenset({"cooldown", "cap", "quota"})


class BackfillRefused(Exception):
    """The source is not explicitly allowed for detail fetch, or the manifest does not fit it."""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _empty(description: str | None) -> bool:
    return description is None or not description.strip()


def _require_allowed(source: SourceDefinitionModel | None) -> tuple[str, str, str, int]:
    """`(tenant, site, pod, detail_max_requests)` or `BackfillRefused`."""
    if source is None:
        raise BackfillRefused("source not found")
    if source.source_type != "workday":
        raise BackfillRefused(f"source type is {source.source_type}, not workday")
    fetch_detail, detail_max_requests = _detail_settings(source.configuration, "workday")
    if not fetch_detail:
        raise BackfillRefused("source configuration does not enable fetch_detail")
    company_reference, _, api_region = _collector_settings(source)
    approved, reason = _workday_detail_approval(
        source.configuration, source.id, company_reference, api_region
    )
    if not approved:
        raise BackfillRefused(f"detail fetch is not approved for this source: {reason}")
    tenant, site = WorkdayCollector.validate_tenant_identifier(company_reference)
    return tenant, site, WorkdayCollector.validate_pod(api_region), detail_max_requests


def _load_manifest(path: Path | None, source_id: UUID) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("version") != MANIFEST_VERSION
        or manifest.get("source_id") != str(source_id)
        or manifest.get("parser_version") != _PARSER_VERSION
    ):
        raise BackfillRefused("manifest belongs to another source, parser version or format")
    return manifest


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(temporary, path)


def _select_targets(
    session: Session,
    source: SourceDefinitionModel,
    role_families: Sequence[str],
    done: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(targets, decisions)`: every occurrence of the source with the reason it is in or out."""
    rows = session.execute(
        select(SourceOccurrenceModel, OpportunityModel, RawItemModel.payload_hash)
        .join(OpportunityModel, OpportunityModel.id == SourceOccurrenceModel.opportunity_id)
        .join(RawItemModel, RawItemModel.id == SourceOccurrenceModel.raw_item_id)
        .where(SourceOccurrenceModel.source_definition_id == source.id)
        .order_by(SourceOccurrenceModel.external_id, SourceOccurrenceModel.id)
    ).all()
    targets: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    claimed: set[UUID] = set()
    for occurrence, opportunity, payload_hash in rows:
        key = occurrence.external_id
        if not key:
            reason = "no_external_id"
        elif key in done:
            reason = "already_applied"
        elif not _empty(opportunity.description):
            reason = "description_present"
        elif opportunity.role_family not in role_families:
            reason = "role_family_off_target"
        elif opportunity.id in claimed:
            reason = "duplicate_opportunity"
        else:
            reason = "description_missing"
            claimed.add(opportunity.id)
            targets.append(
                {
                    "key": key,
                    "opportunity_id": str(opportunity.id),
                    "occurrence_id": str(occurrence.id),
                    "url": occurrence.source_url,
                    "title": opportunity.canonical_title,
                    "company_name": opportunity.company_name,
                    "backup": {
                        "description": opportunity.description,
                        "version": opportunity.version,
                        "raw_item_id": str(occurrence.raw_item_id),
                        "raw_payload_hash": payload_hash,
                    },
                }
            )
        decisions.append(
            {
                "key": key,
                "opportunity_id": str(opportunity.id),
                "included": reason == "description_missing",
                "reason": reason,
            }
        )
    return targets, decisions


def _write_description(session: Session, opportunity_id: str, description: str) -> bool:
    """Write while the description is still empty; `False` is a conflict, nothing changed."""
    result = session.execute(
        update(OpportunityModel)
        .where(
            OpportunityModel.id == UUID(opportunity_id),
            (OpportunityModel.description.is_(None))
            | (func.btrim(OpportunityModel.description) == ""),
        )
        .values(
            description=description,
            version=OpportunityModel.version + 1,
            # An explicit value keeps the column's `onupdate` from moving it.
            updated_at=OpportunityModel.updated_at,
        )
    )
    session.commit()
    return bool(cast(CursorResult[Any], result).rowcount)


def _recompute_derived(session: Session, opportunity_id: str) -> bool:
    changed = recompute_from_stored_description(session, UUID(opportunity_id))
    session.commit()
    return changed


def run_backfill(
    session: Session,
    *,
    source_id: UUID,
    role_families: Sequence[str],
    apply: bool = False,
    max_requests: int | None = None,
    limit: int | None = None,
    manifest_path: Path | None = None,
    collector: WorkdayCollector | None = None,
    host_ceilings: dict[str, int] | None = None,
) -> dict[str, Any]:
    if apply and manifest_path is None:
        raise BackfillRefused("--apply needs --manifest")
    source = session.get(SourceDefinitionModel, source_id)
    tenant, site, pod, source_cap = _require_allowed(source)
    assert source is not None
    manifest = _load_manifest(manifest_path, source_id)
    entries: dict[str, dict[str, Any]] = (manifest or {}).get("entries", {})
    done = {key for key, entry in entries.items() if entry.get("status") == "applied"}
    targets, decisions = _select_targets(session, source, role_families, done)
    if limit is not None:
        targets = targets[:limit]
    cap = source_cap if max_requests is None else min(max_requests, source_cap)
    report: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "source_id": str(source_id),
        "parser_version": _PARSER_VERSION,
        "postings_seen": len(decisions),
        "excluded": dict(Counter(row["reason"] for row in decisions if not row["included"])),
        "eligible": len(targets),
        "max_requests": cap,
        "decisions": decisions,
    }
    if not apply:
        report["would_fetch"] = min(len(targets), cap)
        return report

    assert manifest_path is not None
    run_id = uuid4()
    manifest = {
        "version": MANIFEST_VERSION,
        "run_id": str(run_id),
        "source_id": str(source_id),
        "host": _budget_host_for_source(source.source_type, source.configuration),
        "parser_version": _PARSER_VERSION,
        "role_families": sorted(role_families),
        "max_requests": cap,
        "created_at": datetime.now(UTC).isoformat(),
        "entries": entries,
    }
    # The backup of every target, written before the first request or write.
    for target in targets:
        entries.setdefault(target["key"], {**target, "status": "planned"})
    _save_manifest(manifest_path, manifest)

    host = manifest["host"]
    ceiling = (host_ceilings or DEFAULT_HOST_CEILING_BY_SOURCE_TYPE)["workday"]
    engine = session.get_bind()

    def reserve(is_detail: bool) -> str | None:
        with Session(bind=engine) as budget_session:
            return AcquisitionRepository(budget_session).reserve_host_request(
                host,
                now=datetime.now(UTC),
                default_ceiling=ceiling,
                run_id=run_id,
                detail=is_detail,
            )

    def persist_cooldown(until: datetime) -> None:
        with Session(bind=engine) as budget_session:
            AcquisitionRepository(budget_session).persist_host_cooldown(host, until)

    request = CollectionRequest(
        company_reference=f"{tenant}/{site}",
        company_name=source.configuration.get("company_name"),
        api_region=pod,
        fetch_detail=True,
        detail_max_requests=cap,
        detail_approval_valid=True,
        target_role_families=tuple(role_families),
        reserve_http_request=reserve,
        persist_cooldown=persist_cooldown,
        network_policy=_source_network_policy(source.source_type, source.rate_limit_policy),
    )
    telemetry = request.telemetry
    detail = _DetailRun(request)
    outcomes = Counter[str]()
    skipped = Counter[str]()
    stopped_by: str | None = None
    attempted = 0

    async def fetch_all() -> None:
        nonlocal stopped_by, attempted
        runner = collector or WorkdayCollector()
        async with _client_for(runner) as client:
            for target in targets:
                entry = entries[target["key"]]
                item = CollectedItem(
                    source_type="workday",
                    raw_payload={},
                    external_id=target["key"],
                    url=target["url"],
                    title=target["title"],
                    company_name=target["company_name"],
                )
                skips_before = dict(telemetry.detail_skip_reasons)
                failures_before = telemetry.detail_failures
                attempted += 1
                result = await runner._with_detail(client, item, tenant, site, pod, request, detail)
                if result.description:
                    if _write_description(session, target["opportunity_id"], result.description):
                        entry.update(
                            status="applied",
                            description_sha256=_sha256(result.description),
                            written_at=datetime.now(UTC).isoformat(),
                        )
                        outcomes["applied"] += 1
                        if _recompute_derived(session, target["opportunity_id"]):
                            outcomes["derived_changed"] += 1
                    else:
                        entry["status"] = "conflict"
                        outcomes["conflict"] += 1
                elif telemetry.detail_skip_reasons != skips_before:
                    reason = next(
                        name
                        for name, count in telemetry.detail_skip_reasons.items()
                        if count != skips_before.get(name, 0)
                    )
                    entry.update(status="skipped", reason=reason)
                    skipped[reason] += 1
                    if reason in _STOPPING_REASONS:
                        stopped_by = reason
                elif telemetry.detail_failures != failures_before:
                    entry["status"] = "failed"
                    outcomes["failed"] += 1
                else:
                    entry["status"] = "no_description"
                    outcomes["no_description"] += 1
                _save_manifest(manifest_path, manifest)
                if detail.stopped and stopped_by is None:
                    stopped_by = "cooldown"  # a 429 persisted the cooldown
                if stopped_by is not None:
                    break

    asyncio.run(fetch_all())
    report.update(
        details_fetched=telemetry.detail_requests,
        http_requests=telemetry.http_requests,
        applied=outcomes["applied"],
        derived_changed=outcomes["derived_changed"],
        conflicts=outcomes["conflict"],
        failed=outcomes["failed"],
        no_description=outcomes["no_description"],
        skipped=dict(skipped),
        not_attempted=len(targets) - attempted,
        stopped_by=stopped_by,
        run_id=str(run_id),
    )
    return report


def _client_for(collector: WorkdayCollector) -> Any:
    """The collector's own client (a fake in tests) or one from its factory."""
    if collector._client is not None:
        return _Borrowed(collector._client)
    return collector._client_factory()


class _Borrowed:
    """Lends a client that its owner closes."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def __aenter__(self) -> Any:
        return self._client

    async def __aexit__(self, *exc: object) -> None:
        return None


def rollback(
    session: Session, *, source_id: UUID, manifest_path: Path, apply: bool = False
) -> dict[str, Any]:
    """Empty again the descriptions this manifest wrote, only where they still equal it."""
    manifest = _load_manifest(manifest_path, source_id)
    if manifest is None:
        raise BackfillRefused("manifest not found")
    restorable = conflicts = already = 0
    for key, entry in manifest["entries"].items():
        if entry.get("status") != "applied":
            continue
        opportunity = session.get(OpportunityModel, UUID(entry["opportunity_id"]))
        current = opportunity.description if opportunity is not None else None
        if current is None or _sha256(current) != entry.get("description_sha256"):
            if _empty(current):
                already += 1
            else:
                conflicts += 1
            continue
        restorable += 1
        if apply:
            session.execute(
                update(OpportunityModel)
                .where(OpportunityModel.id == UUID(entry["opportunity_id"]))
                .values(
                    description=entry["backup"]["description"],
                    version=OpportunityModel.version + 1,
                    updated_at=OpportunityModel.updated_at,
                )
            )
            entry["status"] = "rolled_back"
    if apply:
        session.commit()
        _save_manifest(manifest_path, manifest)
    return {
        "mode": "rollback-apply" if apply else "rollback-dry-run",
        "source_id": str(source_id),
        "restorable": restorable,
        "conflicts": conflicts,
        "already_empty": already,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source-id", type=UUID, required=True)
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry-run")
    parser.add_argument("--manifest", type=Path, help="required with --apply; resumed if present")
    parser.add_argument("--max-requests", type=int, help="at most N detail requests this run")
    parser.add_argument("--limit", type=int, help="at most N postings this run")
    parser.add_argument("--rollback", action="store_true", help="undo the manifest's writes")
    parser.add_argument("--explain", action="store_true", help="list the reason of every posting")
    args = parser.parse_args(argv)
    engine = create_database_engine(os.environ["DATABASE_URL"])
    try:
        with Session(engine) as session:
            if args.rollback:
                if args.manifest is None:
                    parser.error("--rollback needs --manifest")
                report = rollback(
                    session,
                    source_id=args.source_id,
                    manifest_path=args.manifest,
                    apply=args.apply,
                )
            else:
                families = active_profile_target_role_families(session)()
                if not families:
                    parser.error("the active profile has no target role family")
                report = run_backfill(
                    session,
                    source_id=args.source_id,
                    role_families=families,
                    apply=args.apply,
                    max_requests=args.max_requests,
                    limit=args.limit,
                    manifest_path=args.manifest,
                    host_ceilings=Settings().host_request_ceiling_map,
                )
    except BackfillRefused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2
    if not args.explain:
        report.pop("decisions", None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
