"""Per-adapter inventory contracts and the scope a cached 304 may speak for (F51-13).

The matrix records what each collector really does, read from its implementation and its
fixtures. A value nobody verified is `NOT_VERIFIABLE`, never presumed. `CollectorCapabilities`
stays the machine-readable source for pagination and validators; a test ties both together.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

#: Bump when what a validator, cursor or hash is allowed to prove changes: every cached
#: validator stored under an older version stops being compatible and is re-read in full.
INVENTORY_CONTRACT_VERSION: Final = "inventory-contract-v1"

NOT_VERIFIABLE: Final = "not_verifiable"

PAGINATION_NONE: Final = "none"
PAGINATION_OFFSET: Final = "offset"
PAGINATION_CURSOR: Final = "cursor"


@dataclass(frozen=True, slots=True)
class InventoryContract:
    source_type: str
    #: `none`, `offset` or `cursor`: the mechanism the endpoint really has.
    pagination: str
    #: What ends the listing.
    termination: str
    #: What the collector reports as `items_announced`: `known` (the endpoint states it or
    #: one answer is the whole board), `derived` (the collector's own exhaustive count),
    #: `unknown` (never reported). An absent total is never zero.
    announced_total: str
    #: The collector's own per-request ceiling, if any.
    local_limit: str
    #: What a 304 on this adapter can speak for.
    not_modified_scope: str
    #: When a run of this adapter counts as complete.
    complete_run: str
    #: What happens to presence when a request fails after valid evidence.
    on_error: str


_ERROR_AFTER_EVIDENCE = (
    "items already seen stay observed; the run is partial and closes no absence"
)
_SINGLE_SHOT = "single response; a bare 304 revalidates that one representation"

INVENTORY_CONTRACTS: Final[dict[str, InventoryContract]] = {
    contract.source_type: contract
    for contract in (
        InventoryContract(
            "workday",
            PAGINATION_OFFSET,
            "short page, announced total reached (read from offset 0 only, capped by "
            "Workday), or a repeated page / no new posting (error)",
            "derived: total_fetched on a clean end; the endpoint's own total is not trusted "
            "as the announced count; zero only from a valid empty first page",
            "page size 20; max_items",
            "offset 0 only; validators are never sent for a resumed cursor",
            "SUCCEEDED, max_items unset, whole board read",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "lever",
            PAGINATION_OFFSET,
            "short page, or a repeated page / no new posting (error)",
            "derived: total_fetched on a short final page; no field states a total",
            "page size 100; max_items",
            "first page (skip 0) only",
            "SUCCEEDED, max_items unset, whole board read",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "teamtailor",
            PAGINATION_NONE,
            "one feed response",
            "derived: item count of the single response, only when max_items is unset",
            "max_items",
            _SINGLE_SHOT,
            "SUCCEEDED, max_items unset, single response parsed",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "workable",
            PAGINATION_NONE,
            "one widget response",
            "derived: items emitted from the single response, only when it was fully read",
            "max_items",
            _SINGLE_SHOT,
            "SUCCEEDED, max_items unset, single response parsed",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "factorial",
            PAGINATION_NONE,
            "one page response",
            "derived: job count of the single response, only when max_items is unset",
            "max_items",
            _SINGLE_SHOT,
            "SUCCEEDED, max_items unset, single response parsed",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "greenhouse",
            PAGINATION_NONE,
            "one boards-api response",
            "known: meta.total, non-negative integer required (0 is an explicit zero)",
            "max_items",
            _SINGLE_SHOT,
            "SUCCEEDED, max_items unset, items_seen reached meta.total",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "ashby",
            PAGINATION_NONE,
            "one job-board response",
            "derived: job count of the single response",
            "max_items",
            _SINGLE_SHOT,
            "SUCCEEDED, max_items unset, single response parsed",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "remotive",
            PAGINATION_NONE,
            "one search response (keywords are part of the query)",
            "unknown: never reported",
            "max_items is sent as the request limit",
            _SINGLE_SHOT,
            "SUCCEEDED and max_items unset; no total to cross-check",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "inhire",
            PAGINATION_NONE,
            "one list call (no pagination observed)",
            "derived: size of the list; an empty list is a valid empty board",
            NOT_VERIFIABLE,
            "no validators: the adapter does not declare etag or last_modified",
            "SUCCEEDED, max_items unset, list parsed",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "jobposting",
            PAGINATION_NONE,
            NOT_VERIFIABLE,
            "unknown: never reported",
            NOT_VERIFIABLE,
            "no validators: the adapter does not declare etag or last_modified",
            NOT_VERIFIABLE,
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "hacker_news",
            PAGINATION_NONE,
            NOT_VERIFIABLE,
            "derived: live comment count, only when no keyword filter is active",
            NOT_VERIFIABLE,
            "no validators: the adapter does not declare etag or last_modified",
            "SUCCEEDED, max_items unset, no keyword filter",
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "tavily_search",
            PAGINATION_NONE,
            "search results, bounded by the per-run credit budget",
            "unknown: never reported",
            "credit budget per run",
            "no validators: the adapter does not declare etag or last_modified",
            NOT_VERIFIABLE,
            _ERROR_AFTER_EVIDENCE,
        ),
        InventoryContract(
            "manual",
            PAGINATION_NONE,
            "the submitted inputs",
            "unknown: never reported",
            NOT_VERIFIABLE,
            "no validators: direct input",
            NOT_VERIFIABLE,
            _ERROR_AFTER_EVIDENCE,
        ),
    )
}


def inventory_scope_hash(
    *,
    source_type: str,
    company_reference: str | None,
    api_region: str | None,
    keywords: Sequence[str],
    locations: Sequence[str],
) -> str:
    """Fingerprint of what a cached validator describes: host/board, filters and contract.

    A validator stored under one fingerprint may condition a request, or let a fully
    revalidated manifest reuse an inventory, only under that same fingerprint.
    """
    scope = {
        "version": INVENTORY_CONTRACT_VERSION,
        "source_type": source_type,
        "company_reference": company_reference,
        "api_region": api_region,
        "keywords": sorted(keyword.casefold() for keyword in keywords),
        "locations": sorted(location.casefold() for location in locations),
    }
    return hashlib.sha256(
        json.dumps(scope, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
