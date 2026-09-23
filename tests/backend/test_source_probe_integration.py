"""Database-backed proof that a live collector test is what confirms source evidence."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from opportunity_radar.acquisition.collectors import CollectorRegistry
from opportunity_radar.acquisition.domain import (
    AcquisitionError,
    AcquisitionErrorCode,
    CollectedItem,
    CollectionRequest,
    CollectorCapabilities,
    HealthResult,
)
from opportunity_radar.acquisition.models import (
    RawItemModel,
    SourceProbeModel,
    SourceRunModel,
)
from opportunity_radar.platform.config import Settings
from opportunity_radar.platform.database import create_database_engine
from opportunity_radar.presentation.http.app import create_app
from opportunity_radar.presentation.http.dependencies import get_collector_registry

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]


class _Board:
    """A Greenhouse stand-in that counts how often it was asked."""

    source_type = "greenhouse"
    capabilities = CollectorCapabilities(company_jobs=True)

    def __init__(self, *, broken: bool = False) -> None:
        self.broken = broken
        self.calls = 0

    async def healthcheck(self, context: object = None) -> HealthResult:
        return HealthResult(healthy=True)

    async def discover(self, request: CollectionRequest) -> AsyncIterator[CollectedItem]:
        self.calls += 1
        request.telemetry.record_http_attempt()
        if self.broken:
            raise AcquisitionError(
                AcquisitionErrorCode.PARSER_SCHEMA_CHANGED, "jobs field is missing"
            )
        yield CollectedItem(
            source_type="greenhouse",
            external_id="probe-1",
            raw_payload={"title": "Read, then discarded"},
            title="Read, then discarded",
        )


@pytest.fixture()
def board() -> _Board:
    return _Board()


@pytest.fixture()
def client(board: _Board) -> Iterator[TestClient]:
    app = create_app(Settings(database_url=os.environ["DATABASE_URL"]))
    app.dependency_overrides[get_collector_registry] = lambda: CollectorRegistry((board,))
    yield TestClient(app)


def _source(client: TestClient, **extra: object) -> dict[str, object]:
    created = client.post(
        "/sources",
        json={
            "source_type": "greenhouse",
            "name": f"Probe board {uuid4().hex[:8]}",
            "configuration": {"board_token": f"probe{uuid4().hex[:8]}"},
            **extra,
        },
    )
    assert created.status_code == 201
    return created.json()


def _counts(source_id: object) -> tuple[int, int, int]:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.connect() as connection:
        probes = connection.scalar(
            select(func.count()).where(SourceProbeModel.source_definition_id == source_id)
        )
        runs = connection.scalar(
            select(func.count()).where(SourceRunModel.source_definition_id == source_id)
        )
        raw = connection.scalar(
            select(func.count()).where(RawItemModel.source_definition_id == source_id)
        )
    return probes or 0, runs or 0, raw or 0


def _age_probes(source_id: object) -> None:
    """Moves this source's probes past the spacing rule, as if a minute went by."""
    engine = create_database_engine(os.environ["DATABASE_URL"])
    with engine.begin() as connection:
        connection.execute(
            update(SourceProbeModel)
            .where(SourceProbeModel.source_definition_id == source_id)
            .values(started_at=datetime.now(UTC) - timedelta(minutes=5))
        )


def test_a_passing_probe_confirms_evidence_and_nothing_else(
    client: TestClient, board: _Board
) -> None:
    source = _source(client)
    assert source["evidence_status"] == "unverified"

    probed = client.post(
        f"/sources/{source['id']}/probe", json={"expected_version": source["version"]}
    )

    assert probed.status_code == 200
    body = probed.json()
    assert body["probe"]["status"] == "PASSED"
    assert body["probe"]["evidence_recorded"] is True
    assert body["probe"]["requested_by"] == "interface"
    after = body["source"]
    assert after["evidence_status"] == "confirmed"
    assert after["collector_local_tested"] is True
    assert after["version"] == source["version"] + 1
    # The human half of the gate is untouched.
    assert after["terms_reviewed"] is False
    assert after["reviewed_at"] is None
    assert after["enabled"] is False
    audit = after["configuration"]["homologation_audit"]["collector_local_test"]
    assert audit["probe_id"] == body["probe"]["id"]
    assert audit["requested_by"] == "interface"
    # What the probe read is gone: no run, no raw item.
    assert _counts(source["id"]) == (1, 0, 0)
    assert board.calls == 1

    # With the evidence confirmed, the rest of the gate is the operator's, as before.
    enabled = client.patch(
        f"/sources/{source['id']}",
        json={
            "enabled": True,
            "terms_reviewed": True,
            "collector_local_tested": True,
            "reviewed_at": "2026-09-23T12:00:00Z",
            "expected_version": after["version"],
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


def test_a_failing_probe_changes_nothing_and_says_why(client: TestClient, board: _Board) -> None:
    board.broken = True
    source = _source(client)

    probed = client.post(
        f"/sources/{source['id']}/probe", json={"expected_version": source["version"]}
    )

    assert probed.status_code == 200
    body = probed.json()
    assert body["probe"]["status"] == "FAILED"
    assert body["probe"]["error_code"] == "PARSER_SCHEMA_CHANGED"
    assert body["probe"]["detail"] == "jobs field is missing"
    assert body["probe"]["evidence_recorded"] is False
    assert body["source"]["evidence_status"] == "unverified"
    assert body["source"]["version"] == source["version"]
    assert _counts(source["id"]) == (1, 0, 0)


def test_probes_are_spaced_so_a_double_click_is_one_request(
    client: TestClient, board: _Board
) -> None:
    board.broken = True
    source = _source(client)
    payload = {"expected_version": source["version"]}

    first = client.post(f"/sources/{source['id']}/probe", json=payload)
    second = client.post(f"/sources/{source['id']}/probe", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"]["retry_after_seconds"] > 0
    assert int(second.headers["Retry-After"]) > 0
    assert board.calls == 1
    assert _counts(source["id"])[0] == 1

    _age_probes(source["id"])
    board.broken = False
    third = client.post(f"/sources/{source['id']}/probe", json=payload)
    assert third.status_code == 200
    assert third.json()["probe"]["status"] == "PASSED"
    assert board.calls == 2


def test_probe_refuses_stale_enabled_and_manual_sources(
    client: TestClient, board: _Board
) -> None:
    source = _source(client)
    stale = client.post(
        f"/sources/{source['id']}/probe",
        json={"expected_version": int(str(source["version"])) + 5},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    enabled = _source(
        client,
        enabled=True,
        evidence_status="confirmed",
        reviewed_at="2026-09-23T12:00:00Z",
        terms_reviewed=True,
        collector_local_tested=True,
    )
    refused = client.post(
        f"/sources/{enabled['id']}/probe", json={"expected_version": enabled["version"]}
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["field"] == "enabled"

    manual = client.post(
        "/sources", json={"source_type": "manual", "name": f"Manual {uuid4().hex[:8]}"}
    ).json()
    no_endpoint = client.post(
        f"/sources/{manual['id']}/probe", json={"expected_version": manual["version"]}
    )
    assert no_endpoint.status_code == 422
    assert no_endpoint.json()["detail"]["field"] == "source_type"
    assert board.calls == 0
