"""Read-only, versioned source and content baseline reports (F51-01)."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from opportunity_radar.acquisition.models import RawItemModel, SourceDefinitionModel
from opportunity_radar.opportunities.models import OpportunityModel, SourceOccurrenceModel

BASELINE_VERSION = "source-baseline-v1"
COLLECTOR_VERSION = "source-baseline-collector-v1"
DESCRIPTION_RULE_VERSION = "useful-description-v1"
_HTML = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
_ERROR_TEXT = re.compile(
    r"\b(access denied|403 forbidden|404 not found|cloudflare|captcha|"
    r"enable javascript|temporarily unavailable|page not found)\b",
    re.IGNORECASE,
)
_BOILERPLATE = re.compile(
    r"^(?:apply now|read more|learn more|view job|view role|job description|"
    r"careers|cookie policy|privacy policy)[.!\s]*$",
    re.IGNORECASE,
)


def classify_description(description: str | None, title: str | None) -> dict[str, str]:
    """Classify only explicit text; missing text remains unmeasured/absent."""
    if description is None:
        return {
            "state": "missing",
            "reason": "null_description",
            "rule_version": DESCRIPTION_RULE_VERSION,
        }
    text = " ".join(description.split())
    if not text:
        return {
            "state": "invalid",
            "reason": "empty_description",
            "rule_version": DESCRIPTION_RULE_VERSION,
        }
    if _HTML.search(text):
        return {
            "state": "invalid",
            "reason": "html_residue",
            "rule_version": DESCRIPTION_RULE_VERSION,
        }
    if _ERROR_TEXT.search(text):
        return {
            "state": "invalid",
            "reason": "error_or_access_message",
            "rule_version": DESCRIPTION_RULE_VERSION,
        }
    if title and text.casefold().strip(" .!\n") == title.casefold().strip(" .!\n"):
        return {
            "state": "invalid",
            "reason": "title_only",
            "rule_version": DESCRIPTION_RULE_VERSION,
        }
    if _BOILERPLATE.fullmatch(text):
        return {
            "state": "invalid",
            "reason": "boilerplate",
            "rule_version": DESCRIPTION_RULE_VERSION,
        }
    return {"state": "useful", "reason": "text_passes_v1", "rule_version": DESCRIPTION_RULE_VERSION}


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def opportunity_search_payload_hash(row: dict[str, Any]) -> str:
    """Hash every persisted field contributing to generated full-text search."""
    fields = (
        "canonical_title",
        "company_name",
        "search_skills",
        "role_family",
        "description",
        "location_text",
        "search_document",
    )
    return _digest({key: row.get(key) for key in fields})


def baseline_query_hash(definition: dict[str, Any], implementation_hash: str) -> str:
    """Hash collector implementation and declared filters; this is not compiled SQL."""
    return _digest({"definition": definition, "implementation_hash": implementation_hash})


def build_source_baseline(
    session: Session,
    *,
    captured_at: datetime,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> dict[str, Any]:
    """Read populations separately and return a deterministic, auditable snapshot."""
    sources = session.execute(
        select(
            SourceDefinitionModel.id, SourceDefinitionModel.name, SourceDefinitionModel.version
        ).order_by(SourceDefinitionModel.id)
    ).all()
    raw_stmt = select(RawItemModel.source_definition_id, func.count(RawItemModel.id)).group_by(
        RawItemModel.source_definition_id
    )
    occurrence_stmt = select(
        SourceOccurrenceModel.source_definition_id, func.count(SourceOccurrenceModel.id)
    ).group_by(SourceOccurrenceModel.source_definition_id)
    canonical_count_stmt = select(
        SourceOccurrenceModel.source_definition_id,
        func.count(func.distinct(SourceOccurrenceModel.opportunity_id)),
    ).group_by(SourceOccurrenceModel.source_definition_id)
    if window_start is not None:
        raw_stmt = raw_stmt.where(RawItemModel.fetched_at >= window_start)
        occurrence_stmt = occurrence_stmt.where(SourceOccurrenceModel.first_seen_at >= window_start)
        canonical_count_stmt = canonical_count_stmt.where(
            SourceOccurrenceModel.first_seen_at >= window_start
        )
    if window_end is not None:
        raw_stmt = raw_stmt.where(RawItemModel.fetched_at < window_end)
        occurrence_stmt = occurrence_stmt.where(SourceOccurrenceModel.first_seen_at < window_end)
        canonical_count_stmt = canonical_count_stmt.where(
            SourceOccurrenceModel.first_seen_at < window_end
        )
    raw_counts: dict[Any, int] = {
        source_id: int(count) for source_id, count in session.execute(raw_stmt).all()
    }
    occurrence_counts: dict[Any, int] = {
        source_id: int(count) for source_id, count in session.execute(occurrence_stmt).all()
    }
    canonical_counts: dict[Any, int] = {
        source_id: int(count) for source_id, count in session.execute(canonical_count_stmt).all()
    }
    quality_stmt = select(
        SourceOccurrenceModel.source_definition_id,
        OpportunityModel.description,
        OpportunityModel.canonical_title,
    ).join(OpportunityModel, OpportunityModel.id == SourceOccurrenceModel.opportunity_id)
    if window_start is not None:
        quality_stmt = quality_stmt.where(SourceOccurrenceModel.first_seen_at >= window_start)
    if window_end is not None:
        quality_stmt = quality_stmt.where(SourceOccurrenceModel.first_seen_at < window_end)
    quality_rows = session.execute(quality_stmt).all()
    quality: dict[Any, Counter[str]] = {}
    for source_id, description, title in quality_rows:
        state = classify_description(description, title)["state"]
        quality.setdefault(source_id, Counter())[state] += 1

    by_source = [
        {
            "source_id": str(source_id),
            "source_name": name,
            "source_version": version,
            "raw_items": {"count": int(raw_counts.get(source_id, 0)), "unit": "raw_item"},
            "occurrences": {
                "count": int(occurrence_counts.get(source_id, 0)),
                "unit": "source_occurrence",
            },
            "canonical_opportunities": {
                "count": int(canonical_counts.get(source_id, 0)),
                "unit": "opportunity",
                "scope": "distinct_opportunities_with_source_occurrence",
                "status": "measured_nonexclusive_source_counts",
            },
            "occurrence_descriptions": dict(quality.get(source_id, {})),
        }
        for source_id, name, version in sources
    ]
    corpus_rows = session.execute(
        select(
            OpportunityModel.id,
            OpportunityModel.canonical_title,
            OpportunityModel.company_name,
            OpportunityModel.search_skills,
            OpportunityModel.role_family,
            OpportunityModel.description,
            OpportunityModel.location_text,
            OpportunityModel.search_document,
        ).order_by(OpportunityModel.id)
    ).all()
    corpus = [
        {
            "opportunity_id": str(row.id),
            "payload_hash": opportunity_search_payload_hash(
                {
                    "canonical_title": row.canonical_title,
                    "company_name": row.company_name,
                    "search_skills": row.search_skills,
                    "role_family": row.role_family,
                    "description": row.description,
                    "location_text": row.location_text,
                    "search_document": str(row.search_document)
                    if row.search_document is not None
                    else None,
                }
            ),
        }
        for row in corpus_rows
    ]
    canonical_quality = Counter(
        classify_description(row.description, row.canonical_title)["state"] for row in corpus_rows
    )
    definition: dict[str, Any] = {
        "version": BASELINE_VERSION,
        "collector_version": COLLECTOR_VERSION,
        "description_rule_version": DESCRIPTION_RULE_VERSION,
        "window_start": window_start,
        "window_end": window_end,
        "units": ["raw_item", "source_occurrence", "opportunity"],
        "filters": {
            "window_timestamp": {"raw_item": "fetched_at", "source_occurrence": "first_seen_at"}
        },
        "canonical_scope": "full_opportunity_catalog_at_repeatable_read_snapshot",
        "source_canonical_attribution": (
            "distinct_per_source_via_occurrences; counts_overlap_and_must_not_be_summed"
        ),
        "collector_implementation_hash": _digest(
            {
                name: inspect.getsource(function)
                for name, function in (
                    ("build_source_baseline", build_source_baseline),
                    ("classify_description", classify_description),
                    ("opportunity_search_payload_hash", opportunity_search_payload_hash),
                )
            }
        ),
    }
    return {
        **definition,
        "captured_at": captured_at,
        "query_hash": baseline_query_hash(definition, definition["collector_implementation_hash"]),
        "source_count": len(by_source),
        "by_source": by_source,
        "corpus": corpus,
        "canonical_opportunities": {
            "count": len(corpus_rows),
            "description_useful_count": canonical_quality["useful"],
            "description_missing_count": canonical_quality["missing"],
            "description_invalid_count": canonical_quality["invalid"],
            "description_rule_version": DESCRIPTION_RULE_VERSION,
        },
        "complete_inventory_runs": None,
        "complete_inventory_status": "not_included_in_this_population_query",
    }


def write_immutable_json(path: str, report: dict[str, Any]) -> None:
    """Create a report once; never silently replace a prior baseline artifact."""
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2, default=str)
        handle.write("\n")
