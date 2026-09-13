import asyncio
from base64 import b64decode

import pytest

from opportunity_radar.acquisition.collectors import CollectorRegistry, ManualCollector
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectionMode,
    CollectionRequest,
    ManualInput,
    ManualInputKind,
)


async def _collect(request: CollectionRequest):
    return [item async for item in ManualCollector().discover(request)]


def test_manual_collector_preserves_url_and_text_payloads() -> None:
    request = CollectionRequest(
        mode=CollectionMode.MANUAL,
        manual_inputs=(
            ManualInput(kind=ManualInputKind.URL, value="https://example.com/jobs/1"),
            ManualInput(kind=ManualInputKind.TEXT, value="Original job description"),
        ),
    )

    items = asyncio.run(_collect(request))

    assert items[0].url == "https://example.com/jobs/1"
    assert items[0].raw_payload == {"kind": "URL", "url": "https://example.com/jobs/1"}
    assert items[1].description == "Original job description"
    assert items[1].raw_payload["text"] == "Original job description"


def test_manual_collector_preserves_file_bytes() -> None:
    request = CollectionRequest(
        mode=CollectionMode.MANUAL,
        manual_inputs=(
            ManualInput(
                kind=ManualInputKind.FILE,
                value="job.txt",
                content=b"Original file payload",
            ),
        ),
    )

    [item] = asyncio.run(_collect(request))

    assert item.raw_payload["filename"] == "job.txt"
    assert b64decode(item.raw_payload["content_base64"]) == b"Original file payload"


def test_registry_resolves_manual_collector() -> None:
    registry = CollectorRegistry((ManualCollector(),))

    assert registry.resolve("MANUAL").source_type == "manual"


def test_manual_collector_does_not_fetch_invalid_url() -> None:
    request = CollectionRequest(
        mode=CollectionMode.MANUAL,
        manual_inputs=(ManualInput(kind=ManualInputKind.URL, value="example.com/jobs"),),
    )

    with pytest.raises(AcquisitionError) as error:
        asyncio.run(_collect(request))

    assert error.value.code is AcquisitionErrorCode.MANUAL_INPUT_INVALID
