"""Collector port and the local-only manual collector adapter."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from base64 import b64encode
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionMode,
    CollectionRequest,
    CollectorCapabilities,
    HealthcheckContext,
    HealthResult,
    ManualInput,
    ManualInputKind,
)


class Collector(Protocol):
    source_type: str
    capabilities: CollectorCapabilities

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult: ...

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]: ...


class CollectorRegistry:
    """Maps stable source types to collector implementations."""

    def __init__(self, collectors: tuple[Collector, ...] = ()) -> None:
        self._collectors: dict[str, Collector] = {}
        for collector in collectors:
            self.register(collector)

    def register(self, collector: Collector) -> None:
        source_type = collector.source_type.strip().casefold()
        if not source_type:
            raise ValueError("collector source type cannot be empty")
        if source_type in self._collectors:
            raise ValueError(f"collector already registered: {source_type}")
        self._collectors[source_type] = collector

    def resolve(self, source_type: str) -> Collector:
        try:
            return self._collectors[source_type.strip().casefold()]
        except KeyError as error:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                f"collector is not registered: {source_type}",
            ) from error


class ManualCollector:
    """Turns URL, text, and local-file submissions into standard collected items.

    It deliberately never fetches a URL. The submitted URL is retained as raw input
    and goes through the same downstream pipeline as every external collector.
    """

    source_type = "manual"
    capabilities = CollectorCapabilities(direct_input=True)

    async def healthcheck(
        self, context: HealthcheckContext | None = None
    ) -> HealthResult:
        del context
        return HealthResult(healthy=True, summary="manual input is available locally")

    async def discover(
        self, request: CollectionRequest
    ) -> AsyncIterator[CollectedItem]:
        if request.mode is not CollectionMode.MANUAL:
            raise AcquisitionError(
                AcquisitionErrorCode.INVALID_CONFIGURATION,
                "manual collector requires manual collection mode",
            )
        inputs = request.manual_inputs
        if request.max_items is not None:
            inputs = inputs[: request.max_items]
        for manual_input in inputs:
            yield self._to_collected_item(manual_input)

    def _to_collected_item(self, manual_input: ManualInput) -> CollectedItem:
        if manual_input.kind is ManualInputKind.URL:
            return self._from_url(manual_input)
        if manual_input.kind is ManualInputKind.TEXT:
            return self._from_text(manual_input)
        if manual_input.kind is ManualInputKind.FILE:
            return self._from_file(manual_input)
        raise AcquisitionError(
            AcquisitionErrorCode.MANUAL_INPUT_INVALID,
            f"unsupported manual input kind: {manual_input.kind}",
        )

    def _from_url(self, manual_input: ManualInput) -> CollectedItem:
        parsed = urlparse(manual_input.value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AcquisitionError(
                AcquisitionErrorCode.MANUAL_INPUT_INVALID,
                "manual URL must be an absolute HTTP(S) URL",
            )
        payload: dict[str, Any] = {
            "kind": ManualInputKind.URL.value,
            "url": manual_input.value,
        }
        return self._item(manual_input, payload, url=manual_input.value)

    def _from_text(self, manual_input: ManualInput) -> CollectedItem:
        if not manual_input.value.strip():
            raise AcquisitionError(
                AcquisitionErrorCode.MANUAL_INPUT_INVALID,
                "manual text cannot be empty",
            )
        payload: dict[str, Any] = {
            "kind": ManualInputKind.TEXT.value,
            "text": manual_input.value,
        }
        return self._item(manual_input, payload, description=manual_input.value)

    def _from_file(self, manual_input: ManualInput) -> CollectedItem:
        path = Path(manual_input.value.replace("\\", "/")).name
        content = manual_input.content
        if not path or content is None:
            raise AcquisitionError(
                AcquisitionErrorCode.MANUAL_INPUT_INVALID,
                "manual file requires a filename and content",
            )
        payload: dict[str, Any] = {
            "kind": ManualInputKind.FILE.value,
            "filename": path,
            "content_base64": b64encode(content).decode("ascii"),
            "encoding": "base64",
        }
        content_type = manual_input.content_type or mimetypes.guess_type(path)[0]
        description = content.decode("utf-8", errors="replace")
        return self._item(
            manual_input,
            payload,
            description=description,
            content_type=content_type,
        )

    def _item(
        self,
        manual_input: ManualInput,
        payload: dict[str, Any],
        *,
        url: str | None = None,
        description: str | None = None,
        content_type: str | None = None,
    ) -> CollectedItem:
        serialized_payload = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(serialized_payload).hexdigest()
        metadata = {**manual_input.metadata}
        if content_type is not None:
            metadata["content_type"] = content_type
        return CollectedItem(
            source_type=self.source_type,
            external_id=f"manual:{digest}",
            url=url,
            description=description,
            raw_payload=payload,
            metadata=metadata,
        )
