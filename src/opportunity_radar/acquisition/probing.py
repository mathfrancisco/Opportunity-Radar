"""The live collector test that turns a researched source into confirmed evidence.

One definition of "the collector works against this endpoint", used by the enable script
and by the interface alike. It asks the public endpoint for a handful of items, keeps none
of them, and reports whether the collector could read the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionNetworkPolicy,
    CollectionRequest,
)

# The collectors a probe can exercise: every one with a public endpoint to call.
PROBE_TYPES = ("ashby", "lever", "greenhouse", "remotive")
PUBLIC_ENDPOINT_REFERENCES = {
    "ashby": "https://developers.ashbyhq.com/docs/public-job-posting-api",
    "greenhouse": "https://docs.greenhouse.io/job-board.html",
    "lever": "https://github.com/lever/postings-api",
    "remotive": "https://remotive.com/api-documentation",
}


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    ok: bool
    detail: str
    items_seen: int = 0
    http_requests: int = 0
    error_code: str | None = None
    last_http_attempt_at: datetime | None = None
    # Only set when error_code == SOURCE_RATE_LIMITED, from the response's Retry-After
    # header (F20-25): lets a batch of probes wait the right amount before the next one.
    retry_after_seconds: float | None = None


def probe_request(
    source_type: str,
    configuration: dict[str, Any],
    *,
    max_items: int,
    network_policy: CollectionNetworkPolicy | None = None,
) -> CollectionRequest:
    """The collection request a probe sends, built from the source's own configuration."""
    common: dict[str, Any] = {"max_items": max_items, "network_policy": network_policy}
    if source_type == "ashby":
        common["company_reference"] = _required(configuration, "board_identifier")
        common["company_name"] = configuration.get("company_name")
    elif source_type == "lever":
        common["company_reference"] = _required(configuration, "site_identifier")
        common["company_name"] = configuration.get("company_name")
        common["api_region"] = configuration.get("api_region", "global")
    elif source_type == "greenhouse":
        common["company_reference"] = _required(configuration, "board_token")
        common["company_name"] = configuration.get("company_name")
    return CollectionRequest(**common)


async def run_probe(
    source_type: str,
    configuration: dict[str, Any],
    registry: CollectorRegistry,
    *,
    max_items: int,
    network_policy: CollectionNetworkPolicy | None = None,
) -> ProbeOutcome:
    """Ask the endpoint for up to `max_items` items and discard them.

    Never raises for a collector failure: a probe that fails is an answer, and the caller
    records it like one that passed.
    """
    request: CollectionRequest | None = None
    try:
        if source_type not in PROBE_TYPES:
            raise ValueError(f"{source_type} has no public endpoint to probe")
        request = probe_request(
            source_type, configuration, max_items=max_items, network_policy=network_policy
        )
        collector = registry.resolve(source_type)
        items_seen = 0
        async for item in collector.discover(request):
            if not isinstance(item, CollectedItem):
                raise TypeError("collector emitted an invalid item")
            items_seen += 1
            if items_seen >= max_items:
                break
        return ProbeOutcome(
            ok=True,
            detail="public endpoint responded and the collector parsed its schema",
            items_seen=items_seen,
            http_requests=request.telemetry.http_requests,
            last_http_attempt_at=request.telemetry.last_http_attempt_at,
        )
    except AcquisitionError as error:
        return _failed(
            request,
            error.summary,
            error.code.value,
            retry_after_seconds=error.retry_after_seconds,
        )
    except (TypeError, ValueError) as error:
        return _failed(request, str(error), AcquisitionErrorCode.INVALID_CONFIGURATION.value)
    except Exception as error:  # A probe reports; it never takes the caller down.
        return _failed(request, str(error), AcquisitionErrorCode.UNKNOWN_EXTERNAL_ERROR.value)


def collector_test_audit(
    source_type: str,
    outcome: ProbeOutcome,
    *,
    probe_id: str | None,
    probed_at: datetime,
    requested_by: str,
) -> dict[str, Any]:
    """What the configuration keeps about the probe that confirmed the evidence."""
    return {
        "public_endpoint_reference": PUBLIC_ENDPOINT_REFERENCES[source_type],
        "collector_local_test": {
            "status": "passed",
            "items_seen": outcome.items_seen,
            "http_requests": outcome.http_requests,
            "probe_id": probe_id,
            "probed_at": probed_at.isoformat(),
            "requested_by": requested_by,
        },
    }


def _failed(
    request: CollectionRequest | None,
    detail: str,
    code: str,
    *,
    retry_after_seconds: float | None = None,
) -> ProbeOutcome:
    return ProbeOutcome(
        ok=False,
        detail=detail,
        error_code=code,
        http_requests=request.telemetry.http_requests if request else 0,
        last_http_attempt_at=request.telemetry.last_http_attempt_at if request else None,
        retry_after_seconds=retry_after_seconds,
    )


def _required(configuration: dict[str, Any], key: str) -> str:
    value = configuration.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"configuration requires {key}")
    return value.strip()
