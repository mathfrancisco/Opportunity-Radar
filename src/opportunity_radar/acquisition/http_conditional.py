"""Shared HTTP-conditional-request helpers for collectors (F20-38/F20-39).

`AcquisitionService` already builds `CollectionRequest.conditional_headers` from the
checkpoint's stored `etag`/`last_modified` (F20-38) and already reads
`CollectionTelemetry.response_etag`/`response_last_modified`/`not_modified` back to
decide what a 304 proves (F20-39, SPEC 39 §7). What was missing is collectors actually
sending the headers and reporting the response — every collector duplicated the same
handful of lines, so this module gives them one shared implementation instead of eight
slightly different ones.

A collector that wants HTTP-conditional support:
1. Merges `conditional_request_headers(request)` into its outgoing request's headers.
2. Calls `record_conditional_response(request, response)` for every response the server
   actually returned (not a transport/timeout error) — this is a no-op unless the
   response carried an `ETag`/`Last-Modified` or was itself a 304.
3. On a bare 304, raises `NotModifiedResponse` (after step 2) instead of trying to parse
   a body that is not there; the collector's `discover()` catches it and stops cleanly,
   emitting no items and *not* calling `record_items_announced` — a 304 proves the
   representation is unchanged, never that the collector learned the board's total
   (SPEC 39 §7; `AcquisitionService` is the only thing allowed to turn a fully
   revalidated manifest into `run.complete`, see `service.py`).
"""

from __future__ import annotations

import httpx

from opportunity_radar.acquisition.domain import CollectionRequest


class NotModifiedResponse(Exception):
    """A bare 304: the representation is unchanged, there is no body to parse.

    Raised by a collector's low-level fetch method and caught by its own `discover()`,
    never allowed to escape a collector module.
    """


def conditional_request_headers(request: CollectionRequest) -> dict[str, str]:
    """`If-None-Match`/`If-Modified-Since` headers for the next request, if any.

    Empty when the request carries no conditional headers (no checkpoint yet, or the
    checkpoint belongs to a different scope — `AcquisitionService._conditional_headers_for`
    already refuses to build headers across scopes, so a collector never has to check
    that itself).
    """
    headers = request.conditional_headers
    if headers is None:
        return {}
    return headers.as_headers()


def record_conditional_response(
    request: CollectionRequest, response: httpx.Response
) -> None:
    """Report this response's validators and 304-ness to the run's telemetry.

    A no-op when the response carried neither a validator nor a 304 status, so a
    collector can call this unconditionally on every attempt without polluting
    telemetry for a plain 200 with no `ETag`/`Last-Modified`.
    """
    etag = response.headers.get("ETag")
    last_modified = response.headers.get("Last-Modified")
    not_modified = response.status_code == 304
    if etag is None and last_modified is None and not not_modified:
        return
    request.telemetry.record_conditional_response(
        etag=etag,
        last_modified=last_modified,
        not_modified=not_modified,
    )
